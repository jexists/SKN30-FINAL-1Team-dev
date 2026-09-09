"""모든 보고서 작성 화면이 공유하는 원본 보관·추출 API."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession
from app.core.config import settings
from app.models.content import ReportAttachment
from app.schemas.reports import ReportAttachmentRead
from app.services import ocr, report_attachments, storage, stt
from app.services.document_extraction import ExtractionError
from app.services.upload_guard import (
    ALLOWED_AUDIO_EXTENSIONS,
    UploadRejected,
    check_report_attachment_upload,
    check_size,
)

router = APIRouter(tags=["report-attachments"])


@router.get("/report-attachments/limits")
async def report_attachment_limits(_member: CurrentMember) -> dict[str, int]:
    return {
        "audio_max_bytes": settings.stt_max_bytes,
        "document_max_bytes": settings.upload_max_bytes,
    }


def _processing_error(error: Exception) -> HTTPException:
    if isinstance(error, stt.STTNotConfigured):
        return HTTPException(503, "stt_not_configured")
    if isinstance(error, stt.STTError):
        return HTTPException(503, "stt_unavailable")
    if isinstance(error, ocr.OcrError):
        detail = (
            "ocr_not_configured"
            if str(error) == "ocr_provider_not_configured"
            else "ocr_unavailable"
        )
        return HTTPException(503, detail)
    if isinstance(error, ExtractionError):
        if str(error) in {
            "report_attachment_ocr_too_large",
            "report_attachment_text_too_large",
        }:
            return HTTPException(413, str(error))
        return HTTPException(422, "report_attachment_extraction_failed")
    raise TypeError("unsupported_report_attachment_error")


@router.post(
    "/report-attachments",
    response_model=ReportAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_report_attachment(
    member: CurrentMember,
    db: DbSession,
    upload: Annotated[UploadFile, File()],
) -> ReportAttachmentRead:
    """검증·추출한 원본을 24시간 보관하며, 확정하면 보고서에 귀속한다."""
    if not settings.storage_configured:
        raise HTTPException(503, "storage_not_configured")
    file_name = (upload.filename or "").strip()
    limit = (
        settings.stt_max_bytes
        if Path(file_name).suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
        else settings.upload_max_bytes
    )
    content = await upload.read(limit + 1)
    try:
        check_size(len(content), limit)
        allowed = check_report_attachment_upload(
            file_name=file_name,
            declared_media_type=upload.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(rejected.status_code, rejected.detail) from rejected

    try:
        extracted = await report_attachments.extract(
            file_name=file_name,
            media_type=allowed.media_type,
            content=content,
        )
    except (stt.STTError, ocr.OcrError, ExtractionError) as error:
        raise _processing_error(error) from error

    attachment_id = uuid4()
    read = ReportAttachmentRead(
        id=attachment_id,
        kind=report_attachments.kind_of(allowed.media_type, file_name),
        name=file_name,
        byte_size=len(content),
        extract=extracted.plain_text,
        original_stored=True,
    )
    now = datetime.now(UTC)
    storage_key = storage.build_storage_key(member.team_id, allowed.extension)
    row = ReportAttachment(
        id=attachment_id,
        team_id=member.team_id,
        uploaded_by_member_id=member.id,
        report_id=None,
        file_name=file_name,
        storage_key=storage_key,
        media_type=allowed.media_type,
        byte_size=len(content),
        extracted_text=None,
        expires_at=now + report_attachments.PENDING_RETENTION,
        uploaded_at=now,
    )
    # 먼저 키를 기록해야 Storage 성공 후 DB 실패가 나도 만료 정리가 원본을 찾는다.
    try:
        db.add(row)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    try:
        await storage.upload(
            storage_key=storage_key, content=content, media_type=allowed.media_type
        )
        row.extracted_text = read.extract
        await db.commit()
    except Exception as error:
        await db.rollback()
        # 삭제가 실패하면 만료된 행을 유지한다. 다음 worker sweep이 같은 키를 재시도한다.
        try:
            pending = (
                await db.execute(
                    select(ReportAttachment)
                    .where(ReportAttachment.id == attachment_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if pending is not None:
                pending.expires_at = datetime.now(UTC)
                try:
                    removed = await storage.remove(storage_key=storage_key)
                except storage.StorageError:
                    removed = False
                if removed:
                    await db.delete(pending)
                await db.commit()
        except Exception:
            # 예약 행은 최초 commit에 남아 있으므로 DB가 복구되면 기존 sweep이 처리한다.
            await db.rollback()
        if isinstance(error, storage.StorageError):
            raise HTTPException(503, str(error)) from error
        raise
    return read
