"""어드민 계정 발급 테스트.

실제 Supabase 를 부르지 않는다. supabase_auth 의 admin 함수 세 개를 갈아끼워
"어느 한쪽만 남는 상태"가 생기는지를 본다.
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.admin import LOCAL_DEV_PASSWORD
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member, Team
from app.services import supabase_auth

ORIGIN = settings.cors_origin_list[0]
ADMIN_ID = UUID("aaaaaaaa-1111-4111-8111-111111111111")
PLAIN_ID = UUID("bbbbbbbb-2222-4222-8222-222222222222")
INVITED_ID = UUID("cccccccc-3333-4333-8333-333333333333")
# 검증 숫자가 맞는 사업자등록번호.
VALID_BUSINESS_NO = "220-81-62517"


class _Db:
    """계정 발급이 실제로 쓰는 만큼만 흉내낸다: get / add / flush / commit / rollback."""

    def __init__(
        self,
        *,
        teams: list[Team] | None = None,
        members: list[Member] | None = None,
        fail_on_commit: bool = False,
    ):
        self.teams = teams or []
        self.members = members or []
        self.added: list[object] = []
        self.fail_on_commit = fail_on_commit
        self.committed = False
        self.rolled_back = False

    async def get(self, _model, key):
        return next((team for team in self.teams if team.id == key), None)

    async def execute(self, statement):
        # list_teams 는 Team 과 Member 를 차례로 훑고, _resolve_team 은 count 를 센다.
        text = str(statement)
        if "FROM public.member" in text:
            return _CountResult(len(self.members), self.members)
        if "count(" in text:
            return _CountResult(len(self.teams))
        return _CountResult(len(self.teams), self.teams)

    def add(self, entity):
        self.added.append(entity)

    async def flush(self):
        return None

    async def commit(self):
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _CountResult:
    """count() 와 목록 조회 두 쓰임을 함께 흉내낸다."""

    def __init__(self, value: int, rows: list | None = None):
        self.value = value
        self.rows = rows or []

    def scalar_one(self) -> int:
        return self.value

    def scalars(self):
        return self

    def all(self) -> list:
        return self.rows


class _SupabaseSpy:
    """invite / create / delete 호출을 기록한다. 되돌리기가 실제로 일어났는지 보려고 둔다."""

    def __init__(self, *, invite: UUID | Exception = INVITED_ID):
        self.invite_outcome = invite
        self.invited: list[str] = []
        self.created: list[tuple[str, str]] = []
        self.deleted: list[UUID] = []

    async def invite_user(self, *, email: str, redirect_to: str) -> UUID:
        self.invited.append(email)
        self.redirect_to = redirect_to
        if isinstance(self.invite_outcome, Exception):
            raise self.invite_outcome
        return self.invite_outcome

    async def create_confirmed_user(self, *, email: str, password: str) -> UUID:
        self.created.append((email, password))
        if isinstance(self.invite_outcome, Exception):
            raise self.invite_outcome
        return self.invite_outcome

    async def delete_user(self, *, user_id: UUID) -> None:
        self.deleted.append(user_id)


def _member(member_id: UUID) -> Member:
    return Member(
        id=member_id,
        team_id=uuid4(),
        display_name="합성 사용자",
        role_code="manager",
        job_title=None,
        active=True,
    )


@pytest.fixture(autouse=True)
def admin_environment(monkeypatch):
    # local 이면 초대 대신 고정 비밀번호 경로를 탄다. 개발자 .env 가 APP_ENV=local 이라
    # 여기서 못박지 않으면 초대 흐름 테스트가 조용히 다른 경로를 보게 된다.
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.test")
    monkeypatch.setattr(settings, "supabase_secret_key", SecretStr("secret-test-key"))
    monkeypatch.setattr(settings, "admin_user_ids", str(ADMIN_ID))
    monkeypatch.setattr(settings, "frontend_base_url", "https://app.salesluv.test")
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _client(*, signed_in_as: UUID | None, db: _Db, spy: _SupabaseSpy, monkeypatch) -> TestClient:
    monkeypatch.setattr(supabase_auth, "invite_user", spy.invite_user)
    monkeypatch.setattr(supabase_auth, "create_confirmed_user", spy.create_confirmed_user)
    monkeypatch.setattr(supabase_auth, "delete_user", spy.delete_user)

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    if signed_in_as is not None:
        app.dependency_overrides[get_current_member] = lambda: _member(signed_in_as)
    return TestClient(app)


def _payload(**overrides) -> dict:
    payload = {
        "email": "new.member@salesluv.test",
        "display_name": "김신입",
        "role_code": "member",
        "team": {
            "name": "영업 1팀",
            "company_name": "세일즈러브",
            "department": "영업본부",
            "business_no": VALID_BUSINESS_NO,
        },
    }
    payload.update(overrides)
    return payload


def _post(client: TestClient, payload: dict):
    return client.post("/api/admin/accounts", headers={"Origin": ORIGIN}, json=payload)


def test_non_admin_member_cannot_create_accounts(monkeypatch):
    spy = _SupabaseSpy()
    client = _client(signed_in_as=PLAIN_ID, db=_Db(), spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload())

    assert response.status_code == 403
    assert response.json()["detail"] == "admin_only"
    # 막혔다면 Supabase 사용자도 생기지 않아야 한다.
    assert spy.invited == []


def test_admin_creates_team_and_member_and_sends_one_invite(monkeypatch):
    spy = _SupabaseSpy()
    db = _Db()
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload())

    assert response.status_code == 201
    body = response.json()
    # member.id 는 초대가 만든 auth 사용자 id 와 같아야 한다.
    assert body["id"] == str(INVITED_ID)
    assert body["email"] == "new.member@salesluv.test"
    assert spy.invited == ["new.member@salesluv.test"]
    assert spy.redirect_to == "https://app.salesluv.test/set-password"
    assert db.committed and not db.rolled_back
    assert spy.deleted == []

    team = next(entity for entity in db.added if isinstance(entity, Team))
    member = next(entity for entity in db.added if isinstance(entity, Member))
    assert team.business_no == "2208162517"
    assert team.company_name == "세일즈러브"
    assert member.team_id == team.id
    assert member.role_code == "member"


def test_instant_skips_the_invite_and_fixes_the_password(monkeypatch):
    """메일을 받을 곳이 없을 때 쓰는 경로. 메일 대신 고정 비밀번호로 계정이 서야 한다."""
    monkeypatch.setattr(settings, "app_env", "local")
    spy = _SupabaseSpy()
    db = _Db()
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload(email="아무거나@test.test", instant=True))

    assert response.status_code == 201
    assert spy.invited == []
    assert spy.created == [("아무거나@test.test", LOCAL_DEV_PASSWORD)]
    assert db.committed and not db.rolled_back

    member = next(entity for entity in db.added if isinstance(entity, Member))
    assert member.id == INVITED_ID
    assert member.email == "아무거나@test.test"


def test_local_still_invites_when_instant_is_not_asked_for(monkeypatch):
    """로컬이어도 고르는 쪽이 정한다. local 이라는 이유만으로 메일을 건너뛰지 않는다."""
    monkeypatch.setattr(settings, "app_env", "local")
    spy = _SupabaseSpy()
    client = _client(signed_in_as=ADMIN_ID, db=_Db(), spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload())

    assert response.status_code == 201
    assert spy.created == []
    assert spy.invited == ["new.member@salesluv.test"]


def test_instant_is_refused_outside_local_and_writes_nothing(monkeypatch):
    """배포 환경에서는 조용히 초대로 넘기지 않고 거절한다."""
    spy = _SupabaseSpy()
    db = _Db()
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload(instant=True))

    assert response.status_code == 422
    assert response.json()["detail"] == "instant_local_only"
    assert spy.created == [] and spy.invited == []
    assert db.added == [] and not db.committed


def test_db_failure_removes_the_invited_supabase_user(monkeypatch):
    spy = _SupabaseSpy()
    db = _Db(fail_on_commit=True)
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)

    with client, pytest.raises(RuntimeError):
        _post(client, _payload())

    assert db.rolled_back and not db.committed
    # 초대만 남으면 그 이메일로 다시 발급할 수 없게 된다.
    assert spy.deleted == [INVITED_ID]


def test_existing_email_is_a_conflict_and_writes_nothing(monkeypatch):
    spy = _SupabaseSpy(invite=supabase_auth.EmailAlreadyExists("email_already_exists"))
    db = _Db()
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload())

    assert response.status_code == 409
    assert response.json()["detail"] == "email_already_exists"
    assert not db.committed
    assert not any(isinstance(entity, Member) for entity in db.added)


def test_unknown_team_id_fails_before_any_supabase_user_is_made(monkeypatch):
    spy = _SupabaseSpy()
    db = _Db()
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload(team=None, team_id=str(uuid4())))

    assert response.status_code == 404
    assert response.json()["detail"] == "team_not_found"
    # 되돌릴 것이 없는 실패가 되돌려야 하는 실패보다 낫다.
    assert spy.invited == []


def test_account_joins_an_existing_team_without_creating_one(monkeypatch):
    existing = Team(id=uuid4(), name="영업 1팀")
    spy = _SupabaseSpy()
    db = _Db(teams=[existing])
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload(team=None, team_id=str(existing.id)))

    assert response.status_code == 201
    assert response.json()["team_id"] == str(existing.id)
    assert not any(isinstance(entity, Team) for entity in db.added)


@pytest.mark.parametrize("business_no", ["220-81-62518", "12345", "abcdefghij"])
def test_business_no_checksum_is_enforced(business_no, monkeypatch):
    spy = _SupabaseSpy()
    db = _Db()
    client = _client(signed_in_as=ADMIN_ID, db=db, spy=spy, monkeypatch=monkeypatch)
    payload = _payload()
    payload["team"]["business_no"] = business_no

    with client:
        response = _post(client, payload)

    assert response.status_code == 422
    assert spy.invited == []


def test_admin_surface_is_unavailable_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "admin_user_ids", "")
    spy = _SupabaseSpy()
    client = _client(signed_in_as=ADMIN_ID, db=_Db(), spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload())

    assert response.status_code == 503
    assert response.json()["detail"] == "admin_not_configured"


def test_signed_out_request_is_unauthenticated(monkeypatch):
    spy = _SupabaseSpy()
    client = _client(signed_in_as=None, db=_Db(), spy=spy, monkeypatch=monkeypatch)

    with client:
        response = _post(client, _payload())

    assert response.status_code == 401
    assert spy.invited == []


def test_teams_listing_is_admin_only(monkeypatch):
    spy = _SupabaseSpy()
    client = _client(signed_in_as=PLAIN_ID, db=_Db(), spy=spy, monkeypatch=monkeypatch)

    with client:
        assert client.get("/api/admin/teams").status_code == 403


def test_teams_listing_carries_members_and_counts(monkeypatch):
    """발급 화면이 기존 팀을 고르고 이미 있는 계정을 확인하는 데 쓰는 응답이다."""
    team = Team(
        id=uuid4(),
        name="영업 1팀",
        company_name="세일즈러브",
        department="영업본부",
        business_no="2208162517",
    )
    member = Member(
        id=uuid4(),
        team_id=team.id,
        display_name="김지훈",
        role_code="member",
        job_title=None,
        email="jihoon@salesluv.test",
        active=True,
    )
    client = _client(
        signed_in_as=ADMIN_ID,
        db=_Db(teams=[team], members=[member]),
        spy=_SupabaseSpy(),
        monkeypatch=monkeypatch,
    )

    with client:
        response = client.get("/api/admin/teams")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(team.id),
            "name": "영업 1팀",
            "company_name": "세일즈러브",
            "department": "영업본부",
            "business_no": "2208162517",
            "member_count": 1,
            "members": [
                {
                    "id": str(member.id),
                    "display_name": "김지훈",
                    "email": "jihoon@salesluv.test",
                    "role_code": "member",
                    "active": True,
                }
            ],
        }
    ]
