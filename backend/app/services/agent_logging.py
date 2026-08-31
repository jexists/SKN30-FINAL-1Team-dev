"""실행 ID로 찾는 에이전트 오류 로그. 예외 메시지·입력·응답 본문은 기록하지 않는다."""

import json
import logging
import re
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import get_args

from pydantic import ValidationError
from pydantic_core import ErrorType

logger = logging.getLogger(__name__)
# 성공 호출도 실제 운영 로그에 남긴다. 메시지는 아래 허용 필드만 포함한다.
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    logger.addHandler(logging.StreamHandler())
_context: ContextVar[dict | None] = ContextVar("agent_log_context", default=None)
_fields = frozenset(
    {
        "run_id",
        "agent_code",
        "model",
        "sales_deal_id",
        "schema_name",
        "lookup_kind",
        "attempt",
        "status_code",
        "request_id",
        "elapsed_ms",
        "timeout_seconds",
        "call_count",
        "call_limit",
        "model_call_id",
        "review_attempt",
        "review_limit",
        "validation_attempt",
        "validation_path",
        "missing_evidence_ids",
        "unexpected_evidence_ids",
        "semantic_review_count",
        "review_candidate_count",
        "review_change_count",
        "segment_id",
        "before_scope",
        "after_scope",
        "before_deal_ids",
        "after_deal_ids",
        "basis_segment_ids",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "reason_code",
        "outcome",
    }
)
_validation_types = frozenset(get_args(ErrorType))
_report_validation_codes = frozenset(
    {
        "report_selected_deals_mismatch",
        "report_deal_evidence_mismatch",
        "report_common_evidence_mismatch",
        "report_common_without_evidence",
        "report_unassigned_evidence_missing",
        "report_unassigned_original_missing",
        "report_unassigned_without_evidence",
        "report_evidence_coverage_missing",
        "report_transcript_hash_mismatch",
        "report_body_empty",
        "report_evidence_duplicate",
    }
)


@contextmanager
def agent_log_context(**fields):
    """async task·to_thread에 전파하고 종료 시 복원한다. fields는 코드가 정한 메타데이터만."""
    token = _context.set({**(_context.get() or {}), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def log_agent_event(stage: str, **fields):
    """호출 시간·횟수·공급자가 반환한 토큰 수. 본문이나 모델의 자유 서술은 받지 않는다."""
    record = {
        "event": "agent_progress",
        "timestamp": datetime.now(UTC).isoformat(),
        "stage": stage,
        **{
            key: value
            for key, value in {**(_context.get() or {}), **fields}.items()
            if key in _fields and isinstance(value, (str, int, float, bool))
        },
    }
    request_id = record.pop("request_id", None)
    if isinstance(request_id, str) and re.fullmatch(r"req[_-][A-Za-z0-9_-]{1,100}", request_id):
        record["request_id"] = request_id
    logger.info("agent_progress %s", json.dumps(record, ensure_ascii=False))


def log_agent_error(error: BaseException, *, stage: str, error_code: str | None = None, **fields):
    record = {
        "event": "agent_error",
        "timestamp": datetime.now(UTC).isoformat(),
        "stage": stage,
        **{
            key: value
            for key, value in {**(_context.get() or {}), **fields}.items()
            if key in _fields
        },
    }
    request_id = record.pop("request_id", None)
    if isinstance(request_id, str) and re.fullmatch(r"req[_-][A-Za-z0-9_-]{1,100}", request_id):
        record["request_id"] = request_id
    if error_code is not None:
        record["error_code"] = error_code
    exceptions = []
    pending = [error]
    seen = set()
    while pending and len(exceptions) < 5:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        detail = {
            "type": type(current).__name__,
            # format_exception/format_tb는 예외 본문·소스 줄을 포함할 수 있어 사용하지 않는다.
            "frames": [
                f"{Path(frame.f_code.co_filename).name}:{line}:{frame.f_code.co_name}"
                for frame, line in traceback.walk_tb(current.__traceback__)
            ][-16:],
        }
        status = getattr(current, "status_code", None)
        if isinstance(status, int) and 100 <= status <= 599:
            detail["status_code"] = status
        request_id = getattr(current, "request_id", None)
        if isinstance(request_id, str) and re.fullmatch(r"req[_-][A-Za-z0-9_-]{1,100}", request_id):
            detail["request_id"] = request_id
        if isinstance(current, ValidationError):
            detail["validation_error_types"] = sorted(
                {
                    item["type"] if item["type"] in _validation_types else "custom_error"
                    for item in current.errors(
                        include_input=False, include_context=False, include_url=False
                    )
                }
            )
        # 자체 검증기의 고정 코드만 허용한다. 임의 ValueError 메시지는 기록하지 않는다.
        if current.args and isinstance(current.args[0], str):
            if current.args[0] in _report_validation_codes:
                detail["reason_code"] = current.args[0]
        exceptions.append(detail)
        for cause in (current.__cause__, current.__context__, getattr(current, "source", None)):
            if isinstance(cause, BaseException) and id(cause) not in seen:
                pending.append(cause)
    record["exceptions"] = exceptions
    logger.error("agent_error %s", json.dumps(record, ensure_ascii=False))


@contextmanager
def agent_operation(stage: str, **fields):
    """예외가 안전한 코드로 치환되거나 상위 단계로 전달되기 전에 원인을 기록한다."""
    with agent_log_context(**fields):
        started = perf_counter()
        try:
            yield
        except Exception as error:
            log_agent_error(error, stage=stage, elapsed_ms=round((perf_counter() - started) * 1000))
            raise
        else:
            log_agent_event(
                stage, outcome="completed", elapsed_ms=round((perf_counter() - started) * 1000)
            )
