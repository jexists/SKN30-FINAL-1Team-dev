"""기존 보고서 RAG 문맥의 임베딩을 채운다. 기본은 건수 조회, --apply일 때만 저장한다."""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import func, or_, select, update

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.content import ReportContextChunk
from app.services import embeddings


async def run(team_id: UUID, apply: bool, batch_size: int) -> None:
    if not settings.embedding_configured:
        raise SystemExit("임베딩 공급자·모델·차원을 먼저 설정하세요.")
    sessions = get_sessionmaker()
    base = select(ReportContextChunk).where(
        ReportContextChunk.team_id == team_id,
        or_(
            ReportContextChunk.embedding_vector.is_(None),
            ReportContextChunk.embedding_model != embeddings.model_identity(),
        ),
    )
    async with sessions() as db:
        count = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    print(f"pending_report_contexts={count}; apply={apply}")
    if not apply:
        return
    cursor = None
    processed = 0
    while True:
        async with sessions() as db:
            statement = base.order_by(ReportContextChunk.report_submission_id).limit(batch_size)
            if cursor is not None:
                statement = statement.where(ReportContextChunk.report_submission_id > cursor)
            rows = (await db.execute(statement)).scalars().all()
            if not rows:
                break
            vectors = await embeddings.embed([row.content for row in rows])
            for row, vector in zip(rows, vectors, strict=True):
                await db.execute(
                    update(ReportContextChunk)
                    .where(
                        ReportContextChunk.report_submission_id == row.report_submission_id,
                        ReportContextChunk.content == row.content,
                    )
                    .values(
                        embedding_vector=vector,
                        embedding_model=embeddings.model_identity(),
                    )
                )
            await db.commit()
            cursor = rows[-1].report_submission_id
            processed += len(rows)
            print(f"processed_report_contexts={processed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=32, choices=range(1, 129))
    args = parser.parse_args()
    asyncio.run(run(args.team_id, args.apply, args.batch_size))
