"""자료실의 승인 대기 파일과 감사 이력 정리."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, or_, select

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.content import DocumentFileAudit
from app.models.content import File as FileRow
from app.services import document_processing, storage


@dataclass(frozen=True)
class CleanupResult:
    """한 번의 정리 작업에서 처리한 행 수."""

    expired_review_drafts: int
    expired_unapproved_files: int
    deleted_audit_logs: int


async def cleanup_expired(
    *, now: datetime | None = None, dry_run: bool = False
) -> CleanupResult:
    """보관 정책이 지난 Storage 객체와 DB 이력을 정리한다.

    승인 완료 파일은 원본과 RAG를 삭제하지 않는다. 승인 전 파일만 원본 보관
    기한을 적용하고, 임시 OCR·요약 결과는 더 짧은 검토 기한을 적용한다.
    """
    current = now or datetime.now(UTC)
    review_cutoff = current - timedelta(days=settings.document_review_draft_retention_days)
    file_cutoff = current - timedelta(days=settings.document_unapproved_file_retention_days)
    audit_cutoff = current - timedelta(days=settings.document_audit_log_retention_days)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        unapproved = (
            await db.execute(
                select(FileRow).where(
                    FileRow.processing_status != "completed",
                    or_(
                        FileRow.unapproved_expires_at <= current,
                        and_(
                            FileRow.unapproved_expires_at.is_(None),
                            FileRow.uploaded_at <= file_cutoff,
                        ),
                    ),
                )
            )
        ).scalars().all()
        if not dry_run:
            for row in unapproved:
                await storage.remove(
                    storage_key=document_processing.draft_storage_key(row.storage_key)
                )
                await storage.remove(storage_key=row.storage_key)
                await db.delete(row)

        review_conditions = [
            FileRow.processing_status == "review_required",
            or_(
                FileRow.review_expires_at <= current,
                and_(
                    FileRow.review_expires_at.is_(None),
                    FileRow.processed_at <= review_cutoff,
                ),
            ),
        ]
        if unapproved:
            review_conditions.append(FileRow.id.not_in([row.id for row in unapproved]))
        review_drafts = (
            await db.execute(select(FileRow).where(*review_conditions))
        ).scalars().all()
        if not dry_run:
            for row in review_drafts:
                await storage.remove(
                    storage_key=document_processing.draft_storage_key(row.storage_key)
                )
                row.processing_status = "failed"
                row.processing_error = "review_expired"
                row.review_expires_at = None

        if dry_run:
            audit_result = await db.execute(
                select(func.count()).select_from(DocumentFileAudit).where(
                    DocumentFileAudit.created_at <= audit_cutoff
                )
            )
            deleted_audit_logs = audit_result.scalar_one()
        else:
            audit_result = await db.execute(
                delete(DocumentFileAudit).where(DocumentFileAudit.created_at <= audit_cutoff)
            )
            deleted_audit_logs = audit_result.rowcount or 0
            await db.commit()

    return CleanupResult(
        expired_review_drafts=len(review_drafts),
        expired_unapproved_files=len(unapproved),
        deleted_audit_logs=deleted_audit_logs,
    )
