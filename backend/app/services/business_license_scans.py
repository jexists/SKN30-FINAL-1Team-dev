"""사업자등록증 OCR의 비동기 실행 상태."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import perf_counter
from uuid import UUID, uuid4

from app.schemas.business_licenses import BusinessLicenseDraft
from app.services import business_licenses, ocr
from app.services.agent_logging import agent_log_context, log_agent_error, log_agent_event
from app.services.llm import LLMError

SCAN_RETENTION_SECONDS = 300
AGENT_CODE = "business_license_scan"


@dataclass
class ScanState:
    requested_by_member_id: UUID
    expires_at: datetime
    processing_status: str = "processing"
    draft: BusinessLicenseDraft | None = None
    processing_error: str | None = None


_scans: dict[UUID, ScanState] = {}
_lock = Lock()


def _purge(now: datetime) -> None:
    for scan_id in [key for key, state in _scans.items() if state.expires_at <= now]:
        del _scans[scan_id]


def create(*, member_id: UUID, now: datetime | None = None) -> UUID:
    current = now or datetime.now(UTC)
    scan_id = uuid4()
    with _lock:
        _purge(current)
        _scans[scan_id] = ScanState(
            requested_by_member_id=member_id,
            expires_at=current + timedelta(seconds=SCAN_RETENTION_SECONDS),
        )
    return scan_id


def get(scan_id: UUID, *, member_id: UUID, now: datetime | None = None) -> ScanState | None:
    current = now or datetime.now(UTC)
    with _lock:
        _purge(current)
        state = _scans.get(scan_id)
        if state is None or state.requested_by_member_id != member_id:
            return None
        return state


def _finish(scan_id: UUID, *, draft: BusinessLicenseDraft | None, error: str | None) -> None:
    with _lock:
        state = _scans.get(scan_id)
        if state is None:
            return
        state.processing_status = "completed" if error is None else "failed"
        state.draft = draft
        state.processing_error = error


def _elapsed_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)


async def run(
    scan_id: UUID,
    *,
    file_name: str,
    media_type: str,
    content: bytes,
) -> None:
    """OCR과 구조화 추출을 실행하고 원문은 상태에 저장하지 않는다."""

    with agent_log_context(run_id=str(scan_id), agent_code=AGENT_CODE):
        started = perf_counter()
        log_agent_event("ocr_started")
        try:
            extracted = await ocr.extract_document(
                file_name=file_name,
                media_type=media_type,
                content=content,
                profile="document",
            )
        except ocr.OcrError as error:
            log_agent_error(
                error,
                stage="ocr_failed",
                error_code="ocr_unavailable",
                elapsed_ms=_elapsed_ms(started),
            )
            _finish(scan_id, draft=None, error="ocr_unavailable")
            return
        except Exception as error:
            code = f"business_license_scan_failed:{type(error).__name__}"
            log_agent_error(
                error, stage="ocr_failed", error_code=code, elapsed_ms=_elapsed_ms(started)
            )
            _finish(scan_id, draft=None, error=code)
            return

        log_agent_event(
            "ocr_completed",
            elapsed_ms=_elapsed_ms(started),
            ocr_provider=str(extracted.payload.get("ocr_provider") or "unknown"),
        )
        llm_started = perf_counter()
        try:
            draft = await business_licenses.extract(
                ocr_text=extracted.plain_text,
                file_name=file_name,
            )
        except LLMError as error:
            code = (
                "llm_not_configured"
                if str(error) == "llm_not_configured"
                else "business_license_extraction_failed"
            )
            log_agent_error(
                error,
                stage="llm_failed",
                error_code=code,
                elapsed_ms=_elapsed_ms(llm_started),
            )
            _finish(scan_id, draft=None, error=code)
            return
        except Exception as error:
            code = f"business_license_scan_failed:{type(error).__name__}"
            log_agent_error(
                error, stage="scan_failed", error_code=code, elapsed_ms=_elapsed_ms(started)
            )
            _finish(scan_id, draft=None, error=code)
            return

        log_agent_event("llm_completed", elapsed_ms=_elapsed_ms(llm_started))
        log_agent_event("scan_completed", elapsed_ms=_elapsed_ms(started))
        _finish(scan_id, draft=draft, error=None)
