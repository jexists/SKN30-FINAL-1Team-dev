"""Supabase Auth 호출 경계.

password login, 세션 갱신, 로그아웃, access token 검증에 더해
어드민 계정 발급이 쓰는 초대·삭제·비밀번호 변경까지 둔다.
인증 공급자를 바꾸면 이 모듈만 교체한다.

publishable 키는 Auth REST 호출에만 쓰고 브라우저로 보내지 않는다.
secret 키는 사용자를 만들고 지울 수 있으므로 admin 경로에서만 쓴다.
비밀번호와 토큰은 예외 메시지나 로그에 남기지 않는다.
"""

import logging
import time
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

import httpx
import jwt
from jwt import PyJWK, PyJWKSet

from app.core.config import settings

# 실패 원인을 서버 쪽에 남긴다. 응답은 원인을 구분하지 않으므로 여기가 유일한 단서다.
# 비밀번호·토큰·이메일은 절대 싣지 않는다.
logger = logging.getLogger(__name__)

# Supabase access token 의 고정 audience.
_AUDIENCE = "authenticated"
# 비대칭 서명만 받는다. 대칭키(HS*)는 검증 키를 서버가 들고 있어야 하므로 쓰지 않는다.
_ALGORITHMS = ("ES256", "RS256")
_JWKS_TTL_SECONDS = 600.0
# 모르는 kid 를 만났을 때 JWKS 를 다시 받는 최소 간격. 아무 kid 나 담은 토큰으로
# 요청마다 JWKS 를 때리지 못하게 막는다.
_JWKS_MIN_REFETCH_SECONDS = 30.0
# 로컬 시계가 조금 밀려도 방금 받은 토큰을 거절하지 않는다.
_CLOCK_SKEW_LEEWAY_SECONDS = 30.0
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


class EmailAlreadyExists(AuthError):
    """그 이메일의 Supabase 사용자가 이미 있다. 409 로 바꾼다."""


class WeakPassword(AuthError):
    """Supabase 의 비밀번호 정책에 걸렸다. 422 로 바꾼다. 본문은 옮기지 않는다."""


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


def _admin_headers() -> dict[str, str]:
    """사용자를 만들고 지울 수 있는 키다. 이 모듈의 admin 함수 밖으로 새어 나가면 안 된다."""
    key = settings.supabase_secret_key.get_secret_value()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _require_config() -> None:
    if not settings.auth_configured:
        raise AuthNotConfigured("auth_not_configured")


def _require_admin_config() -> None:
    if not settings.admin_configured:
        raise AuthNotConfigured("admin_not_configured")


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


def _error_code(response: httpx.Response) -> str:
    """로그에 남길 Supabase 오류 코드. 본문의 나머지는 옮기지 않는다.

    본문 전체를 남기면 요청에 실린 이메일이 메시지에 섞여 나올 수 있다.
    """
    try:
        payload = response.json()
    except ValueError:
        return "unparseable"
    if not isinstance(payload, dict):
        return "unparseable"
    code = payload.get("error_code") or payload.get("error")
    return code if isinstance(code, str) else "unknown"


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
        # 응답에서 지운 구분은 로그에만 남긴다. 이게 없으면 비밀번호 오류와
        # email_not_confirmed 같은 설정 문제를 서버 운영자도 구분할 수 없다.
        logger.warning(
            "supabase token grant rejected: grant_type=%s status=%s error_code=%s",
            grant_type,
            response.status_code,
            _error_code(response),
        )
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


async def invite_user(*, email: str, redirect_to: str) -> UUID:
    """사용자를 만들고 초대 메일을 보낸다. 두 가지가 한 호출로 끝난다.

    비밀번호는 여기서 정하지 않는다. 받는 사람이 메일 링크에서 직접 정하므로
    임시 비밀번호가 어디에도 남지 않는다.
    """
    _require_admin_config()
    url = _endpoint(f"invite?redirect_to={quote(redirect_to, safe='')}")
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(url, headers=_admin_headers(), json={"email": email})
    except httpx.HTTPError as error:
        raise AuthUnavailable(f"auth_request_failed:{type(error).__name__}") from error

    if response.status_code in (409, 422):
        raise EmailAlreadyExists("email_already_exists")
    if response.status_code == 429:
        raise AuthRateLimited("auth_rate_limited")
    if response.status_code >= 500:
        raise AuthUnavailable(f"auth_upstream_failed:{response.status_code}")
    if response.status_code >= 400:
        raise AuthUnavailable(f"auth_invite_failed:{response.status_code}")

    try:
        user_id = response.json()["id"]
    except (ValueError, KeyError, TypeError) as error:
        raise AuthUnavailable("auth_response_invalid") from error
    try:
        return UUID(user_id)
    except (ValueError, AttributeError, TypeError) as error:
        raise AuthUnavailable("auth_response_invalid") from error


async def delete_user(*, user_id: UUID) -> None:
    """초대 뒤 DB 기록이 실패했을 때 되돌리기 위해 쓴다. 그 밖에는 부르지 않는다."""
    _require_admin_config()
    url = _endpoint(f"admin/users/{user_id}")
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.delete(url, headers=_admin_headers())
    except httpx.HTTPError as error:
        raise AuthUnavailable(f"auth_request_failed:{type(error).__name__}") from error
    # 이미 없으면 되돌릴 것도 없다. 404 는 성공으로 본다.
    if response.status_code >= 400 and response.status_code != 404:
        raise AuthUnavailable(f"auth_delete_failed:{response.status_code}")


async def update_password(*, access_token: str, password: str) -> None:
    """초대·복구 링크로 받은 토큰을 자격증명 삼아 비밀번호를 정한다.

    publishable 키를 쓴다. 이 호출은 토큰 주인 자신만 바꿀 수 있으므로
    사용자를 임의로 건드릴 수 있는 secret 키가 필요하지 않다.
    """
    _require_config()
    if not isinstance(access_token, str) or not access_token:
        raise InvalidCredentials("invalid_token")

    url = _endpoint("user")
    headers = {**_headers(), "Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.put(url, headers=headers, json={"password": password})
    except httpx.HTTPError as error:
        raise AuthUnavailable(f"auth_request_failed:{type(error).__name__}") from error

    if response.status_code in (401, 403):
        raise InvalidCredentials("invalid_token")
    if response.status_code == 429:
        raise AuthRateLimited("auth_rate_limited")
    if response.status_code >= 500:
        raise AuthUnavailable(f"auth_upstream_failed:{response.status_code}")
    if response.status_code >= 400:
        # 비밀번호 정책 위반 등. 본문에 비밀번호가 섞일 수 있으므로 코드만 남긴다.
        raise WeakPassword("password_rejected")


# JWKS 는 자주 바뀌지 않는다. TTL 안에서는 다시 받지 않아 요청마다 네트워크를 타지 않는다.
_jwks_cache: tuple[PyJWKSet, float] | None = None


def reset_jwks_cache() -> None:
    """테스트와 키 교체 후 강제 갱신용."""
    global _jwks_cache
    _jwks_cache = None


async def _jwks(*, now: float | None = None, force: bool = False) -> PyJWKSet:
    """`force` 는 TTL 을 무시하지만 최소 재조회 간격은 지킨다."""
    global _jwks_cache
    current = time.monotonic() if now is None else now
    age_limit = _JWKS_MIN_REFETCH_SECONDS if force else _JWKS_TTL_SECONDS
    if _jwks_cache is not None and current - _jwks_cache[1] < age_limit:
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


async def _signing_key(kid: str) -> PyJWK:
    """캐시에 없는 kid 는 키 교체 신호다. TTL 이 끝나기를 기다리지 않고 한 번 다시 받는다.

    이걸 하지 않으면 Supabase 가 서명 키를 바꾼 뒤 캐시가 늙어 죽을 때까지
    (최대 `_JWKS_TTL_SECONDS`) 모든 로그인이 실패한다.
    """
    keys = await _jwks()
    try:
        return keys[kid]
    except KeyError:
        pass

    # 최소 간격이 지나지 않았거나 방금 받아온 목록이면 같은 객체가 돌아온다.
    # 그때는 다시 볼 것이 없다.
    refreshed = await _jwks(force=True)
    if refreshed is not keys:
        try:
            return refreshed[kid]
        except KeyError:
            pass
    logger.warning("access token signed by an unknown key: kid=%s", kid)
    raise InvalidCredentials("unknown_signing_key")


async def verify_access_token(token: str) -> UUID:
    """서명을 로컬에서 검증하고 Supabase 사용자 UUID(= public.member.id)를 돌려준다.

    요청마다 Supabase 를 부르지 않으므로 Auth 장애가 조회 API 를 막지 않는다.
    대신 정지·삭제된 사용자는 access token 이 만료될 때까지 통과하므로,
    호출부가 `member.active` 로 한 번 더 거른다.
    """
    if not isinstance(token, str) or not token:
        raise InvalidCredentials("invalid_token")

    try:
        kid = jwt.get_unverified_header(token)["kid"]
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise InvalidCredentials("invalid_token") from error

    key = await _signing_key(kid)
    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=list(_ALGORITHMS),
            audience=_AUDIENCE,
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
            options={"require": ["exp", "sub", "aud"]},
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        # 서명·만료·audience 중 무엇이 틀렸는지는 응답에 남지 않는다. 여기에만 남긴다.
        logger.warning(
            "access token verification failed: kid=%s reason=%s", kid, type(error).__name__
        )
        raise InvalidCredentials("invalid_token") from error

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise InvalidCredentials("invalid_token")
    try:
        return UUID(subject)
    except ValueError as error:
        raise InvalidCredentials("invalid_token") from error
