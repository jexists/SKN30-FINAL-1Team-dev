"""명함 인식의 비동기 실행 상태.

CloudFront origin timeout 안에서 응답을 끝내기 위해 OCR·LLM 호출을 백그라운드로
넘기고, 진행 상태만 프로세스 안에 잠깐 둔다. 원본 이미지는 어디에도 저장하지
않고 백그라운드 작업 인자로만 전달하며, 확인 전 개인정보인 인식 결과도 DB에
남기지 않고 짧은 TTL 뒤에 사라진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import perf_counter
from uuid import UUID, uuid4

from app.schemas.business_cards import BusinessCardDraft
from app.services import business_cards, ocr
from app.services.agent_logging import agent_log_context, log_agent_error, log_agent_event
from app.services.llm import LLMError

# 사용자가 화면에서 결과를 받아가기에 충분하고, 개인정보가 오래 남지 않는 길이다.
SCAN_RETENTION_SECONDS = 300
AGENT_CODE = "business_card_scan"


@dataclass
class ScanState:
    """한 건의 명함 인식 진행 상태. 완료 전에는 draft 가 비어 있다."""

    requested_by_member_id: UUID
    expires_at: datetime
    processing_status: str = "processing"
    draft: BusinessCardDraft | None = None
    processing_error: str | None = None


# 백엔드 컨테이너는 uvicorn 단일 프로세스라 접수와 폴링이 같은 프로세스에 도달한다.
_scans: dict[UUID, ScanState] = {}
_lock = Lock()


def _purge(now: datetime) -> None:
    """만료된 결과를 지운다. 별도 타이머 없이 접근할 때마다 정리한다."""
    for scan_id in [key for key, state in _scans.items() if state.expires_at <= now]:
        del _scans[scan_id]


def create(*, member_id: UUID, now: datetime | None = None) -> UUID:
    """인식 자리를 만들고 폴링에 쓸 id 를 돌려준다."""
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
    """접수한 본인의 인식 상태만 돌려준다. 없거나 만료됐으면 None 이다."""
    current = now or datetime.now(UTC)
    with _lock:
        _purge(current)
        state = _scans.get(scan_id)
        if state is None or state.requested_by_member_id != member_id:
            return None
        return state


def _finish(scan_id: UUID, *, draft: BusinessCardDraft | None, error: str | None) -> None:
    with _lock:
        state = _scans.get(scan_id)
        if state is None:
            # 결과가 나오기 전에 만료됐다면 사용자는 이미 다시 시도한 뒤다.
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
    """백그라운드 인식. 실패 코드는 동기 구현이 쓰던 값을 그대로 유지한다.

    한 건이 어느 단계까지 갔는지 로컬 콘솔과 운영 로그에서 추적할 수 있게 단계마다
    기록한다. 파일명·OCR 원문·추출한 명함 값은 agent_logging 의 허용 필드가 아니라
    기록되지 않는다.
    """
    with agent_log_context(run_id=str(scan_id), agent_code=AGENT_CODE):
        started = perf_counter()
        log_agent_event("ocr_started")
        try:
            extracted = await ocr.extract_document(
                file_name=file_name,
                media_type=media_type,
                content=content,
                profile="business_card",
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
            code = f"business_card_scan_failed:{type(error).__name__}"
            log_agent_error(
                error, stage="ocr_failed", error_code=code, elapsed_ms=_elapsed_ms(started)
            )
            _finish(scan_id, draft=None, error=code)
            return

        # 원격 OCR이 실패해 로컬로 폴백했는지가 여기서 드러난다. 폴백은 조용히
        # 일어나기 때문에 provider 를 남기지 않으면 원인을 찾을 수 없다.
        log_agent_event(
            "ocr_completed",
            elapsed_ms=_elapsed_ms(started),
            ocr_provider=str(extracted.payload.get("ocr_provider") or "unknown"),
        )

        llm_started = perf_counter()
        try:
            draft = await business_cards.extract(ocr_text=extracted.plain_text, file_name=file_name)
        except LLMError as error:
            code = (
                "llm_not_configured"
                if str(error) == "llm_not_configured"
                else "business_card_extraction_failed"
            )
            log_agent_error(
                error, stage="llm_failed", error_code=code, elapsed_ms=_elapsed_ms(llm_started)
            )
            _finish(scan_id, draft=None, error=code)
            return
        except Exception as error:
            # 예상하지 못한 오류도 원문 대신 안전한 코드만 화면에 전달한다.
            code = f"business_card_scan_failed:{type(error).__name__}"
            log_agent_error(
                error, stage="scan_failed", error_code=code, elapsed_ms=_elapsed_ms(started)
            )
            _finish(scan_id, draft=None, error=code)
            return

        log_agent_event("llm_completed", elapsed_ms=_elapsed_ms(llm_started))
        log_agent_event("scan_completed", elapsed_ms=_elapsed_ms(started))
        _finish(scan_id, draft=draft, error=None)
