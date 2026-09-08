"""보고서의 단일 구조화 호출과 안전한 초안 보존 경계."""

import asyncio
from time import perf_counter
from typing import Annotated

from langsmith import tracing_context
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.agent_logging import log_agent_error, log_agent_event
from app.services.llm import LLMError, generate_structured, llm_boundary_error_code

REPORT_TIMEOUT_SECONDS = 180


class ReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[Annotated[str, Field(min_length=1, pattern=r"\S")]] = Field(max_length=30)


async def generate_report[Schema: BaseModel](
    *, instructions: str, input_text: str, schema: type[Schema], stage: str
) -> Schema:
    """한 단계만 실행한다. 입력/권한 오류와 취소는 호출자에게 그대로 전달한다."""
    started = perf_counter()
    log_agent_event(stage, outcome="started", schema_name=schema.__name__)
    try:
        with tracing_context(enabled=False):
            async with asyncio.timeout(REPORT_TIMEOUT_SECONDS):
                result = await generate_structured(
                    instructions=instructions,
                    input_text=input_text,
                    schema=schema,
                    schema_name=stage.replace(".", "_"),
                    report_mode=True,
                )
        log_agent_event(
            stage,
            outcome="returned",
            reason_code=f"result_{type(result).__name__}",
            schema_name=schema.__name__,
        )
        try:
            return schema.model_validate(
                result.model_dump(mode="json") if isinstance(result, BaseModel) else result
            )
        except (TypeError, ValidationError) as error:
            raise LLMError("llm_output_schema_mismatch") from error
    except Exception as error:
        log_agent_error(error, stage=stage)
        if isinstance(error, (LLMError, ValueError, PermissionError)):
            raise
        if code := llm_boundary_error_code(error):
            raise LLMError(code) from None
        if isinstance(error, TimeoutError):
            raise LLMError("report_generation_timeout") from None
        if isinstance(error, (RuntimeError, TypeError)):
            raise LLMError("report_generation_failed") from None
        raise
    finally:
        log_agent_event(stage, elapsed_ms=round((perf_counter() - started) * 1000))


def retain_valid_draft(error: Exception, *, stage: str) -> None:
    """생성/출력 실패와 기간 후속 입력 크기 초과만 복구한다. 원본·권한·설정 오류는 전파한다."""
    if str(error) in {"llm_provider_error:401", "llm_provider_error:403"}:
        raise error
    if not isinstance(error, LLMError) or not (
        str(error).startswith(("llm_request_failed:", "llm_provider_error:"))
        or (
            str(error) == "period_report_input_too_large"
            and stage in {"period_report_writing.review", "period_report_writing.revise"}
        )
        or str(error)
        in {
            "llm_response_not_object",
            "llm_response_not_json",
            "empty_llm_output",
            "llm_output_schema_mismatch",
            "report_output_invalid",
            "report_generation_timeout",
            "report_generation_failed",
        }
    ):
        raise error
    log_agent_event(stage, outcome="degraded", reason_code="valid_draft_fallback")
    log_agent_error(error, stage=stage)
