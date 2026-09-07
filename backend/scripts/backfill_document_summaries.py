"""현재 자료요약 프롬프트로 기존 자료실 요약을 다시 생성하는 관리 명령.

문서마다 자료실이 보여 주는 파일의 요약만 대상으로 합니다. 예전에 쌓여 남은 행은
드로어에 나오지 않고, 다시 처리하면 LLM·OCR 비용만 늘어납니다.

먼저 대상만 확인합니다.
    uv run python scripts/backfill_document_summaries.py --dry-run

확인한 뒤 실제 재처리를 실행합니다.
    uv run python scripts/backfill_document_summaries.py

특정 팀만 또는 일부만 처리할 수도 있습니다.
    uv run python scripts/backfill_document_summaries.py --team-id <TEAM_ID> --limit 3
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from uuid import UUID, uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.models.content import (  # noqa: E402
    Document,
    DocumentFileAudit,
)
from app.models.content import File as FileRow  # noqa: E402
from app.services import document_processing  # noqa: E402


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"정수가 아니다: {value}") from None
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"1 이상이어야 한다: {value}")
    return parsed


async def _targets(team_id: UUID | None, limit: int | None) -> list[UUID]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        statement = (
            select(FileRow.id)
            .join(Document, Document.id == FileRow.document_id)
            .where(
                FileRow.document_id.is_not(None),
                FileRow.processing_status == "completed",
                FileRow.summary_markdown.is_not(None),
                document_processing.latest_completed_file(),
            )
            .order_by(FileRow.uploaded_at, FileRow.id)
        )
        if team_id is not None:
            statement = statement.where(Document.team_id == team_id)
        if limit is not None:
            statement = statement.limit(limit)
        return list((await session.execute(statement)).scalars().all())


async def _mark_processing(file_id: UUID) -> bool:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(
            select(FileRow, Document.team_id)
            .join(Document, Document.id == FileRow.document_id)
            .where(FileRow.id == file_id)
            .with_for_update(of=FileRow)
        )
        row_and_team = result.one_or_none()
        if row_and_team is None:
            return False
        row, team_id = row_and_team
        if row.processing_status != "completed":
            return False

        row.processing_status = "processing"
        row.processing_error = None
        row.review_expires_at = None
        row.unapproved_expires_at = None
        row.approved_by_member_id = None
        row.approved_at = None
        session.add(
            DocumentFileAudit(
                id=uuid4(),
                team_id=team_id,
                document_id=row.document_id,
                file_id=row.id,
                action_code="summary_reprocess_requested",
                # 관리 명령은 별도 사용자 세션이 없으므로 원본 업로더를 실행 주체로 남긴다.
                actor_member_id=row.uploaded_by_member_id,
                before_snapshot={"processing_status": "completed"},
                after_snapshot={"processing_status": "processing"},
            )
        )
        await session.commit()
        return True


async def _status(file_id: UUID) -> str | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        return (
            await session.execute(select(FileRow.processing_status).where(FileRow.id == file_id))
        ).scalar_one_or_none()


async def main(*, dry_run: bool, team_id: UUID | None, limit: int | None) -> int:
    if not dry_run and not settings.llm_configured:
        print("LLM 설정이 없어 아무것도 하지 않는다. .env 의 LLM_* 값을 확인하라.")
        return 1
    if not dry_run and not settings.storage_configured:
        print("Storage 설정이 없어 아무것도 하지 않는다. .env 의 SUPABASE_* 값을 확인하라.")
        return 1

    targets = await _targets(team_id, limit)
    print(f"자료실이 보여 주는 파일의 기존 요약 {len(targets)}건")
    if dry_run:
        print("--dry-run 이라 실행하지 않았다.")
        return 0

    completed = 0
    failed = 0
    for index, file_id in enumerate(targets, start=1):
        print(f"[{index}/{len(targets)}] 재처리 중")
        if not await _mark_processing(file_id):
            failed += 1
            continue
        await document_processing.execute(file_id)
        if await _status(file_id) == "completed":
            completed += 1
        else:
            failed += 1

    print(f"완료 {completed}건 · 실패 {failed}건")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="대상만 세고 실행하지 않는다")
    parser.add_argument("--team-id", type=UUID, help="특정 팀만 처리한다")
    parser.add_argument("--limit", type=_positive_int, help="앞에서 N건만 처리한다")
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(main(dry_run=args.dry_run, team_id=args.team_id, limit=args.limit))
    )
