"""Discord 로 나가는 유일한 경계.

계정 요청을 DB 에 쌓지 않고 팀 채널로 바로 보낸다. 그 채널이 곧 대기열이라
전송이 실패하면 요청 자체가 사라진다. 그래서 실패를 삼키지 않고 호출부로 올린다.

웹훅 URL 과 요청자 이메일은 응답에도 로그에도 남기지 않는다.
"""

import logging
from datetime import UTC, datetime

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 파란 계열. 앱의 --blue(#007aff) 를 십진수로 옮긴 값이다.
_EMBED_COLOR = 0x007AFF


class DiscordError(Exception):
    """Discord 로 보내지 못했다. 메시지에 비밀값을 담지 않는다."""


class DiscordNotConfigured(DiscordError):
    """DISCORD_WEBHOOK_URL 이 비어 있다."""


async def send_account_request(*, email: str) -> None:
    """계정을 받고 싶다는 요청 하나를 팀 채널에 알린다."""
    if not settings.discord_configured:
        raise DiscordNotConfigured("signup_not_configured")

    payload = {
        "embeds": [
            {
                "title": "📬 새 계정 요청",
                "description": "SalesLuv 로그인 화면에서 계정 요청이 들어왔습니다.",
                "color": _EMBED_COLOR,
                "fields": [{"name": "이메일", "value": email, "inline": False}],
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=settings.discord_timeout_seconds) as client:
            response = await client.post(
                settings.discord_webhook_url.get_secret_value(),
                json=payload,
            )
    except httpx.HTTPError as error:
        # 예외 타입 이름만 남긴다. 원문에는 웹훅 URL 이 들어 있다.
        raise DiscordError(f"signup_delivery_failed:{type(error).__name__}") from error

    if response.status_code >= 400:
        logger.warning("discord webhook rejected account request: status=%s", response.status_code)
        raise DiscordError(f"signup_delivery_failed:{response.status_code}")
