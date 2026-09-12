"""실행 ID로 찾는 에이전트 오류 로그. 예외 메시지·입력·응답 본문은 기록하지 않는다."""

import hashlib
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
_usage: ContextVar[dict[str, int] | None] = ContextVar("agent_token_usage", default=None)
_fields = frozenset(
    {
        "run_id",
        "agent_code",
        "model",
        "sales_deal_id",
        "schema_name",
        "lookup_kind",
        "ocr_provider",
        "attempt",
        "status_code",
        "request_id",
        "elapsed_ms",
        "timeout_seconds",
        "call_count",
        "model_call_count",
        "call_limit",
        "tool_call_count",
        "model_call_id",
        "required_delegation_count",
        "delegation_count",
        "review_attempt",
        "review_limit",
        "repair_count",
        "repair_limit",
        "validation_attempt",
        "validation_limit",
        "validation_path",
        "missing_evidence_ids",
        "unexpected_evidence_ids",
        "semantic_review_count",
        "evidence_batch_count",
        "support_batch_count",
        "review_candidate_count",
        "review_change_count",
        "review_trigger",
        "selected_deal_count",
        "scope_name",
        "scope_count",
        "phase",
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
        "parent_run_id",
        "assignment_id",
        "assignment_kind",
        "assignment_phase",
        "work_unit_id",
        "tool_name",
        "requested_scope",
        "requested_scope_kind",
        "requested_scope_length",
        "requested_scope_sha256",
        "allowed_scopes",
        "existing_scopes",
        "decision",
        "fallback_selected",
        "report_kind",
        "allowed_scope_count",
        "existing_scope_count",
        "validation_error_path",
        "validation_missing_fields",
        "validation_actual_keys",
        "validation_actual_types",
        "validation_null_fields",
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
        "report_unassigned_without_evidence",
        "report_evidence_coverage_missing",
        "report_transcript_hash_mismatch",
        "report_body_empty",
        "report_evidence_duplicate",
        "report_title_empty",
        "report_deal_title_missing",
        "report_scope_not_allowed",
        "report_deal_not_allowed",
        "report_source_not_allowed",
        "report_deal_no_evidence_marker_missing",
    }
)

_server_identifier = re.compile(r"[a-z][a-z0-9_-]{0,63}(?::[1-9][0-9]{0,5})?")
_scope_identifier = re.compile(
    r"(?:common(?:_report)?|unassigned(?:_report)?|deal_reports\[(?:0|[1-9][0-9]{0,5})\]|"
    r"(?:meeting_bundle|child_submission|direct_activity|attachment):[1-9][0-9]{0,5})"
)


def safe_report_scope(scope: object, known_scopes=()) -> dict[str, object]:
    """Known server scope는 이름을, 모델 자유 문자열은 종류·길이·해시만 남긴다."""
    if not isinstance(scope, str):
        return {"requested_scope_kind": type(scope).__name__}
    if scope in known_scopes and (
        _server_identifier.fullmatch(scope) or _scope_identifier.fullmatch(scope)
    ):
        return {"requested_scope": scope, "requested_scope_kind": "known"}
    if _scope_identifier.fullmatch(scope):
        return {"requested_scope": scope, "requested_scope_kind": "scope_identifier"}
    kind = "identifier" if _server_identifier.fullmatch(scope) else "freeform"
    return {
        "requested_scope_kind": kind,
        "requested_scope_length": len(scope),
        "requested_scope_sha256": hashlib.sha256(scope.encode()).hexdigest()[:16],
    }


def _safe_fields(fields: dict) -> dict:
    safe = {}
    known_scopes = set()
    for key in ("allowed_scopes", "existing_scopes"):
        value = fields.get(key)
        if isinstance(value, (list, tuple, set, frozenset)):
            known_scopes.update(item for item in value if isinstance(item, str))
    for key, value in fields.items():
        if key not in _fields:
            continue
        if key == "requested_scope":
            continue
        if key in {"allowed_scopes", "existing_scopes"}:
            if (
                isinstance(value, (list, tuple, set, frozenset))
                and all(
                    isinstance(item, str)
                    and (_server_identifier.fullmatch(item) or _scope_identifier.fullmatch(item))
                    for item in value
                )
            ):
                values = sorted(value)
                safe[key] = values[:20]
                safe[key.replace("scopes", "scope_count")] = len(values)
        elif isinstance(value, (str, int, float, bool)):
            safe[key] = value
    if "requested_scope" in fields:
        safe.update(safe_report_scope(fields["requested_scope"], known_scopes))
    return safe


@contextmanager
def agent_log_context(**fields):
    """async task·to_thread에 전파하고 종료 시 복원한다. fields는 코드가 정한 메타데이터만."""
    token = _context.set({**(_context.get() or {}), **fields})
    try:
        yield
    finally:
        _context.reset(token)


@contextmanager
def collect_token_usage():
    """한 AgentRun 안의 여러 모델 호출 사용량을 합산한다."""
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    token = _usage.set(usage)
    try:
        yield usage
    finally:
        _usage.reset(token)


def log_agent_event(stage: str, **fields):
    """호출 시간·횟수·공급자가 반환한 토큰 수. 본문이나 모델의 자유 서술은 받지 않는다."""
    usage = _usage.get()
    if usage is not None:
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = fields.get(key)
            if type(value) is int and value >= 0:
                usage[key] += value
    record = {
        "event": "agent_progress",
        "timestamp": datetime.now(UTC).isoformat(),
        "stage": stage,
        **_safe_fields({**(_context.get() or {}), **fields}),
    }
    request_id = record.pop("request_id", None)
    if isinstance(request_id, str) and re.fullmatch(r"req[_-][A-Za-z0-9_-]{1,100}", request_id):
        record["request_id"] = request_id
    try:
        logger.info("agent_progress %s", json.dumps(record, ensure_ascii=False))
    except Exception:
        pass


def log_agent_error(error: BaseException, *, stage: str, error_code: str | None = None, **fields):
    record = {
        "event": "agent_error",
        "timestamp": datetime.now(UTC).isoformat(),
        "stage": stage,
        **_safe_fields({**(_context.get() or {}), **fields}),
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
    try:
        logger.error("agent_error %s", json.dumps(record, ensure_ascii=False))
    except Exception:
        pass


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
