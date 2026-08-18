from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.db.session import get_db
from app.main import app
from app.models.sales import SalesDeal
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
            return "today" if "distinct" in sql else "follow_ups"
        if "public.sales_deal" in sql:
            return "deal_sums" if "sum(" in sql else "renewals"
        raise AssertionError(f"예상하지 못한 쿼리: {sql[:120]}")

    @staticmethod
    def _default(key: str):
        return {
            "notice_count": _Result(scalar=0),
            "notice_rows": _Result(rows=[]),
            "today": _Result(row=(0, 0)),
            "follow_ups": _Result(row=(0, 0, 0)),
            "support": _Result(row=(0, 0, 0)),
            "renewals": _Result(rows=[]),
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
        login_id=f"{uuid4()}@salesluv.demo",
        password_hash="unused",
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


def _deal(member: Member) -> SalesDeal:
    return SalesDeal(
        id=uuid4(),
        team_id=member.team_id,
        deal_no="SL-DL-2026-0001",
        customer_company_id=uuid4(),
        customer_contact_id=None,
        owner_member_id=member.id,
        product_id=None,
        sales_pipeline_id=uuid4(),
        sales_pipeline_stage_id=uuid4(),
        sales_deal_type_id=uuid4(),
        title="합성 딜",
        description=None,
        deal_amount=98_000_000,
        opened_on=date(2026, 1, 5),
        closed_on=None,
        quote_no=None,
        quote_issued_on=None,
        quote_valid_until=None,
        contract_no="FM-CT-2026-0001",
        contract_signed_on=date(2026, 2, 1),
        contract_ends_on=date(2026, 9, 1),
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        stage_position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


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
    deal = _deal(member)
    db = _Db(
        notice_count=_Result(scalar=5),
        notice_rows=_Result(rows=[(_notice(member), member.display_name)]),
        # 같은 회사를 두 번 방문해도 회사 수는 1이다. DISTINCT 결과를 그대로 받는다.
        today=_Result(row=(1, 2)),
        follow_ups=_Result(row=(4, 1, 2)),
        support=_Result(row=(3, 2, 1)),
        renewals=_Result(rows=[(deal, "새봄정형외과")]),
        deal_sums=_Result(row=(98_000_000, 30_000_000)),
    )

    with _client(db, member) as client:
        response = client.get("/api/dashboard?date=2026-08-18")

    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-08-18"
    assert body["visited_companies"]["count"] == 1
    assert body["activities"]["count"] == 2
    assert body["follow_ups"] == {"total": 4, "overdue": 1, "due_within_7_days": 2}
    assert body["support_requests"] == {"total": 3, "in_progress": 2, "urgent": 1}

    renewal = body["contract_renewals"]
    assert renewal["within_days"] == 30
    assert renewal["count"] == 1
    assert renewal["items"][0]["contract_no"] == "FM-CT-2026-0001"
    assert renewal["items"][0]["contract_ends_on"] == "2026-09-01"
    assert renewal["items"][0]["customer_company_name"] == "새봄정형외과"
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
