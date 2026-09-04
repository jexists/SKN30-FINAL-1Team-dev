"""LLM 공급자와 통신하는 공통 경계.

API URL·인증·HTTP 오류·응답 파싱은 이 모듈에서 처리한다.
프롬프트·이력·도구 실행 흐름은 각 에이전트가 담당한다.

API key 는 서버 환경변수에서만 읽고 응답이나 로그에 남기지 않는다.
"""

import asyncio
import json
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

import httpx
import openai
from langchain_openai import ChatOpenAI, StreamChunkTimeoutError
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.services.agent_logging import log_agent_error, log_agent_event


class LLMError(Exception):
    """공급자 호출이나 구조화 출력 검증이 실패했다. 메시지에 비밀값을 담지 않는다."""


class LLMNotConfigured(LLMError):
    """LLM URL, API key 또는 모델 설정이 비어 있다."""


def _validated_endpoint():
    try:
        endpoint = urlsplit(settings.llm_api_url)
        hostname = endpoint.hostname
    except ValueError:
        raise LLMError("report_agent_unsupported_endpoint") from None
    if (
        not endpoint.netloc
        or not hostname
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.query
        or endpoint.fragment
        or endpoint.scheme != "https"
    ):
        raise LLMError("report_agent_unsupported_endpoint")
    return endpoint


def _external_api_key() -> str:
    api_key = settings.effective_llm_api_key.strip()
    if not api_key:
        raise LLMNotConfigured("llm_not_configured")
    return api_key


def configured_chat_model() -> ChatOpenAI:
    """LangChain 에이전트가 공유하는 OpenAI 호환 채팅 모델을 만든다."""
    if not settings.llm_configured:
        raise LLMNotConfigured("llm_not_configured")
    endpoint = _validated_endpoint()
    path = endpoint.path.rstrip("/")
    suffix = next((s for s in ("/responses", "/chat/completions") if path.endswith(s)), None)
    base_path = path[: -len(suffix)] if suffix else None
    if base_path is None:
        raise LLMError("report_agent_unsupported_endpoint")
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=_external_api_key(),
        base_url=urlunsplit((endpoint.scheme, endpoint.netloc, base_path, "", "")),
        use_responses_api=suffix == "/responses",
        timeout=httpx.Timeout(max(180.0, settings.llm_timeout_seconds), connect=10.0),
        max_retries=0,
        max_completion_tokens=12_000,
        streaming=True,
        stream_usage=True,
        stream_chunk_timeout=max(180.0, settings.llm_timeout_seconds),
    )


_TRANSIENT_REQUEST_ERRORS = (
    httpx.NetworkError,
    httpx.TimeoutException,
    httpx.ProxyError,
    httpx.RemoteProtocolError,
    openai.APIConnectionError,
    StreamChunkTimeoutError,
)
_TRANSIENT_REQUEST_ERROR_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "CloseError",
    "ConnectError",
    "ConnectTimeout",
    "NetworkError",
    "PoolTimeout",
    "ProxyError",
    "ReadError",
    "ReadTimeout",
    "RemoteProtocolError",
    "StreamChunkTimeoutError",
    "TimeoutException",
    "WriteError",
    "WriteTimeout",
}


def llm_boundary_error_code(error: BaseException) -> str | None:
    """SDK/HTTP 예외 체인을 비밀값 없는 LLM 경계 코드로 바꾼다.

    OpenAI·LangChain·httpx가 발생시킨 연결 오류와 HTTP 상태 오류만
    분류한다. 출력 검증·앱 로직 오류는 ``None``으로 남겨 재시도하지
    않도록 한다. 예외 메시지는 코드에 포함하지 않는다.
    """
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, openai.APIStatusError):
            return f"llm_provider_error:{current.status_code}"
        if isinstance(current, httpx.HTTPStatusError):
            return f"llm_provider_error:{current.response.status_code}"
        if isinstance(current, _TRANSIENT_REQUEST_ERRORS):
            return f"llm_request_failed:{type(current).__name__}"
        current = current.__cause__ or current.__context__
    return None


def is_transient_llm_error(error_code: str) -> bool:
    """LLM 경계 코드 중 연결 장애·429·5xx인 경우만 재시도 가능하다."""
    if error_code.startswith("llm_request_failed:"):
        return error_code.rsplit(":", 1)[-1] in _TRANSIENT_REQUEST_ERROR_NAMES
    if error_code.startswith("llm_provider_error:"):
        try:
            status_code = int(error_code.rsplit(":", 1)[-1])
        except ValueError:
            return False
        return status_code == 429 or 500 <= status_code <= 599
    return False


def safe_token_usage(usage: object) -> dict[str, int]:
    """공급자가 돌려준 사용량 중 알려진 비음수 정수만 남긴다. 없으면 추정하지 않는다."""
    if not isinstance(usage, dict):
        return {}
    counts = {}
    for field, fallback in (
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = usage.get(field, usage.get(fallback))
        if type(value) is int and value >= 0:
            counts[field] = value
    return counts


def _extract_text(payload: object) -> str:
    """공급자 응답에서 모델이 쓴 본문만 꺼낸다."""
    if not isinstance(payload, dict):
        raise LLMError("llm_response_not_object")
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
    _validated_endpoint()

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
        "Authorization": f"Bearer {_external_api_key()}",
        "Content-Type": "application/json",
    }

    started = perf_counter()
    log_agent_event(
        "llm.request_started", schema_name=schema_name, timeout_seconds=settings.llm_timeout_seconds
    )
    try:
        timeout = httpx.Timeout(
            settings.llm_timeout_seconds, connect=min(10.0, settings.llm_timeout_seconds)
        )
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                settings.llm_api_url,
                headers=headers,
                json=body,
            )
    except httpx.HTTPError as error:
        log_agent_error(
            error,
            stage="llm.request",
            schema_name=schema_name,
            elapsed_ms=round((perf_counter() - started) * 1000),
        )
        # 공급자 URL 과 key 가 메시지에 섞이지 않도록 예외 종류만 남긴다.
        code = llm_boundary_error_code(error) or f"llm_request_failed:{type(error).__name__}"
        raise LLMError(code) from error
    except asyncio.CancelledError:
        log_agent_event(
            "llm.request_cancelled",
            schema_name=schema_name,
            elapsed_ms=round((perf_counter() - started) * 1000),
        )
        raise

    response_log = {
        "schema_name": schema_name,
        "status_code": response.status_code,
        "request_id": getattr(response, "headers", {}).get("x-request-id"),
        "elapsed_ms": round((perf_counter() - started) * 1000),
    }
    if response.status_code >= 400:
        error = LLMError(f"llm_provider_error:{response.status_code}")
        log_agent_error(
            error,
            stage="llm.response",
            error_code="llm_provider_error",
            **response_log,
        )
        raise error

    try:
        payload = response.json()
    except ValueError as error:
        log_agent_error(error, stage="llm.response_json", **response_log)
        raise LLMError("llm_response_not_json") from error

    log_agent_event(
        "llm.request_completed",
        **response_log,
        **safe_token_usage(payload.get("usage") if isinstance(payload, dict) else None),
    )
    try:
        text = _extract_text(payload).strip()
    except Exception as error:
        log_agent_error(error, stage="llm.output_text", **response_log)
        raise
    if text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return schema.model_validate(json.loads(text))
    except (ValueError, ValidationError) as error:
        log_agent_error(error, stage="llm.output_validation", **response_log)
        raise LLMError("llm_output_schema_mismatch") from error
