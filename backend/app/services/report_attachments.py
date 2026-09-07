"""보고서 첨부의 공용 추출·원본 보관·제출 연결 경계."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.content import Report, ReportAttachment, ReportSubmission
from app.models.workspace import Member
from app.schemas.reports import REPORT_ATTACHMENT_EXTRACT_MAX_LENGTH, ReportAttachmentRead
from app.services import ocr, storage, stt
from app.services.document_extraction import ExtractedDocument, ExtractionError, extract_document

PENDING_RETENTION = timedelta(hours=24)


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


async def validate_inputs(
    db: AsyncSession,
    member: Member,
    attachments: list[ReportAttachmentRead],
    *,
    report_id: UUID | None = None,
    generation: Any = None,
    expires_at: datetime | None = None,
) -> dict[UUID, ReportAttachment]:
    """같은 원본 행을 잠가 소유권 검증·만료 연장·확정과 삭제를 직렬화한다."""
    if not attachments:
        return {}
    rows = list(
        (
            await db.execute(
                select(ReportAttachment)
                .where(ReportAttachment.id.in_([item.id for item in attachments]))
                .order_by(ReportAttachment.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    originals = {row.id: row for row in rows}
    now = datetime.now(UTC)
    for item in attachments:
        row = originals.get(item.id)
        if row is None:
            if item.original_stored:
                raise HTTPException(409, "report_attachment_expired")
            # 과거 추출 전용 UUID는 원본을 가리키지 않는다.
            continue
        if row.team_id != member.team_id or row.uploaded_by_member_id != member.id:
            raise HTTPException(404, "report_attachment_not_found")
        if row.report_id is not None and row.report_id != report_id:
            linked = None
            if generation is not None:
                linked = (
                    await db.execute(
                        select(Report).where(
                            Report.id == row.report_id,
                            Report.team_id == member.team_id,
                            Report.author_member_id == member.id,
                        )
                    )
                ).scalar_one_or_none()
            if linked is None or any(
                getattr(linked, field) != getattr(generation, field)
                for field in (
                    "report_kind",
                    "report_date",
                    "source_activity_id",
                    "period_start",
                    "period_end",
                )
            ):
                raise HTTPException(409, "report_attachment_already_linked")
        if row.extracted_text is None or (
            row.report_id is None and (row.expires_at is None or row.expires_at <= now)
        ):
            raise HTTPException(409, "report_attachment_expired")
        if (item.name, item.byte_size, item.kind) != (
            row.file_name,
            row.byte_size,
            kind_of(row.media_type, row.file_name),
        ):
            raise HTTPException(422, "report_attachment_metadata_changed")
        if row.report_id is None and expires_at is not None:
            row.expires_at = max(row.expires_at, expires_at)
    return originals


def bind_to_report(
    report: Report,
    attachments: list[ReportAttachmentRead],
    originals: dict[UUID, ReportAttachment],
) -> list[dict[str, Any]]:
    """원본은 한 보고서에 귀속하고, 교정문·목적은 제출별 스냅샷으로 남긴다."""
    snapshot = []
    for item in attachments:
        value = item.model_dump(mode="json")
        if row := originals.get(item.id):
            row.report_id = report.id
            row.expires_at = None
            value["original_stored"] = True
        snapshot.append(value)
    return snapshot


def read_snapshot(value: Any) -> list[ReportAttachmentRead]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue
        try:
            result.append(ReportAttachmentRead.model_validate(item))
        except ValidationError:
            # 손상된 구형 메타데이터를 파일 경로나 원본 ID로 추정하지 않는다.
            continue
    return result


async def for_reports(
    db: AsyncSession, reports: list[Report]
) -> dict[UUID, list[ReportAttachmentRead]]:
    current = [report.current_submission_id for report in reports if report.current_submission_id]
    submissions = {}
    if current:
        submissions = {
            row.id: row
            for row in (
                await db.execute(select(ReportSubmission).where(ReportSubmission.id.in_(current)))
            )
            .scalars()
            .all()
        }
    result = {}
    for report in reports:
        submission = submissions.get(report.current_submission_id)
        snapshot = getattr(submission, "attachments_snapshot", None)
        result[report.id] = read_snapshot(snapshot)
    return result


async def cleanup_expired(*, now: datetime | None = None) -> int:
    """미귀속 원본만 정리한다. 실패한 객체는 행과 키를 유지해 다음 sweep에서 재시도한다."""
    current = now or datetime.now(UTC)
    removed_count = 0
    async with get_sessionmaker()() as db:
        rows = list(
            (
                await db.execute(
                    select(ReportAttachment)
                    .where(
                        ReportAttachment.report_id.is_(None), ReportAttachment.expires_at <= current
                    )
                    .order_by(ReportAttachment.id)
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            try:
                removed = await storage.remove(storage_key=row.storage_key)
            except storage.StorageError:
                removed = False
            if removed:
                await db.delete(row)
                removed_count += 1
        await db.commit()
    return removed_count
