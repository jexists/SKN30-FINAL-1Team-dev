"""사업자등록증 OCR의 비동기 실행 상태."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
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


def _text_shape(plain_text: str) -> dict[str, object]:
    """OCR 원문 대신 형태만 남긴다. 원문에는 상호·주소가 들어 있어 로그에 남기지 않는다."""

    return {
        "ocr_text_length": len(plain_text),
        "ocr_has_table": "|" in plain_text,
    }


def _is_pdf(*, file_name: str, media_type: str) -> bool:
    return media_type == "application/pdf" or file_name.lower().endswith(".pdf")


async def _scan_once(
    *,
    file_name: str,
    media_type: str,
    content: bytes,
    source: str,
    started: float,
) -> tuple[BusinessLicenseDraft | None, str | None]:
    """OCR 한 번과 구조화 한 번. 실패는 draft 대신 오류 코드로 돌려준다."""

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
            ocr_source=source,
        )
        return None, "ocr_unavailable"
    except Exception as error:
        code = f"business_license_scan_failed:{type(error).__name__}"
        log_agent_error(
            error,
            stage="ocr_failed",
            error_code=code,
            elapsed_ms=_elapsed_ms(started),
            ocr_source=source,
        )
        return None, code

    log_agent_event(
        "ocr_completed",
        elapsed_ms=_elapsed_ms(started),
        ocr_provider=str(extracted.payload.get("ocr_provider") or "unknown"),
        ocr_source=source,
        **_text_shape(extracted.plain_text),
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
            ocr_source=source,
        )
        return None, code
    except Exception as error:
        code = f"business_license_scan_failed:{type(error).__name__}"
        log_agent_error(
            error,
            stage="scan_failed",
            error_code=code,
            elapsed_ms=_elapsed_ms(started),
            ocr_source=source,
        )
        return None, code

    log_agent_event("llm_completed", elapsed_ms=_elapsed_ms(llm_started), ocr_source=source)
    return draft, None


async def _retry_as_image(
    *,
    file_name: str,
    content: bytes,
    started: float,
) -> BusinessLicenseDraft | None:
    """스캔 PDF를 이미지로 구워 한국어 OCR 경로로 다시 읽는다.

    PDF는 pdf-inspector 경로로 가는데 그쪽에는 한국어 설정이 없어 한글이 깨진다.
    실패하면 None을 돌려주고 1차 결과를 그대로 쓴다. 재시도가 되던 것을 망치면 안 된다.
    """

    log_agent_event("retrying_as_image")
    try:
        png = await asyncio.to_thread(ocr.render_pdf_page_png, content)
    except ocr.OcrError as error:
        log_agent_error(error, stage="pdf_render_failed", error_code=str(error))
        return None

    draft, error_code = await _scan_once(
        file_name=f"{Path(file_name).stem}.png",
        media_type="image/png",
        content=png,
        source="pdf_rendered_image",
        started=started,
    )
    if draft is None:
        log_agent_event("image_retry_failed", error_code=error_code)
    return draft


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
        draft, error_code = await _scan_once(
            file_name=file_name,
            media_type=media_type,
            content=content,
            source="original",
            started=started,
        )
        if draft is None:
            _finish(scan_id, draft=None, error=error_code)
            return

        # 회사명과 주소가 둘 다 비면 한글을 못 읽은 것이다. 텍스트 PDF는 지금 경로가
        # 더 정확하므로, 이때만 이미지로 구워 한 번 더 읽는다.
        if (
            _is_pdf(file_name=file_name, media_type=media_type)
            and not draft.fields.company.strip()
            and not draft.fields.address.strip()
        ):
            retried = await _retry_as_image(file_name=file_name, content=content, started=started)
            if retried is not None:
                draft = retried

        log_agent_event("scan_completed", elapsed_ms=_elapsed_ms(started))
        _finish(scan_id, draft=draft, error=None)
