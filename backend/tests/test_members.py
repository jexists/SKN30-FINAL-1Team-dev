from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_member
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _Scalars(self.values)


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results
        return self.results.pop(0)


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(
    *,
    name: str = "합성 영업 담당자",
    role: str = "member",
    team_id: UUID | None = None,
) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name=name,
        role_code=role,
        job_title="영업 담당자",
        email="member@demo.test",
        active=True,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_team_members_are_scoped_to_the_callers_team_and_active_only():
    caller = _member(role="manager")
    teammate = _member(name="합성 팀원", team_id=caller.team_id)
    db = _Db(_Result([caller, teammate]))

    with _client(db, caller) as client:
        response = client.get("/api/team-members")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(caller.id), str(teammate.id)]
    statement = db.statements[0]
    assert caller.team_id in statement.compile().params.values()
    sql = str(statement)
    assert "public.member.active IS true" in sql
    assert "public.member.role_code IN" in sql
    assert "ORDER BY public.member.display_name" in sql


def test_team_members_do_not_expose_email():
    caller = _member()
    db = _Db(_Result([caller]))

    with _client(db, caller) as client:
        response = client.get("/api/team-members")

    assert response.status_code == 200
    # 이메일은 어드민 목록 화면 전용이라 일반 화면까지 내보내지 않는다.
    assert response.json() == [
        {
            "id": str(caller.id),
            "display_name": caller.display_name,
            "job_title": caller.job_title,
            "role_code": caller.role_code,
        }
    ]
