"""팀 관리(팀장 전용).

팀원의 인사 정보와 그달 매출 목표를 다룬다. 목표는 sales_target 에서 거래처를 가리지 않는
행(customer_company_id IS NULL) 하나이고, 달성률은 dashboard._sales_target_card 와 같은
규약으로 센다. 두 화면이 다른 숫자를 말하면 팀장이 어느 쪽을 믿을지 알 수 없다.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.sales import SalesTarget
from app.models.workspace import Member
from app.schemas.team import TeamMemberPatch

ORIGIN = settings.cors_origin_list[0]
MONTH = date(2026, 8, 1)
_MISSING = object()


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None, scalar_values=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows
        self.scalar_values = [] if scalar_values is None else scalar_values

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def all(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result, flush_error: Exception | None = None):
        self.results = list(results)
        self.flush_error = flush_error
        self.statements = []
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1
        if self.flush_error is not None:
            raise self.flush_error

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(
    *,
    name: str = "합성 팀원",
    role: str = "member",
    team_id: UUID | None = None,
    active: bool = True,
) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name=name,
        role_code=role,
        job_title="영업 담당자",
        email="member@demo.test",
        active=active,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_overview_computes_achievement_per_member_and_for_the_team():
    manager = _member(name="합성 팀장", role="manager")
    teammate = _member(team_id=manager.team_id)

    db = _Db(
        _Result(scalar_values=[manager, teammate]),
        # 목표: 팀장 1억, 팀원 7천만
        _Result(rows=[(manager.id, 100_000_000), (teammate.id, 70_000_000)]),
        # 실적: 팀장 7천5백만, 팀원 5천2백만
        _Result(rows=[(manager.id, 75_000_000), (teammate.id, 52_000_000)]),
    )
    with _client(db, manager) as client:
        response = client.get("/api/team/members?target_month=2026-08-01")

    assert response.status_code == 200
    body = response.json()
    assert body["target_month"] == "2026-08"
    rows = {row["display_name"]: row for row in body["members"]}
    assert rows["합성 팀장"]["achievement_rate"] == 75.0
    assert rows["합성 팀원"]["achievement_rate"] == 74.3
    # 팀 목표는 팀원 목표의 합이다.
    assert body["team_target"] == body["member_target_sum"] == 170_000_000
    assert body["team_confirmed"] == 127_000_000
    assert body["team_rate"] == 74.7


def test_members_without_a_target_report_no_rate_rather_than_zero():
    """목표 미설정과 미달성은 다르다. 대시보드 카드와 같은 규약이다."""
    manager = _member(name="합성 팀장", role="manager")
    teammate = _member(team_id=manager.team_id)

    db = _Db(
        _Result(scalar_values=[manager, teammate]),
        _Result(rows=[]),
        _Result(rows=[(teammate.id, 3_000_000)]),
    )
    with _client(db, manager) as client:
        response = client.get("/api/team/members")

    assert response.status_code == 200
    body = response.json()
    assert [row["achievement_rate"] for row in body["members"]] == [None, None]
    assert body["team_rate"] is None
    # 목표가 없어도 실적은 그대로 센다.
    assert body["team_confirmed"] == 3_000_000


def test_overview_counts_only_confirmed_deals_signed_in_the_month():
    manager = _member(role="manager")
    db = _Db(
        _Result(scalar_values=[manager]),
        _Result(rows=[]),
        _Result(rows=[]),
    )
    with _client(db, manager) as client:
        assert client.get("/api/team/members?target_month=2026-08-01").status_code == 200

    sql = str(db.statements[2])
    assert "outcome_code" in sql
    assert "contract_signed_on" in sql
    assert "GROUP BY" in sql
    params = db.statements[2].compile().params
    assert MONTH in params.values()
    assert date(2026, 9, 1) in params.values()


def test_overview_and_patch_are_manager_only():
    teammate = _member()
    db = _Db()

    with _client(db, teammate) as client:
        listed = client.get("/api/team/members")
        patched = client.patch(
            f"/api/team/members/{teammate.id}",
            headers={"Origin": ORIGIN},
            json={"job_title": "팀장"},
        )

    assert listed.status_code == patched.status_code == 403
    assert listed.json() == patched.json() == {"detail": "manager_required"}
    # 권한부터 끊으므로 조회조차 하지 않는다.
    assert db.statements == []


def test_patch_creates_a_member_level_target_row():
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)

    db = _Db(
        _Result(scalar=teammate),
        # 아직 이 달 목표 행이 없다.
        _Result(scalar=None),
        _Result(rows=[(teammate.id, 70_000_000)]),
        _Result(rows=[(teammate.id, 35_000_000)]),
    )
    with _client(db, manager) as client:
        response = client.patch(
            f"/api/team/members/{teammate.id}",
            headers={"Origin": ORIGIN},
            json={"monthly_target_amount": 70_000_000, "target_month": "2026-08-01"},
        )

    assert response.status_code == 200
    assert response.json()["achievement_rate"] == 50.0
    assert len(db.added) == 1
    created = db.added[0]
    assert isinstance(created, SalesTarget)
    assert created.owner_member_id == teammate.id
    assert created.target_month == MONTH
    assert created.target_amount == 70_000_000
    # 거래처를 가리지 않는 행이어야 대시보드 합계에 한 번만 잡힌다.
    assert created.customer_company_id is None
    assert db.commit_count == 1


def test_patch_updates_an_existing_target_row_instead_of_adding_another():
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    existing = SalesTarget(
        id=uuid4(),
        owner_member_id=teammate.id,
        customer_company_id=None,
        target_month=MONTH,
        target_amount=50_000_000,
    )

    db = _Db(
        _Result(scalar=teammate),
        _Result(scalar=existing),
        _Result(rows=[(teammate.id, 80_000_000)]),
        _Result(rows=[]),
    )
    with _client(db, manager) as client:
        response = client.patch(
            f"/api/team/members/{teammate.id}",
            headers={"Origin": ORIGIN},
            json={"monthly_target_amount": 80_000_000, "target_month": "2026-08-01"},
        )

    assert response.status_code == 200
    assert existing.target_amount == 80_000_000
    assert db.added == []
    assert "FOR UPDATE" in str(db.statements[1])


def test_manager_cannot_demote_or_deactivate_themselves():
    """자기 역할을 내리면 이 화면에 다시 들어올 수 없다. 되살려 줄 사람도 없다."""
    manager = _member(role="manager")

    demote_db = _Db(_Result(scalar=manager))
    with _client(demote_db, manager) as client:
        demoted = client.patch(
            f"/api/team/members/{manager.id}",
            headers={"Origin": ORIGIN},
            json={"role_code": "member"},
        )
    assert demoted.status_code == 409
    assert demoted.json() == {"detail": "cannot_demote_self"}
    assert manager.role_code == "manager"
    assert demote_db.commit_count == 0

    deactivate_db = _Db(_Result(scalar=manager))
    with _client(deactivate_db, manager) as client:
        deactivated = client.patch(
            f"/api/team/members/{manager.id}",
            headers={"Origin": ORIGIN},
            json={"active": False},
        )
    assert deactivated.status_code == 409
    assert deactivated.json() == {"detail": "cannot_demote_self"}
    assert manager.active is True


def test_patch_on_another_team_is_not_found():
    manager = _member(role="manager")
    outsider = _member()

    db = _Db(_Result(scalar=None))
    with _client(db, manager) as client:
        response = client.patch(
            f"/api/team/members/{outsider.id}",
            headers={"Origin": ORIGIN},
            json={"job_title": "영업 담당자"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "member_not_found"}
    # 다른 팀 사람을 더듬어 볼 수 없도록 조회 자체에 팀 조건이 걸린다.
    assert manager.team_id in db.statements[0].compile().params.values()


def test_promoting_a_second_manager_is_rejected_by_the_index():
    """팀당 활성 팀장은 한 명이다. 근거는 DB 의 부분 유니크 인덱스다."""
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    violation = IntegrityError(
        "INSERT",
        {},
        Exception(
            'duplicate key value violates unique constraint "member_one_manager_per_team_uq"'
        ),
    )

    db = _Db(_Result(scalar=teammate), flush_error=violation)
    with _client(db, manager) as client:
        response = client.patch(
            f"/api/team/members/{teammate.id}",
            headers={"Origin": ORIGIN},
            json={"role_code": "manager"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "manager_already_exists"}
    assert db.rollback_count == 1


def test_patch_rejects_unsafe_values():
    with pytest.raises(ValidationError):
        # 목표는 음수가 될 수 없다.
        TeamMemberPatch(monthly_target_amount=-1)

    with pytest.raises(ValidationError):
        # 보낸 필수 항목을 null 로 지우지 않는다.
        TeamMemberPatch(role_code=None)

    with pytest.raises(ValidationError):
        # 목표 월은 그달 1일이다. sales_target 의 CHECK 와 같은 규약이다.
        TeamMemberPatch(target_month=date(2026, 8, 15))

    with pytest.raises(ValidationError):
        # 모르는 필드는 조용히 버리지 않고 거절한다.
        TeamMemberPatch(monthly_targt_amount=1)
