"""인증 API.

세션의 주인은 Supabase Auth 다. 백엔드는 자격증명을 대신 전달하고,
Supabase 가 발급한 토큰을 HttpOnly 쿠키로만 보관한다.
자체 토큰을 만들지 않으므로 만료·회전·폐기는 Supabase 가 관리한다.
"""

import math
import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentMember, DbSession, member_by_auth_user_id
from app.core.config import settings
from app.models.workspace import Member
from app.schemas.auth import LoginRequest, SessionRead
from app.services import supabase_auth
from app.services.supabase_auth import SupabaseSession

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE = "salesluv_access"
REFRESH_COOKIE = "salesluv_refresh"
# 세션이 있는지만 알리는 표시. 토큰이 아니라서 프론트가 읽을 수 있어야 한다.
#
# 토큰 쿠키는 HttpOnly 라 브라우저 스크립트가 존재조차 확인할 수 없다. 그래서
# 로그인한 적 없는 방문자도 앱이 뜰 때마다 /auth/me 를 불러야 했다. 이 표시를
# 토큰과 같은 응답에서 함께 설정하고 함께 지우면 둘의 상태가 어긋나지 않는다.
SIGNED_IN_COOKIE = "salesluv_signed_in"
# refresh 쿠키는 갱신 경로에서만 필요하다. 일반 API 요청에는 실려 나가지 않는다.
ACCESS_COOKIE_PATH = "/api"
REFRESH_COOKIE_PATH = "/api/auth"
# 표시는 어느 화면에서든 읽어야 하므로 경로를 좁히지 않는다.
SIGNED_IN_COOKIE_PATH = "/"

# ponytail: 단일 프로세스용 고정 구간 제한기. 다중 worker 배포 시 공유 저장소로 교체한다.
# 계정 단위 버킷은 두지 않는다. Supabase 쿼터를 소진시키는 무차별 시도만 IP 로 막는다.
_login_attempts: dict[str, tuple[int, float]] = {}
_max_login_buckets = 10_000


def _reserve_login_attempt(client_host: str) -> int | None:
    now = time.monotonic()
    expired_keys = [
        key
        for key, (_, started_at) in _login_attempts.items()
        if now - started_at >= settings.login_window_seconds
    ]
    for key in expired_keys:
        _login_attempts.pop(key, None)

    count, started_at = _login_attempts.get(client_host, (0, now))
    if count >= settings.login_max_attempts:
        return max(1, math.ceil(settings.login_window_seconds - (now - started_at)))
    if client_host not in _login_attempts and len(_login_attempts) + 1 > _max_login_buckets:
        return settings.login_window_seconds

    _login_attempts[client_host] = (count + 1, started_at)
    return None


def _release_login_attempt(client_host: str) -> None:
    attempt = _login_attempts.get(client_host)
    if attempt is None:
        return
    count, started_at = attempt
    if count == 1:
        _login_attempts.pop(client_host)
    else:
        _login_attempts[client_host] = (count - 1, started_at)


def _set_session_cookies(response: Response, session: SupabaseSession) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=session.access_token,
        max_age=session.expires_in,
        path=ACCESS_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    # 갱신할 때마다 다시 내려 미사용 기간만 만료로 이어지게 한다.
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=session.refresh_token,
        max_age=settings.refresh_cookie_max_age_seconds,
        path=REFRESH_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    # refresh 쿠키와 수명을 맞춘다. 세션이 살아 있는 동안에만 표시가 남는다.
    response.set_cookie(
        key=SIGNED_IN_COOKIE,
        value="1",
        max_age=settings.refresh_cookie_max_age_seconds,
        path=SIGNED_IN_COOKIE_PATH,
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_session_cookies(response: Response) -> None:
    for key, path, httponly in (
        (ACCESS_COOKIE, ACCESS_COOKIE_PATH, True),
        (REFRESH_COOKIE, REFRESH_COOKIE_PATH, True),
        (SIGNED_IN_COOKIE, SIGNED_IN_COOKIE_PATH, False),
    ):
        response.delete_cookie(
            key=key,
            path=path,
            secure=settings.session_cookie_secure,
            httponly=httponly,
            samesite="lax",
        )
    response.headers["Cache-Control"] = "no-store"


def auth_http_error(error: supabase_auth.AuthError) -> HTTPException:
    """Supabase 오류를 응답 코드로 옮긴다. 토큰과 키는 응답에 넣지 않는다."""
    if isinstance(error, supabase_auth.InvalidCredentials):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        )
    if isinstance(error, supabase_auth.AuthRateLimited):
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="login_rate_limited",
        )
    if isinstance(error, supabase_auth.AuthNotConfigured):
        # 서버가 덜 준비된 것이지 Supabase 가 죽은 것이 아니다. 원인을 구분해 둔다.
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth_not_configured",
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="auth_unavailable",
    )


@router.post("/login", response_model=SessionRead)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> Member:
    client_host = request.client.host if request.client else "unknown"
    retry_after = _reserve_login_attempt(client_host)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="login_rate_limited",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        session = await supabase_auth.password_grant(
            email=payload.email,
            password=payload.password,
        )
        auth_user_id = await supabase_auth.verify_access_token(session.access_token)
    except supabase_auth.AuthError as error:
        raise auth_http_error(error) from error
    except BaseException:
        _release_login_attempt(client_host)
        raise

    member = await member_by_auth_user_id(db, auth_user_id)
    if member is None:
        # Supabase 계정은 있지만 이 워크스페이스의 구성원이 아니다.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="member_not_linked")

    _release_login_attempt(client_host)
    _set_session_cookies(response, session)
    return member


def _rejected(status_code: int, detail: str) -> JSONResponse:
    """쿠키를 지우면서 실패를 알린다.

    HTTPException 을 올리면 여기서 만든 응답이 버려져 Set-Cookie 가 사라진다.
    그래서 갱신 실패는 예외 대신 응답으로 돌려준다.
    """
    rejection = JSONResponse(status_code=status_code, content={"detail": detail})
    clear_session_cookies(rejection)
    return rejection


@router.post("/refresh", response_model=SessionRead)
async def refresh(request: Request, response: Response, db: DbSession) -> Member | JSONResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE, "")
    if not refresh_token:
        return _rejected(status.HTTP_401_UNAUTHORIZED, "not_authenticated")

    try:
        session = await supabase_auth.refresh_grant(refresh_token=refresh_token)
        auth_user_id = await supabase_auth.verify_access_token(session.access_token)
    except supabase_auth.AuthError as error:
        http_error = auth_http_error(error)
        # 갱신할 수 없는 토큰은 남겨둘 이유가 없다. 다만 Supabase 장애로는 지우지 않는다.
        if http_error.status_code == status.HTTP_401_UNAUTHORIZED:
            return _rejected(http_error.status_code, "invalid_credentials")
        raise http_error from error

    member = await member_by_auth_user_id(db, auth_user_id)
    if member is None:
        return _rejected(status.HTTP_403_FORBIDDEN, "member_not_linked")

    _set_session_cookies(response, session)
    return member


@router.get("/me", response_model=SessionRead)
async def me(member: CurrentMember, response: Response) -> Member:
    response.headers["Cache-Control"] = "no-store"
    return member


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    access_token = request.cookies.get(ACCESS_COOKIE, "")
    if access_token:
        try:
            await supabase_auth.sign_out(access_token=access_token)
        except supabase_auth.AuthError:
            # Supabase 를 끊지 못해도 이 브라우저의 쿠키는 반드시 지운다.
            pass
    clear_session_cookies(response)
