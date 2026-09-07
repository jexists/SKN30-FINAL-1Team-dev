"""모든 보고서 작성 화면이 공유하는 일회용 첨부 API."""

from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentMember
from app.core.config import settings
from app.schemas.reports import ReportAttachmentRead
from app.services import ocr, report_attachments, stt
from app.services.document_extraction import ExtractionError
from app.services.upload_guard import (
    ALLOWED_AUDIO_EXTENSIONS,
    UploadRejected,
    check_report_attachment_upload,
    check_size,
)

router = APIRouter(tags=["report-attachments"])


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
    _member: CurrentMember,
    upload: Annotated[UploadFile, File()],
) -> ReportAttachmentRead:
    """파일을 요청 안에서 검증·추출하고 원본은 보관하지 않는다."""
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

    return ReportAttachmentRead(
        id=uuid4(),
        kind=report_attachments.kind_of(allowed.media_type, file_name),
        name=file_name,
        byte_size=len(content),
        extract=extracted.plain_text,
    )
