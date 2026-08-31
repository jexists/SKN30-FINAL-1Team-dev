"""개인정보 없는 합성 문서로 Storage·OCR·요약·승인·RAG를 점검한다.

실행 시 합성 문서를 Supabase에 잠시 저장하고, 검증이 끝나면 해당 문서·파일·청크와
Storage 객체를 모두 삭제한다. 실제 문서나 사용자 계정 정보는 사용하지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_sessionmaker
from app.models.content import Document, DocumentChunk, DocumentFileAudit
from app.models.content import File as FileRow
from app.models.workspace import Member, Team
from app.services import document_processing, storage


def _synthetic_pdf() -> bytes:
    image = Image.new("RGB", (1_600, 700), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for index, line in enumerate(
        (
            "SALESLUV SYNTHETIC CONTRACT TEST",
            "Product: Document Summary Module",
            "Contract period: 2026-01-01 to 2026-12-31",
            "Contract amount: 1000000 KRW",
            "Payment terms: after acceptance inspection",
        )
    ):
        draw.text((80, 80 + index * 100), line, fill="black", font=font)
    output = BytesIO()
    image.save(output, format="PDF", resolution=150.0)
    return output.getvalue()


async def _select_actor(sessionmaker) -> tuple[UUID, UUID]:
    async with sessionmaker() as session:
        selected = (
            await session.execute(
                select(Team.id, Member.id)
                .join(Member, Member.team_id == Team.id)
                .where(Member.active.is_(True))
                .limit(1)
            )
        ).one_or_none()
    if selected is None:
        raise RuntimeError("no_active_test_member")
    return selected


async def run() -> dict[str, object]:
    sessionmaker = get_sessionmaker()
    document_id, file_id = uuid4(), uuid4()
    team_id = member_id = storage_key = None
    try:
        team_id, member_id = await _select_actor(sessionmaker)
        async with sessionmaker() as session:
            session.add(
                Document(
                    id=document_id,
                    team_id=team_id,
                    created_by_member_id=member_id,
                    document_no=f"SYNTHETIC-E2E-{document_id.hex[:8]}",
                    category_code="contract",
                    title="Synthetic OCR RAG E2E Test",
                    description="Temporary synthetic test data",
                    tags=["synthetic", "e2e"],
                )
            )
            await session.commit()

        content = _synthetic_pdf()
        storage_key = storage.build_storage_key(team_id, ".pdf")
        await storage.upload(
            storage_key=storage_key,
            content=content,
            media_type="application/pdf",
        )
        async with sessionmaker() as session:
            session.add(
                FileRow(
                    id=file_id,
                    report_id=None,
                    document_id=document_id,
                    version_no=1,
                    file_name="synthetic-contract-e2e.pdf",
                    storage_key=storage_key,
                    media_type="application/pdf",
                    byte_size=len(content),
                    processing_status="uploaded",
                    extracted_text=None,
                    extracted_markdown=None,
                    extracted_payload=None,
                    summary_markdown=None,
                    summary_payload=None,
                    processing_error=None,
                    processed_at=None,
                    review_expires_at=None,
                    unapproved_expires_at=datetime.now(UTC),
                    approved_by_member_id=None,
                    approved_at=None,
                    uploaded_by_member_id=member_id,
                    note="temporary synthetic E2E test",
                )
            )
            await session.flush()
            session.add(
                DocumentFileAudit(
                    id=uuid4(),
                    team_id=team_id,
                    document_id=document_id,
                    file_id=file_id,
                    action_code="file_uploaded",
                    actor_member_id=member_id,
                    before_snapshot=None,
                    after_snapshot={"synthetic": True},
                )
            )
            await session.commit()

        await document_processing.execute(file_id)
        async with sessionmaker() as session:
            row = (await session.execute(select(FileRow).where(FileRow.id == file_id))).scalar_one()
            draft = await document_processing.load_review_draft(row.storage_key)
            review_ok = (
                row.processing_status == "review_required"
                and bool(draft["extracted_text"])
                and bool(draft["summary_markdown"])
            )
            before_approval_matches = await document_processing.search_chunks(
                session,
                team_id=team_id,
                query="contract amount payment terms",
                document_id=document_id,
            )
            await document_processing.approve_review(
                session,
                row=row,
                team_id=team_id,
                approved_by_member_id=member_id,
            )
            await session.commit()

        async with sessionmaker() as session:
            row = (await session.execute(select(FileRow).where(FileRow.id == file_id))).scalar_one()
            chunks = (
                (
                    await session.execute(
                        select(DocumentChunk).where(DocumentChunk.file_id == file_id)
                    )
                )
                .scalars()
                .all()
            )
            matches = await document_processing.search_chunks(
                session,
                team_id=team_id,
                query="contract amount payment terms",
                document_id=document_id,
            )
            return {
                "status": "passed"
                if review_ok
                and not before_approval_matches
                and row.processing_status == "completed"
                and chunks
                and matches
                else "failed",
                "review_required_before_approval": review_ok,
                "unapproved_rag_match_count": len(before_approval_matches),
                "unapproved_excluded": not before_approval_matches,
                "completed_after_approval": row.processing_status == "completed",
                "chunk_count": len(chunks),
                "embedding_present": bool(chunks and isinstance(chunks[0].embedding, list)),
                "rag_match_count": len(matches),
                "page_metadata_present": bool(
                    chunks and chunks[0].page_start == 1 and chunks[0].page_end == 1
                ),
            }
    finally:
        if storage_key:
            await storage.remove(storage_key=storage_key)
            await storage.remove(storage_key=document_processing.draft_storage_key(storage_key))
        if team_id:
            async with sessionmaker() as session:
                await session.execute(
                    delete(DocumentFileAudit).where(DocumentFileAudit.document_id == document_id)
                )
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
                )
                await session.execute(delete(FileRow).where(FileRow.id == file_id))
                await session.execute(delete(Document).where(Document.id == document_id))
                await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="store_true",
        help="합성 테스트 데이터를 저장하고 검증 후 자동 삭제한다.",
    )
    args = parser.parse_args()
    if not args.run:
        parser.error("합성 데이터의 외부 저장을 허용하려면 --run을 지정하세요.")
    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
