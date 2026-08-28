"""계정 요청 API.

관리자가 계정을 발급하는 제품이라 스스로 가입할 수는 없다. 대신 연락할
이메일만 받아 팀 Discord 채널로 넘긴다. 요청을 DB 에 쌓지 않으므로
Discord 로 보내지 못하면 요청도 실패로 알린다. 조용히 삼키면 사라진다.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.rate_limit import AttemptLimiter
from app.schemas.signup import AccountRequest
from app.services import discord

router = APIRouter(prefix="/signup", tags=["signup"])

# 로그인보다 훨씬 드문 요청이라 창을 넓게 잡는다. 같은 사람이 10분에 3번이면 충분하다.
_MAX_REQUESTS = 3
_WINDOW_SECONDS = 600
_request_limiter = AttemptLimiter()


@router.post("/request", status_code=status.HTTP_204_NO_CONTENT)
async def request_account(payload: AccountRequest, request: Request, response: Response) -> None:
    """계정을 받고 싶은 사람이 이메일만 남긴다. 로그인 상태를 요구하지 않는다."""
    client_host = request.client.host if request.client else "unknown"
    retry_after = _request_limiter.reserve(
        client_host,
        max_attempts=_MAX_REQUESTS,
        window_seconds=_WINDOW_SECONDS,
    )
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="signup_rate_limited",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        await discord.send_account_request(email=payload.email)
    except discord.DiscordNotConfigured as error:
        # 서버가 덜 준비된 것이지 Discord 가 죽은 것이 아니다. 원인을 구분해 둔다.
        _request_limiter.release(client_host)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="signup_not_configured",
        ) from error
    except discord.DiscordError as error:
        # 보내지 못한 요청으로 시도 횟수를 채우면 다시 시도할 기회까지 잃는다.
        _request_limiter.release(client_host)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="signup_unavailable",
        ) from error

    response.headers["Cache-Control"] = "no-store"
