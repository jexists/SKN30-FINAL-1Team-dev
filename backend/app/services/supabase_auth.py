"""Supabase Auth 호출 경계.

password login, 세션 갱신, 로그아웃, access token 검증 네 가지만 둔다.
인증 공급자를 바꾸면 이 모듈만 교체한다.

publishable 키는 Auth REST 호출에만 쓰고 브라우저로 보내지 않는다.
비밀번호와 토큰은 예외 메시지나 로그에 남기지 않는다.
"""

import time
from dataclasses import dataclass
from uuid import UUID

import httpx
import jwt
from jwt import PyJWKSet

from app.core.config import settings

# Supabase access token 의 고정 audience.
_AUDIENCE = "authenticated"
# 비대칭 서명만 받는다. 대칭키(HS*)는 검증 키를 서버가 들고 있어야 하므로 쓰지 않는다.
_ALGORITHMS = ("ES256", "RS256")
_JWKS_TTL_SECONDS = 600.0
_HTTP_TIMEOUT = 10.0


class AuthError(Exception):
    """인증 호출이 실패했다. 메시지에 토큰이나 키를 담지 않는다."""


class AuthNotConfigured(AuthError):
    """publishable 키나 프로젝트 주소가 없다."""


class AuthUnavailable(AuthError):
    """Supabase 에 닿지 못했거나 Supabase 가 5xx 를 냈다. 503 으로 바꾼다."""


class AuthRateLimited(AuthError):
    """Supabase 가 429 를 냈다. 그대로 429 로 바꾼다."""


class InvalidCredentials(AuthError):
    """자격증명이 틀렸거나 refresh token 이 더 이상 유효하지 않다. 401 로 바꾼다."""


@dataclass(frozen=True, slots=True)
class SupabaseSession:
    """Supabase 가 돌려준 세션. 쿠키로만 나가고 응답 본문에는 넣지 않는다."""

    access_token: str
    refresh_token: str
    expires_in: int


def _endpoint(path: str) -> str:
    return f"{settings.supabase_project_url}/auth/v1/{path}"


def _headers() -> dict[str, str]:
    key = settings.supabase_publishable_key.get_secret_value()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _require_config() -> None:
    if not settings.auth_configured:
        raise AuthNotConfigured("auth_not_configured")


def _session_from(payload: object) -> SupabaseSession:
    if not isinstance(payload, dict):
        raise AuthUnavailable("auth_response_invalid")
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if not isinstance(access_token, str) or not access_token:
        raise AuthUnavailable("auth_response_invalid")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AuthUnavailable("auth_response_invalid")
    if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in <= 0:
        raise AuthUnavailable("auth_response_invalid")
    return SupabaseSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


async def _token_grant(grant_type: str, body: dict[str, str]) -> SupabaseSession:
    """`/token` 은 grant_type 만 다르고 오류 처리가 같아 한 곳에서 다룬다."""
    _require_config()
    url = _endpoint(f"token?grant_type={grant_type}")
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(url, headers=_headers(), json=body)
    except httpx.HTTPError as error:
        raise AuthUnavailable(f"auth_request_failed:{type(error).__name__}") from error

    if response.status_code == 429:
        raise AuthRateLimited("auth_rate_limited")
    if response.status_code >= 500:
        raise AuthUnavailable(f"auth_upstream_failed:{response.status_code}")
    if response.status_code >= 400:
        # 400/401/403 은 모두 자격증명 문제로 모은다. 계정 존재 여부를 구분하지 않는다.
        raise InvalidCredentials("invalid_credentials")

    try:
        payload = response.json()
    except ValueError as error:
        raise AuthUnavailable("auth_response_invalid") from error
    return _session_from(payload)


async def password_grant(*, email: str, password: str) -> SupabaseSession:
    return await _token_grant("password", {"email": email, "password": password})


async def refresh_grant(*, refresh_token: str) -> SupabaseSession:
    return await _token_grant("refresh_token", {"refresh_token": refresh_token})


async def sign_out(*, access_token: str) -> None:
    """Supabase 세션을 끊는다. 실패해도 호출부는 로컬 쿠키를 지워야 한다."""
    _require_config()
    url = _endpoint("logout")
    headers = {**_headers(), "Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(url, headers=headers)
    except httpx.HTTPError as error:
        raise AuthUnavailable(f"auth_request_failed:{type(error).__name__}") from error
    if response.status_code >= 500:
        raise AuthUnavailable(f"auth_upstream_failed:{response.status_code}")


# JWKS 는 자주 바뀌지 않는다. TTL 안에서는 다시 받지 않아 요청마다 네트워크를 타지 않는다.
_jwks_cache: tuple[PyJWKSet, float] | None = None


def reset_jwks_cache() -> None:
    """테스트와 키 교체 후 강제 갱신용."""
    global _jwks_cache
    _jwks_cache = None


async def _jwks(*, now: float | None = None) -> PyJWKSet:
    global _jwks_cache
    current = time.monotonic() if now is None else now
    if _jwks_cache is not None and current - _jwks_cache[1] < _JWKS_TTL_SECONDS:
        return _jwks_cache[0]

    _require_config()
    url = _endpoint(".well-known/jwks.json")
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.get(url, headers=_headers())
    except httpx.HTTPError as error:
        raise AuthUnavailable(f"auth_request_failed:{type(error).__name__}") from error
    if response.status_code >= 400:
        raise AuthUnavailable(f"auth_jwks_failed:{response.status_code}")

    try:
        keys = PyJWKSet.from_dict(response.json())
    except (ValueError, KeyError, TypeError, jwt.PyJWKSetError) as error:
        # 프로젝트가 아직 레거시 대칭키를 쓰면 목록이 비어 온다.
        raise AuthUnavailable("auth_jwks_invalid") from error

    _jwks_cache = (keys, current)
    return keys


async def verify_access_token(token: str) -> UUID:
    """서명을 로컬에서 검증하고 Supabase 사용자 UUID 를 돌려준다.

    요청마다 Supabase 를 부르지 않으므로 Auth 장애가 조회 API 를 막지 않는다.
    대신 정지·삭제된 사용자는 access token 이 만료될 때까지 통과하므로,
    호출부가 `member.active` 로 한 번 더 거른다.
    """
    if not isinstance(token, str) or not token:
        raise InvalidCredentials("invalid_token")

    keys = await _jwks()
    try:
        header = jwt.get_unverified_header(token)
        key = keys[header["kid"]]
        payload = jwt.decode(
            token,
            key=key,
            algorithms=list(_ALGORITHMS),
            audience=_AUDIENCE,
            options={"require": ["exp", "sub", "aud"]},
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise InvalidCredentials("invalid_token") from error

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise InvalidCredentials("invalid_token")
    try:
        return UUID(subject)
    except ValueError as error:
        raise InvalidCredentials("invalid_token") from error
