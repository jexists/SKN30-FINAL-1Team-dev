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

    def __init__(
        self,
        *,
        token: _Response | Exception,
        logout: _Response | Exception,
        jwks: list[object] | None = None,
    ):
        self.token = token
        self.logout = logout
        # 키 교체를 흉내내려면 JWKS 응답이 호출마다 달라야 한다. 비우면 늘 같은 키다.
        self.jwks = list(jwks or [])
        self.calls: list[tuple[str, str]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url: str, **_kwargs) -> _Response:
        self.calls.append(("GET", url))
        return _Response(200, self.jwks.pop(0) if self.jwks else _JWKS)

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
    jwks: list[object] | None = None,
) -> tuple[TestClient, _SupabaseStub]:
    """member 는 DB 조회 결과, token/logout 은 Supabase 응답을 정한다."""
    stub = _SupabaseStub(
        token=_Response(200, session_payload()) if token is None else token,
        logout=_Response(204) if logout is None else logout,
        jwks=jwks,
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
        # ADMIN_USER_IDS 가 비어 있으므로 어드민이 아니다.
        "is_admin": False,
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


def test_rotated_signing_key_is_fetched_without_waiting_for_the_cache(monkeypatch):
    """Supabase 가 서명 키를 바꿔도 로그인은 즉시 이어져야 한다.

    예전에는 캐시에 없는 kid 를 만나면 그대로 실패했다. JWKS 캐시 TTL 이 10분이라
    키가 교체되면 그동안 모든 로그인이 401 invalid_credentials 로 막혔고,
    캐시가 만료되면 아무것도 하지 않아도 저절로 풀렸다.
    """
    rotated_key = ec.generate_private_key(ec.SECP256R1())
    rotated_kid = "rotated-signing-key"
    rotated_jwks = {
        "keys": [
            {
                **json.loads(jwt.algorithms.ECAlgorithm.to_jwk(rotated_key.public_key())),
                "kid": rotated_kid,
                "alg": "ES256",
                "use": "sig",
            }
        ]
    }
    rotated_token = jwt.encode(
        {"sub": str(AUTH_USER_ID), "aud": "authenticated", "exp": int(time.time()) + 3_600},
        rotated_key,
        algorithm="ES256",
        headers={"kid": rotated_kid},
    )

    # 옛 키만 담긴 캐시가 아직 살아 있는 상태에서 시작한다. TTL 이 지나 버리면
    # 평범한 재조회가 새 키를 물어와, 정작 확인하려는 경로를 타지 않는다.
    monkeypatch.setattr(
        supabase_auth, "_jwks_cache", (jwt.PyJWKSet.from_dict(_JWKS), time.monotonic())
    )
    monkeypatch.setattr(supabase_auth, "_JWKS_MIN_REFETCH_SECONDS", 0.0)

    client, stub = _client(
        _member(),
        monkeypatch,
        token=_Response(
            200,
            {
                "access_token": rotated_token,
                "refresh_token": secrets.token_urlsafe(24),
                "expires_in": 3_600,
            },
        ),
        jwks=[rotated_jwks],
    )

    with client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )

    assert response.status_code == 200
    # 캐시가 아직 유효했는데도 JWKS 를 다시 받아 새 키를 찾았다.
    assert [call for call in stub.calls if call[0] == "GET"]


def test_unknown_signing_key_is_a_server_problem_not_a_wrong_password(monkeypatch):
    """다시 받아온 JWKS 에도 없는 키라면 비밀번호 문제가 아니다.

    401 로 알리면 사용자는 원인이 비밀번호에 있는 줄 알고 같은 값을 계속 다시 친다.
    """
    stranger_key = ec.generate_private_key(ec.SECP256R1())
    stranger_token = jwt.encode(
        {"sub": str(AUTH_USER_ID), "aud": "authenticated", "exp": int(time.time()) + 3_600},
        stranger_key,
        algorithm="ES256",
        headers={"kid": "unknown-signing-key"},
    )

    client, _stub = _client(
        _member(),
        monkeypatch,
        token=_Response(
            200,
            {
                "access_token": stranger_token,
                "refresh_token": secrets.token_urlsafe(24),
                "expires_in": 3_600,
            },
        ),
    )

    with client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "manager@salesluv.demo", "password": secrets.token_urlsafe(16)},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "auth_unavailable"}
    assert not response.headers.get_list("set-cookie")
    # 서버 잘못으로 로그인 시도 슬롯을 채우지 않는다.
    assert not _login_attempts


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
        # 시계 오차 허용치보다 확실히 오래 지난 토큰이어야 만료로 걸린다.
        client.cookies.set("salesluv_access", access_token(expires_in=-600), path="/api")
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


def test_set_password_forwards_the_invite_token_and_keeps_the_password_quiet(monkeypatch):
    """초대 링크로 들어온 사람이 로그인 없이 비밀번호를 정한다."""
    calls: list[tuple[str, str]] = []

    async def fake_update_password(*, access_token: str, password: str) -> None:
        calls.append((access_token, password))

    monkeypatch.setattr(supabase_auth, "update_password", fake_update_password)
    client, _stub = _client(None, monkeypatch)
    token = access_token()
    chosen = secrets.token_urlsafe(16)

    with client:
        response = client.post(
            "/api/auth/set-password",
            headers={"Origin": ORIGIN},
            json={"access_token": token, "password": chosen},
        )

    assert response.status_code == 204
    assert calls == [(token, chosen)]
    # 쿠키를 굽지 않는다. 새 비밀번호는 로그인 화면에서 확인시킨다.
    assert _cookie_names(response) == set()


def test_set_password_rejects_a_short_password_without_echoing_it(monkeypatch):
    submitted = "1234567"
    client, _stub = _client(None, monkeypatch)

    with client:
        response = client.post(
            "/api/auth/set-password",
            headers={"Origin": ORIGIN},
            json={"access_token": access_token(), "password": submitted},
        )

    assert response.status_code == 422
    assert submitted not in response.text


def test_set_password_with_a_dead_link_is_401(monkeypatch):
    async def fake_update_password(**_kwargs) -> None:
        raise supabase_auth.InvalidCredentials("invalid_token")

    monkeypatch.setattr(supabase_auth, "update_password", fake_update_password)
    client, _stub = _client(None, monkeypatch)

    with client:
        response = client.post(
            "/api/auth/set-password",
            headers={"Origin": ORIGIN},
            json={"access_token": access_token(), "password": secrets.token_urlsafe(16)},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


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
