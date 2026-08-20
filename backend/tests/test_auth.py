"""인증 API 테스트.

실제 Supabase 를 부르지 않는다. httpx 호출을 모듈 속성 교체로 가로채고,
JWKS 와 access token 은 테스트가 직접 만든 EC 키로 서명해 맞춘다.
"""

import json
import secrets
import time
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.api.auth import _login_attempts, _reserve_login_attempt
from app.core.config import Settings, settings
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member
from app.services import supabase_auth

ORIGIN = settings.cors_origin_list[0]
SESSION_COOKIES = {"salesluv_access", "salesluv_refresh", "salesluv_signed_in"}
KID = "test-signing-key"
AUTH_USER_ID = UUID("11111111-2222-4333-8444-555555555555")

_signing_key = ec.generate_private_key(ec.SECP256R1())
_JWKS = {
    "keys": [
        {
            **json.loads(jwt.algorithms.ECAlgorithm.to_jwk(_signing_key.public_key())),
            "kid": KID,
            "alg": "ES256",
            "use": "sig",
        }
    ]
}


def access_token(*, subject: UUID = AUTH_USER_ID, expires_in: int = 3_600) -> str:
    return jwt.encode(
        {
            "sub": str(subject),
            "aud": "authenticated",
            "exp": int(time.time()) + expires_in,
        },
        _signing_key,
        algorithm="ES256",
        headers={"kid": KID},
    )


def session_payload(*, expires_in: int = 3_600) -> dict[str, object]:
    return {
        "access_token": access_token(expires_in=expires_in),
        "refresh_token": secrets.token_urlsafe(24),
        "expires_in": expires_in,
    }


class _Response:
    def __init__(self, status_code: int, payload: object | None = None):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class _SupabaseStub:
    """`/token`, `/logout`, JWKS 세 경로만 흉내낸다."""

    def __init__(self, *, token: _Response | Exception, logout: _Response | Exception):
        self.token = token
        self.logout = logout
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url: str, **_kwargs) -> _Response:
        self.calls.append(("GET", url))
        return _Response(200, _JWKS)

    async def post(self, url: str, **_kwargs) -> _Response:
        self.calls.append(("POST", url))
        outcome = self.logout if url.endswith("/logout") else self.token
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


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
def auth_environment(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.test")
    monkeypatch.setattr(settings, "supabase_publishable_key", SecretStr("publishable-test-key"))
    supabase_auth.reset_jwks_cache()
    _login_attempts.clear()
    app.dependency_overrides.clear()
    yield
    supabase_auth.reset_jwks_cache()
    _login_attempts.clear()
    app.dependency_overrides.clear()


def _member(*, active: bool = True, role_code: str = "manager") -> Member:
    return Member(
        id=AUTH_USER_ID,
        team_id=uuid4(),
        display_name="합성 팀장",
        role_code=role_code,
        job_title="영업팀장",
        active=active,
    )


def _client(
    member: Member | None,
    monkeypatch,
    *,
    token: _Response | Exception | None = None,
    logout: _Response | Exception | None = None,
) -> tuple[TestClient, _SupabaseStub]:
    """member 는 DB 조회 결과, token/logout 은 Supabase 응답을 정한다."""
    stub = _SupabaseStub(
        token=_Response(200, session_payload()) if token is None else token,
        logout=_Response(204) if logout is None else logout,
    )
    monkeypatch.setattr(supabase_auth.httpx, "AsyncClient", lambda **_kwargs: stub)

    async def override_db():
        yield _Db(member)

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), stub


def _cookie_names(response) -> set[str]:
    return {header.split("=", 1)[0] for header in response.headers.get_list("set-cookie")}


def _cookie_text(response) -> str:
    return "; ".join(response.headers.get_list("set-cookie")).lower()


def test_login_sets_token_cookies_and_a_readable_session_hint(monkeypatch):
    member = _member()
    client, _stub = _client(member, monkeypatch)

    with client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "MANAGER@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": str(member.id),
        "team_id": str(member.team_id),
        "display_name": "합성 팀장",
        "role_code": "manager",
        "job_title": "영업팀장",
    }
    cookies = _cookie_text(response)
    assert _cookie_names(response) == SESSION_COOKIES
    # 토큰 두 개만 HttpOnly 다. 표시 쿠키는 프론트가 읽어야 한다.
    assert cookies.count("httponly") == 2
    assert cookies.count("samesite=lax") == 3
    assert "path=/api/auth" in cookies
    assert f"max-age={settings.refresh_cookie_max_age_seconds}" in cookies

    hint = next(
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith("salesluv_signed_in=")
    )
    assert "HttpOnly" not in hint
    assert "Path=/;" in hint or hint.endswith("Path=/")
    assert "salesluv_signed_in=1" in hint
    assert response.headers["cache-control"] == "no-store"
    assert not _login_attempts


def test_invalid_credentials_are_rejected_with_401(monkeypatch):
    client, _stub = _client(
        _member(),
        monkeypatch,
        token=_Response(400, {"error": "invalid_grant"}),
    )

    with client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_credentials"}
    assert not response.headers.get_list("set-cookie")


def test_verified_token_resolves_the_linked_member(monkeypatch):
    member = _member()
    client, _stub = _client(member, monkeypatch)

    with client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )
        me = client.get("/api/auth/me")

    assert login.status_code == 200
    assert me.status_code == 200
    assert me.json()["id"] == str(member.id)
    assert member.id == AUTH_USER_ID


def test_unlinked_or_inactive_member_is_forbidden(monkeypatch):
    # 비활성 구성원과 미연결 사용자는 모두 조회 조건에서 걸러져 결과가 없다.
    client, _stub = _client(None, monkeypatch)

    with client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )
        client.cookies.set("salesluv_access", access_token(), path="/api")
        me = client.get("/api/auth/me")

    assert login.status_code == 403
    assert login.json() == {"detail": "member_not_linked"}
    assert me.status_code == 403
    assert not login.headers.get_list("set-cookie")


def test_expired_access_token_recovers_after_refresh(monkeypatch):
    member = _member()
    client, _stub = _client(member, monkeypatch)

    with client:
        client.cookies.set("salesluv_access", access_token(expires_in=-10), path="/api")
        client.cookies.set("salesluv_refresh", secrets.token_urlsafe(24), path="/api/auth")

        expired = client.get("/api/auth/me")
        refreshed = client.post("/api/auth/refresh", headers={"Origin": ORIGIN})
        recovered = client.get("/api/auth/me")

    assert expired.status_code == 401
    assert refreshed.status_code == 200
    assert _cookie_names(refreshed) == SESSION_COOKIES
    assert recovered.status_code == 200
    assert recovered.json()["id"] == str(member.id)


def test_failed_refresh_clears_both_cookies(monkeypatch):
    client, _stub = _client(
        _member(),
        monkeypatch,
        token=_Response(400, {"error": "invalid_grant"}),
    )

    with client:
        client.cookies.set("salesluv_refresh", secrets.token_urlsafe(24), path="/api/auth")
        response = client.post("/api/auth/refresh", headers={"Origin": ORIGIN})

    assert response.status_code == 401
    assert _cookie_names(response) == SESSION_COOKIES
    assert _cookie_text(response).count("max-age=0") == 3


def test_refresh_without_cookie_does_not_call_supabase(monkeypatch):
    client, stub = _client(_member(), monkeypatch)

    with client:
        response = client.post("/api/auth/refresh", headers={"Origin": ORIGIN})

    assert response.status_code == 401
    assert response.json() == {"detail": "not_authenticated"}
    assert not stub.calls


def test_logout_clears_cookies_even_when_supabase_fails(monkeypatch):
    client, _stub = _client(
        _member(),
        monkeypatch,
        logout=httpx.ConnectError("supabase unreachable"),
    )

    with client:
        client.cookies.set("salesluv_access", access_token(), path="/api")
        response = client.post("/api/auth/logout", headers={"Origin": ORIGIN})

    assert response.status_code == 204
    assert response.content == b""
    assert _cookie_names(response) == SESSION_COOKIES
    assert _cookie_text(response).count("max-age=0") == 3


@pytest.mark.parametrize(
    "outcome",
    [_Response(503), _Response(500), httpx.ConnectError("supabase unreachable")],
    ids=["unavailable", "server_error", "network"],
)
def test_supabase_outage_becomes_503(outcome, monkeypatch):
    client, _stub = _client(_member(), monkeypatch, token=outcome)

    with client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "auth_unavailable"}


def test_missing_publishable_key_is_reported_as_configuration(monkeypatch):
    # 설정이 덜 된 것과 Supabase 장애는 같은 503 이지만 원인이 다르다.
    monkeypatch.setattr(settings, "supabase_publishable_key", SecretStr(""))
    client, stub = _client(_member(), monkeypatch)

    with client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )
        client.cookies.set("salesluv_access", access_token(), path="/api")
        me = client.get("/api/auth/me")

    assert login.status_code == 503
    assert login.json() == {"detail": "auth_not_configured"}
    assert me.status_code == 503
    assert me.json() == {"detail": "auth_not_configured"}
    # 설정이 없으면 Supabase 를 부르지도 않는다.
    assert not stub.calls


def test_supabase_rate_limit_is_passed_through(monkeypatch):
    client, _stub = _client(_member(), monkeypatch, token=_Response(429))

    with client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )

    assert response.status_code == 429
    assert response.json() == {"detail": "login_rate_limited"}


def test_protected_route_without_cookie_is_401(monkeypatch):
    client, _stub = _client(_member(), monkeypatch)

    with client:
        response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "not_authenticated"}


def test_mutation_requires_exact_allowed_origin(monkeypatch):
    client, _stub = _client(None, monkeypatch)

    with client:
        missing = client.post("/api/auth/login", json={"email": "a@b.c", "password": "x"})
        suffix = client.post(
            "/api/auth/login",
            headers={"Origin": f"{ORIGIN}.evil.test"},
            json={"email": "a@b.c", "password": "x"},
        )
        preflight = client.options(
            "/api/auth/login",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        )

    assert missing.status_code == 403
    assert suffix.status_code == 403
    assert preflight.status_code == 200


def test_login_attempts_are_rate_limited_per_ip(monkeypatch):
    client, _stub = _client(
        _member(),
        monkeypatch,
        token=_Response(400, {"error": "invalid_grant"}),
    )

    with client:
        for _ in range(settings.login_max_attempts):
            response = client.post(
                "/api/auth/login",
                headers={"Origin": ORIGIN},
                json={"email": "manager@salesluv.demo", "password": "wrong-password"},
            )
            assert response.status_code == 401

        limited = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": "wrong-password"},
        )

    assert limited.status_code == 429
    assert limited.json() == {"detail": "login_rate_limited"}
    assert int(limited.headers["retry-after"]) > 0


def test_changing_email_does_not_bypass_ip_rate_limit():
    for _ in range(settings.login_max_attempts):
        assert _reserve_login_attempt("same-ip") is None

    assert _reserve_login_attempt("same-ip") is not None


def test_validation_error_does_not_echo_password(monkeypatch):
    submitted_password = secrets.token_urlsafe(257)
    client, _stub = _client(None, monkeypatch)

    with client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": submitted_password},
        )

    assert response.status_code == 422
    assert submitted_password not in response.text
    assert all("input" not in error for error in response.json()["detail"])


def test_production_auth_settings_fail_closed(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="staging")
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            debug=True,
            cors_origins="https://salesluv.example",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            cors_origins="http://salesluv.example",
        )

    production = Settings(
        _env_file=None,
        app_env="production",
        debug=False,
        cors_origins="https://salesluv.example",
    )
    assert production.session_cookie_secure
