"""LLM 공급자와 통신하는 공통 경계.

API URL·인증·HTTP 오류·응답 파싱은 이 모듈에서 처리한다.
프롬프트·이력·도구 실행 흐름은 각 에이전트가 담당한다.

API key 는 서버 환경변수에서만 읽고 응답이나 로그에 남기지 않는다.
"""

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings


class LLMError(Exception):
    """공급자 호출이나 구조화 출력 검증이 실패했다. 메시지에 비밀값을 담지 않는다."""


class LLMNotConfigured(LLMError):
    """LLM_API_URL, LLM_API_KEY, LLM_MODEL 중 빠진 값이 있다."""


def _extract_text(payload: dict[str, Any]) -> str:
    """공급자 응답에서 모델이 쓴 본문만 꺼낸다."""
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text

    chunks: list[str] = []
    for item in payload.get("output") or ():
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or ():
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    if chunks:
        return "".join(chunks)

    # Ollama /api/chat 응답은 본문을 response가 아니라
    # message.content에 넣고, /api/generate 응답은 최상위 response에 넣는다.
    response_text = payload.get("response")
    if isinstance(response_text, str) and response_text.strip():
        return response_text
    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        if message["content"].strip():
            return message["content"]

    # Chat Completions 형태로 응답하는 공급자도 받아 준다.
    for choice in payload.get("choices") or ():
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]

    raise LLMError("empty_llm_output")


async def generate_structured[Schema: BaseModel](
    *,
    instructions: str,
    input_text: str,
    schema: type[Schema],
    schema_name: str,
) -> Schema:
    """구조화 출력 하나를 받아 Pydantic 으로 검증해 돌려준다."""
    if not settings.llm_configured:
        raise LLMNotConfigured("llm_not_configured")

    if settings.llm_provider == "ollama":
        body = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "stream": False,
            "format": schema.model_json_schema(),
            "options": {"temperature": 0},
        }
        headers = {"Content-Type": "application/json"}
    else:
        body = {
            "model": settings.llm_model,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": input_text},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema.model_json_schema(),
                    "strict": False,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {settings.effective_llm_api_key}",
            "Content-Type": "application/json",
        }

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                settings.llm_api_url,
                headers=headers,
                json=body,
            )
    except httpx.HTTPError as error:
        # 공급자 URL 과 key 가 메시지에 섞이지 않도록 예외 종류만 남긴다.
        raise LLMError(f"llm_request_failed:{type(error).__name__}") from error

    if response.status_code >= 400:
        raise LLMError(f"llm_provider_error:{response.status_code}")

    try:
        payload = response.json()
    except ValueError as error:
        raise LLMError("llm_response_not_json") from error

    text = _extract_text(payload).strip()
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return schema.model_validate(json.loads(text))
    except (ValueError, ValidationError) as error:
        raise LLMError("llm_output_schema_mismatch") from error
