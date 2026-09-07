"""보고서 종류와 무관한 일회용 첨부 추출 경계."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.config import settings
from app.schemas.reports import REPORT_ATTACHMENT_EXTRACT_MAX_LENGTH
from app.services import ocr, stt
from app.services.document_extraction import ExtractedDocument, ExtractionError, extract_document


def kind_of(media_type: str | None, file_name: str) -> str:
    if (media_type or "").startswith("audio/"):
        return "audio"
    if (media_type or "").startswith("image/"):
        return "image"
    if Path(file_name).suffix.lower() == ".pdf":
        return "pdf"
    raise ValueError("report_attachment_type_invalid")


async def extract(
    *,
    file_name: str,
    media_type: str,
    content: bytes,
) -> ExtractedDocument:
    """기존 STT·문서 추출·OCR을 한 보고서 첨부 결과로 맞춘다."""
    if media_type.startswith("audio/"):
        transcript = await stt.transcribe(
            file_name=file_name,
            media_type=media_type,
            content=content,
        )
        result = ExtractedDocument(
            plain_text=transcript,
            markdown=transcript + "\n",
            payload={"version": 1, "source_type": "audio", "page_count": 1},
        )
    else:
        try:
            result = await asyncio.to_thread(
                extract_document,
                file_name=file_name,
                media_type=media_type,
                content=content,
            )
        except ExtractionError as error:
            if str(error) not in {"ocr_required", "ocr_provider_required"}:
                raise
            if (
                settings.ocr_provider == "runpod"
                and len(content) > settings.ocr_runpod_inline_max_bytes
            ):
                raise ExtractionError("report_attachment_ocr_too_large") from error
            result = await ocr.extract_document(
                file_name=file_name,
                media_type=media_type,
                content=content,
            )
    extract = result.plain_text.strip()
    if not extract:
        raise ExtractionError("report_attachment_extract_empty")
    if len(extract) > REPORT_ATTACHMENT_EXTRACT_MAX_LENGTH:
        raise ExtractionError("report_attachment_text_too_large")
    return result
