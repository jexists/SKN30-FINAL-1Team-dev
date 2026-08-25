from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.db.session import get_db
from app.main import app
from app.models.configuration import ActivityCategory
from app.models.crm import Activity
from app.models.workspace import Member, Notice
from app.schemas.dashboard import DashboardParams

NOW = datetime(2026, 8, 18, 9, tzinfo=UTC)
_MISSING = object()


class _Result:
    def __init__(self, *, scalar=_MISSING, row=None, rows=None):
        self.scalar = scalar
        self.row = row
        self.rows = [] if rows is None else rows

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        return None if self.scalar is _MISSING else self.scalar

    def one(self):
        assert self.row is not None
        return self.row

    def all(self):
        return self.rows


class _Db:
    """SQL 내용을 보고 응답을 고른다. 쿼리 순서가 바뀌어도 테스트가 깨지지 않는다."""

    def __init__(self, **overrides):
        self.statements = []
        self.overrides = overrides

    async def execute(self, statement):
        sql = str(statement).lower()
        self.statements.append(sql)
        key = self._key(sql)
        if key in self.overrides:
            return self.overrides[key]
        return self._default(key)

    @staticmethod
    def _key(sql: str) -> str:
        # sales_target 과 purchase_order 를 sales_deal 보다 먼저 본다. join 으로 겹친다.
        if "public.sales_target" in sql:
            return "target_sum"
        if "public.notice" in sql:
            return "notice_count" if "count(" in sql else "notice_rows"
        if "public.purchase_order" in sql:
            return "weekly_orders"
        if "public.support_request" in sql:
            return "support"
        if "public.activity" in sql:
            if "group by" in sql:
                return "weekly_activities"
            if "distinct" in sql:
                return "today"
            # 후속업무는 집계 세 개, 오늘 목록은 행 조회다.
            return "follow_ups" if "count(" in sql else "today_rows"
        if "public.sales_deal" in sql:
            if "sum(" in sql:
                return "deal_sums"
            return "renewal_count" if "count(" in sql else "renewal_lead"
        raise AssertionError(f"예상하지 못한 쿼리: {sql[:120]}")

    @staticmethod
    def _default(key: str):
        return {
            "notice_count": _Result(scalar=0),
            "notice_rows": _Result(rows=[]),
            "today": _Result(row=(0, 0)),
            "today_rows": _Result(rows=[]),
            "follow_ups": _Result(row=(0, 0, 0)),
            "support": _Result(row=(0, 0, 0)),
            "renewal_count": _Result(scalar=0),
            "renewal_lead": _Result(scalar=None),
            "target_sum": _Result(scalar=None),
            "deal_sums": _Result(row=(None, None)),
            "weekly_activities": _Result(rows=[]),
            "weekly_orders": _Result(rows=[]),
        }[key]

    def sql_for(self, key: str) -> str:
        for sql in self.statements:
            if self._key(sql) == key:
                return sql
        raise AssertionError(f"{key} 쿼리가 실행되지 않았습니다.")


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(*, role: str = "member") -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _notice(author: Member) -> Notice:
    return Notice(
        id=uuid4(),
        team_id=author.team_id,
        author_member_id=author.id,
        recipient_member_id=None,
        tag="공지",
        title="합성 공지",
        body="합성 본문",
        image_storage_key="team/secret-object-key.png",
        image_alt=None,
        published_at=NOW,
        due_at=None,
        due_text=None,
    )


def _category(team_id) -> ActivityCategory:
    return ActivityCategory(
        id=uuid4(),
        team_id=team_id,
        code="visit",
        name="방문",
        tone="blue",
        position=1,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
        activity_type="meeting",
    )


def _activity_row(member: Member, *, hour: int, title: str):
    """오늘 목록 한 줄. 회사·고객·상품이 없는 최소 형태로 둔다."""
    activity = Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        customer_contact_id=None,
        end_user_contact_id=None,
        activity_type="meeting",
        activity_category_id=uuid4(),
        title=title,
        starts_at=datetime(2026, 8, 18, hour, tzinfo=UTC),
        ends_at=None,
        all_day=False,
        due_at=None,
        location=None,
        activity_action_tag_id=None,
        completed_at=None,
        note=None,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
        product_id=None,
        sales_deal_id=None,
        purchase_order_id=None,
    )
    return (activity, member.display_name, None, None, None, None, _category(member.team_id), None)


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_dashboard_params_reject_unsafe_values():
    with pytest.raises(ValidationError):
        DashboardParams(notice_limit=31)
    with pytest.raises(ValidationError):
        DashboardParams(notice_limit=0)
    with pytest.raises(ValidationError):
        DashboardParams(team_id=str(uuid4()))
    assert DashboardParams().date is None


def test_member_cannot_widen_owner_scope():
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        response = client.get(f"/api/dashboard?owner_member_id={uuid4()}")
    assert response.status_code == 403
    assert response.json() == {"detail": "scope_not_allowed"}


def test_manager_cannot_use_other_team_owner():
    manager = _member(role="manager")

    class _ScopeDb(_Db):
        async def execute(self, statement):
            sql = str(statement).lower()
            if "public.member" in sql and "public.notice" not in sql:
                self.statements.append(sql)
                return _Scalars()
            return await super().execute(statement)

    class _Scalars:
        def scalars(self):
            return self

        def all(self):
            return []

    with _client(_ScopeDb(), manager) as client:
        response = client.get(f"/api/dashboard?owner_member_id={uuid4()}")
    assert response.status_code == 403
    assert response.json() == {"detail": "scope_not_allowed"}


def test_cards_and_weekly_band_shape():
    member = _member()
    db = _Db(
        notice_count=_Result(scalar=5),
        notice_rows=_Result(rows=[(_notice(member), member.display_name)]),
        # 같은 회사를 두 번 방문해도 회사 수는 1이다. DISTINCT 결과를 그대로 받는다.
        today=_Result(row=(1, 2)),
        follow_ups=_Result(row=(4, 1, 2)),
        support=_Result(row=(3, 2, 1)),
        renewal_count=_Result(scalar=1),
        renewal_lead=_Result(scalar="새봄정형외과"),
        deal_sums=_Result(row=(98_000_000, 30_000_000)),
    )

    with _client(db, member) as client:
        response = client.get("/api/dashboard?date=2026-08-18&renewal_within_days=30")

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-08-18"
    assert body["visited_companies"]["count"] == 1
    assert body["activities"]["count"] == 2
    assert body["follow_ups"] == {"total": 4, "overdue": 1, "due_within_7_days": 2}
    assert body["support_requests"] == {"total": 3, "in_progress": 2, "urgent": 1}

    renewal = body["contract_renewals"]
    # 서버가 기준 일수를 정하지 않는다. 요청이 준 값을 그대로 되돌려 준다.
    assert renewal["within_days"] == 30
    assert renewal["count"] == 1
    # 목록 전체는 카드를 눌렀을 때 /api/sales-deals 가 준다. 여기는 앞자리 하나만.
    assert renewal["lead_company_name"] == "새봄정형외과"
    assert "items" not in renewal
    # 표시 문구는 서버가 만들지 않는다.
    assert "외 1곳" not in response.text

    # 주간은 기준일이 셋째 칸에 오는 7일이다.
    weekly = body["weekly"]
    assert weekly["start_date"] == "2026-08-16"
    assert weekly["end_date"] == "2026-08-22"
    assert len(weekly["days"]) == 7
    assert weekly["days"][2]["date"] == "2026-08-18"

    # 공지 응답에 저장소 경로가 새지 않는다.
    assert "storage_key" not in response.text


@pytest.mark.parametrize(
    ("requested", "expected_start"),
    [
        ("2026-08-16", "2026-08-16"),  # 일요일
        ("2026-08-18", "2026-08-16"),  # 화요일
        ("2026-08-22", "2026-08-16"),  # 토요일
        ("2026-08-23", "2026-08-23"),  # 다음 주 일요일
    ],
)
def test_weekly_band_is_the_calendar_week(requested, expected_start):
    """유스케이스의 전 주·오늘·다음 주 이동이 주 단위라 달력 주(일~토)를 반환한다."""
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        weekly = client.get(f"/api/dashboard?date={requested}").json()["weekly"]

    assert weekly["start_date"] == expected_start
    assert len(weekly["days"]) == 7
    assert weekly["days"][0]["date"] == expected_start
    assert weekly["days"][-1]["date"] == weekly["end_date"]


def test_renewal_window_is_caller_supplied():
    """유스케이스가 갱신 기준 일수를 정하지 않아 서버가 기본값을 만들지 않는다."""
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        body = client.get("/api/dashboard?date=2026-08-18").json()

    assert body["contract_renewals"]["within_days"] is None
    # 생략하면 기준일 이후 만료 예정 전체를 보므로 상한 조건이 붙지 않는다.
    sql = db.sql_for("renewal_count")
    assert "contract_ends_on >=" in sql
    assert "contract_ends_on <=" not in sql


def test_missing_target_gives_null_rate_not_zero():
    member = _member()
    db = _Db(deal_sums=_Result(row=(98_000_000, 0)))
    with _client(db, member) as client:
        body = client.get("/api/dashboard?date=2026-08-18").json()

    target = body["sales_target"]
    assert target["target_amount"] is None
    assert target["achievement_rate"] is None
    assert target["confirmed_amount"] == 98_000_000
    assert target["in_progress_amount"] == 0
    assert target["target_month"] == "2026-08"


def test_notice_queries_ignore_owner_scope():
    """공지와 지시는 팀 공개 범위다. 담당자 조건이 섞이면 안 된다."""
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        assert client.get("/api/dashboard?date=2026-08-18").status_code == 200

    notice_sql = db.sql_for("notice_count")
    assert "public.notice.team_id" in notice_sql
    assert "owner_member_id" not in notice_sql

    # 반대로 업무 집계에는 담당자 조건이 들어간다.
    assert "activity.owner_member_id" in db.sql_for("today")


def test_today_activities_come_with_the_card_number():
    """오늘 일정은 진입하자마자 화면에 선다. 카드 숫자와 목록 길이가 같아야 한다."""
    member = _member()
    db = _Db(
        today=_Result(row=(1, 2)),
        today_rows=_Result(
            rows=[
                _activity_row(member, hour=1, title="합성 오전 미팅"),
                _activity_row(member, hour=5, title="합성 오후 미팅"),
            ]
        ),
    )
    with _client(db, member) as client:
        body = client.get("/api/dashboard?date=2026-08-18").json()

    assert body["activities"]["count"] == 2
    assert len(body["today_activities"]) == 2
    assert [item["title"] for item in body["today_activities"]] == [
        "합성 오전 미팅",
        "합성 오후 미팅",
    ]
    # 목록도 카드와 같은 하루 경계·같은 담당자 범위를 쓴다. 한쪽만 넓으면 숫자가 어긋난다.
    sql = db.sql_for("today_rows")
    assert "activity.owner_member_id" in sql
    assert "activity.starts_at >=" in sql
    assert "activity.starts_at <" in sql


def test_weekly_start_date_is_caller_supplied():
    """화면이 오늘을 셋째 칸에 두는 7일을 세우므로 시작일을 요청이 정한다."""
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        # 2026-08-17 은 월요일이다. 일요일로 되감기지 않아야 한다.
        weekly = client.get("/api/dashboard?date=2026-08-18&weekly_start_date=2026-08-17").json()[
            "weekly"
        ]

    assert weekly["start_date"] == "2026-08-17"
    assert weekly["end_date"] == "2026-08-23"
    assert weekly["days"][0]["date"] == "2026-08-17"
    assert len(weekly["days"]) == 7


def test_notice_items_omit_the_body():
    """티커는 제목만 세운다. 본문은 눌렀을 때 /api/notices/{id} 가 준다."""
    member = _member()
    db = _Db(
        notice_count=_Result(scalar=5),
        notice_rows=_Result(rows=[(_notice(member), member.display_name)]),
    )
    with _client(db, member) as client:
        response = client.get("/api/dashboard?date=2026-08-18")

    item = response.json()["notices"]["items"][0]
    assert item["title"] == "합성 공지"
    assert item["author_display_name"] == member.display_name
    assert "body" not in item
    assert "합성 본문" not in response.text
