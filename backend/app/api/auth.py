import asyncio
import math
import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession
from app.core.config import settings
from app.core.security import (
    create_session_token,
    dummy_password_hash,
    verify_password,
)
from app.models.workspace import Member
from app.schemas.auth import LoginRequest, SessionRead

router = APIRouter(prefix="/auth", tags=["auth"])

# ponytail: 단일 프로세스용 고정 구간 제한기. 다중 worker 배포 시 공유 저장소로 교체한다.
_login_attempts: dict[tuple[str, str], tuple[int, float]] = {}
_max_login_buckets = 10_000
# ponytail: scrypt 메모리를 프로세스당 약 64MiB로 제한한다. 부하가 커지면 인증 worker를 분리한다.
_scrypt_slots = asyncio.Semaphore(2)
_dummy_password_hash = dummy_password_hash()


def _reserve_login_attempt(client_host: str, login_id: str) -> int | None:
    now = time.monotonic()
    expired_keys = [
        key
        for key, (_, started_at) in _login_attempts.items()
        if now - started_at >= settings.login_window_seconds
    ]
    for key in expired_keys:
        _login_attempts.pop(key, None)

    keys = ((client_host, ""), (client_host, login_id))
    retry_after = 0
    for key in keys:
        count, started_at = _login_attempts.get(key, (0, now))
        if count >= settings.login_max_attempts:
            retry_after = max(
                retry_after,
                math.ceil(settings.login_window_seconds - (now - started_at)),
            )

    if retry_after:
        return max(1, retry_after)
    new_bucket_count = sum(key not in _login_attempts for key in keys)
    if len(_login_attempts) + new_bucket_count > _max_login_buckets:
        return settings.login_window_seconds
    for key in keys:
        count, started_at = _login_attempts.get(key, (0, now))
        _login_attempts[key] = (count + 1, started_at)
    return None


def _release_login_attempt(client_host: str, login_id: str) -> None:
    for key in ((client_host, ""), (client_host, login_id)):
        attempt = _login_attempts.get(key)
        if attempt is None:
            continue
        count, started_at = attempt
        if count == 1:
            _login_attempts.pop(key)
        else:
            _login_attempts[key] = (count - 1, started_at)


@router.post("/login", response_model=SessionRead)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> Member:
    client_host = request.client.host if request.client else "unknown"
    retry_after = _reserve_login_attempt(client_host, payload.login_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="login_rate_limited",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = await db.execute(select(Member).where(Member.login_id == payload.login_id))
        member = result.scalar_one_or_none()
        password_hash = member.password_hash if member is not None else _dummy_password_hash
        async with _scrypt_slots:
            password_matches = await asyncio.to_thread(
                verify_password,
                payload.password,
                password_hash,
            )
    except BaseException:
        _release_login_attempt(client_host, payload.login_id)
        raise

    if (
        member is None
        or not password_matches
        or not member.active
        or member.role_code not in {"member", "manager"}
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_credentials",
        )

    _release_login_attempt(client_host, payload.login_id)
    token = create_session_token(
        member.id,
        settings.session_secret.get_secret_value(),
        settings.session_ttl_seconds,
    )
    response.set_cookie(
        key="salesluv_session",
        value=token,
        max_age=settings.session_ttl_seconds,
        path="/api",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return member


@router.get("/me", response_model=SessionRead)
async def me(member: CurrentMember, response: Response) -> Member:
    response.headers["Cache-Control"] = "no-store"
    return member


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(
        key="salesluv_session",
        path="/api",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
