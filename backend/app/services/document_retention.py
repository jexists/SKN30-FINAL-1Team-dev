"""레거시 승인 대기 임시 결과와 감사 이력 정리."""

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


async def cleanup_expired(*, now: datetime | None = None, dry_run: bool = False) -> CleanupResult:
    """보관 정책이 지난 Storage 객체와 DB 이력을 정리한다.

    자동 저장된 원본·요약·RAG는 삭제하지 않는다. 구버전 승인 대기 임시 결과만
    검토 기한을 적용하고, 감사 이력은 별도 보관 기한을 적용한다.
    """
    current = now or datetime.now(UTC)
    review_cutoff = current - timedelta(days=settings.document_review_draft_retention_days)
    audit_cutoff = current - timedelta(days=settings.document_audit_log_retention_days)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        # 문서 요약은 자동 저장되며 원본은 자료실의 근거이므로, 승인 여부나
        # 처리 지연만으로 Storage 원본과 File 행을 삭제하지 않는다. 이 목록은
        # 하위 호환 결과 형식을 위해 비워 둔다.
        unapproved: list[FileRow] = []

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
        review_drafts = (
            (await db.execute(select(FileRow).where(*review_conditions))).scalars().all()
        )
        if not dry_run:
            for row in review_drafts:
                try:
                    removed = await storage.remove(
                        storage_key=document_processing.draft_storage_key(row.storage_key)
                    )
                except storage.StorageError:
                    removed = False
                if removed is False:
                    # 원본 삭제가 확인될 때까지 같은 review_required 행을
                    # 다음 정리 작업에서도 다시 선택할 수 있게 유지한다.
                    row.processing_error = "review_draft_delete_pending"
                    row.review_expires_at = current
                    continue
                row.processing_status = "failed"
                row.processing_error = "review_expired"
                row.review_expires_at = None

        if dry_run:
            audit_result = await db.execute(
                select(func.count())
                .select_from(DocumentFileAudit)
                .where(DocumentFileAudit.created_at <= audit_cutoff)
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
