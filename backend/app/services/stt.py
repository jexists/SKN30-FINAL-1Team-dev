"""OpenAI 미팅 음성 전사 경계.

라우터는 이 모듈의 ``transcribe``만 호출한다. 추후 로컬 STT를 도입해도
라우터와 보고서 흐름은 바꾸지 않고 이 경계 안의 구현만 교체한다.
"""

from typing import Any

import httpx

from app.core.config import settings

_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"
_CONTEXT = "한국어 영업 미팅입니다. 고객, 계약, 견적, 일정, 후속 조치를 정확히 전사하세요."
_MAX_TRANSCRIPT_CHARS = 50_000


class STTError(Exception):
    """전사 공급자 호출이 실패했다. 메시지에 키·음성·전사문을 담지 않는다."""


class STTNotConfigured(STTError):
    """STT_API_KEY 또는 STT_MODEL이 설정되지 않았다."""


async def transcribe(*, file_name: str, media_type: str, content: bytes) -> str:
    """완성된 음성 파일을 전사해 텍스트만 반환한다."""
    if not settings.stt_configured:
        raise STTNotConfigured("stt_not_configured")

    try:
        async with httpx.AsyncClient(timeout=settings.stt_timeout_seconds) as client:
            response = await client.post(
                _TRANSCRIPTIONS_URL,
                headers={"Authorization": f"Bearer {settings.stt_api_key.get_secret_value()}"},
                data={
                    "model": settings.stt_model,
                    "language": "ko",
                    "prompt": _CONTEXT,
                },
                files={"file": (file_name, content, media_type)},
            )
    except httpx.HTTPError as error:
        raise STTError("stt_request_failed") from error

    if response.status_code >= 400:
        raise STTError("stt_provider_error")

    try:
        payload: Any = response.json()
    except ValueError as error:
        raise STTError("stt_response_not_json") from error

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise STTError("empty_stt_output")
    text = text.strip()
    if len(text) > _MAX_TRANSCRIPT_CHARS:
        # 기존 Report.transcript 한도와 맞추며 내용을 임의로 자르지는 않는다.
        raise STTError("stt_output_too_long")
    return text
