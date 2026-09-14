"""기존 청크의 임베딩만 생성한다. 기본은 건수 조회, --apply일 때만 저장한다."""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import func, or_, select, update

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.content import Document, DocumentChunk, File
from app.services import document_processing, embeddings


async def run(team_id: UUID, apply: bool, batch_size: int) -> None:
    if not settings.embedding_configured:
        raise SystemExit("임베딩 공급자·모델·차원을 먼저 설정하세요.")
    sessions = get_sessionmaker()
    conditions = [
        DocumentChunk.team_id == team_id,
        Document.team_id == team_id,
        Document.deleted_at.is_(None),
        File.processing_status == "completed",
        document_processing.latest_completed_file(),
        or_(
            DocumentChunk.embedding_vector.is_(None),
            DocumentChunk.embedding_model != embeddings.model_identity(),
        ),
    ]
    base = (
        select(DocumentChunk)
        .join(File, File.id == DocumentChunk.file_id)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(*conditions)
    )
    async with sessions() as db:
        count = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    print(f"pending_chunks={count}; apply={apply}")
    if not apply:
        return
    cursor = None
    processed = 0
    while True:
        async with sessions() as db:
            statement = base.order_by(DocumentChunk.id).limit(batch_size)
            if cursor is not None:
                statement = statement.where(DocumentChunk.id > cursor)
            rows = (await db.execute(statement)).scalars().all()
            if not rows:
                break
            vectors = await embeddings.embed([row.content for row in rows])
            for row, vector in zip(rows, vectors, strict=True):
                # Concurrent reprocessing/deletion must not resurrect or overwrite a new chunk.
                await db.execute(
                    update(DocumentChunk)
                    .where(
                        DocumentChunk.id == row.id,
                        DocumentChunk.team_id == team_id,
                        DocumentChunk.content == row.content,
                    )
                    .values(embedding_vector=vector, embedding_model=embeddings.model_identity())
                )
            await db.commit()
            cursor = rows[-1].id
            processed += len(rows)
            print(f"processed_chunks={processed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32, choices=range(1, 129))
    args = parser.parse_args()
    asyncio.run(run(args.team_id, args.apply, args.batch_size))
