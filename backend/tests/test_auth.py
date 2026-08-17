import secrets
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.auth import (
    _login_attempts,
    _reserve_login_attempt,
)
from app.core.config import Settings, settings
from app.core.security import (
    create_session_token,
    hash_password,
    read_session_token,
    verify_password,
)
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member

ORIGIN = settings.cors_origin_list[0]


class _Result:
    def __init__(self, member: Member | None):
        self.member = member

    def scalar_one_or_none(self) -> Member | None:
        return self.member


class _Db:
    def __init__(self, member: Member | None):
        self.member = member

    async def execute(self, _statement):
        return _Result(self.member)


@pytest.fixture(autouse=True)
def reset_auth_state():
    _login_attempts.clear()
    app.dependency_overrides.clear()
    yield
    _login_attempts.clear()
    app.dependency_overrides.clear()


def _member(password_hash: str, *, active: bool = True) -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        login_id="manager@salesluv.demo",
        password_hash=password_hash,
        display_name="합성 팀장",
        role_code="manager",
        job_title="영업팀장",
        active=active,
    )


def _client(member: Member | None) -> TestClient:
    async def override_db():
        yield _Db(member)

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_password_hash_and_session_token_round_trip():
    password = secrets.token_urlsafe(24)
    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash)
    assert not verify_password(f"{password}x", first_hash)

    member_id = uuid4()
    secret = secrets.token_urlsafe(32)
    token = create_session_token(member_id, secret, 60, now=1_000)

    assert read_session_token(token, secret, now=1_059) == member_id
    assert read_session_token(token, secret, now=1_060) is None
    assert read_session_token(f"{token}x", secret, now=1_001) is None


def test_login_me_and_logout_use_signed_cookie():
    password = secrets.token_urlsafe(24)
    member = _member(hash_password(password))

    with _client(member) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"login_id": member.login_id.upper(), "password": password},
        )

        assert login.status_code == 200
        assert login.json() == {
            "id": str(member.id),
            "team_id": str(member.team_id),
            "display_name": "합성 팀장",
            "role_code": "manager",
            "job_title": "영업팀장",
        }
        cookie = login.headers["set-cookie"].lower()
        assert "salesluv_session=" in cookie
        assert "httponly" in cookie
        assert "samesite=lax" in cookie
        assert "path=/api" in cookie
        assert f"max-age={settings.session_ttl_seconds}" in cookie
        assert login.headers["cache-control"] == "no-store"
        assert not _login_attempts

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["id"] == str(member.id)

        logout = client.post("/api/auth/logout", headers={"Origin": ORIGIN})
        assert logout.status_code == 204
        assert logout.content == b""
        assert "max-age=0" in logout.headers["set-cookie"].lower()
        assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("member_state", ["missing", "wrong_password", "inactive"])
def test_invalid_login_does_not_reveal_account_state(member_state: str):
    password = secrets.token_urlsafe(24)
    member = None if member_state == "missing" else _member(hash_password(password))
    if member_state == "inactive" and member is not None:
        member.active = False
    submitted_password = f"{password}x" if member_state == "wrong_password" else password

    with _client(member) as client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"login_id": "manager@salesluv.demo", "password": submitted_password},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_credentials"}


def test_mutation_requires_exact_allowed_origin():
    password = secrets.token_urlsafe(24)
    with _client(None) as client:
        missing = client.post(
            "/api/auth/login",
            json={"login_id": "nobody", "password": password},
        )
        suffix = client.post(
            "/api/auth/login",
            headers={"Origin": f"{ORIGIN}.evil.test"},
            json={"login_id": "nobody", "password": password},
        )
        preflight = client.options(
            "/api/auth/login",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )

    assert missing.status_code == 403
    assert suffix.status_code == 403
    assert preflight.status_code == 200


def test_login_attempts_are_rate_limited():
    password = secrets.token_urlsafe(24)
    member = _member(hash_password(password))

    with _client(member) as client:
        for _ in range(settings.login_max_attempts):
            response = client.post(
                "/api/auth/login",
                headers={"Origin": ORIGIN},
                json={"login_id": member.login_id, "password": f"{password}x"},
            )
            assert response.status_code == 401

        limited = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"login_id": member.login_id, "password": password},
        )

    assert limited.status_code == 429
    assert limited.json() == {"detail": "login_rate_limited"}
    assert int(limited.headers["retry-after"]) > 0


def test_changing_login_id_does_not_bypass_ip_rate_limit():
    for _ in range(settings.login_max_attempts):
        login_id = f"target-{_}"
        assert _reserve_login_attempt("same-ip", login_id) is None

    assert _reserve_login_attempt("same-ip", "new-account") is not None


def test_validation_error_does_not_echo_password():
    submitted_password = secrets.token_urlsafe(257)

    with _client(None) as client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"login_id": "nobody", "password": submitted_password},
        )

    assert response.status_code == 422
    assert submitted_password not in response.text
    assert all("input" not in error for error in response.json()["detail"])


def test_production_auth_settings_fail_closed(monkeypatch):
    secret = secrets.token_urlsafe(32)

    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, session_secret=secret)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging", session_secret=secret)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            debug=True,
            cors_origins="https://salesluv.example",
            session_secret=secret,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            cors_origins="http://salesluv.example",
            session_secret=secret,
        )

    production = Settings(
        _env_file=None,
        app_env="production",
        debug=False,
        cors_origins="https://salesluv.example",
        session_secret=secret,
    )
    assert production.session_cookie_secure
