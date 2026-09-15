"""미팅 브리핑이 쓰는 확정 보고서 직접 조회와 과거 RAG 검색."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Text, and_, case, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.content import Report, ReportContextChunk, ReportDeal, ReportSubmission
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.services import embeddings
from app.services.agent_logging import log_agent_error


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[\w가-힣]{2,}", value)}


def _company_scope(customer_company_id: UUID, team_id: UUID):
    linked_report_ids = (
        select(ReportDeal.report_id)
        .join(SalesDeal, SalesDeal.id == ReportDeal.sales_deal_id)
        .where(
            SalesDeal.team_id == team_id,
            SalesDeal.customer_company_id == customer_company_id,
            SalesDeal.deleted_at.is_(None),
        )
    )
    return or_(
        Report.customer_company_id == customer_company_id,
        Report.id.in_(linked_report_ids),
    )


def _record(report: Report, submission: ReportSubmission, *, score: float | None = None) -> dict:
    snapshot = submission.snapshot if isinstance(submission.snapshot, dict) else {}
    deals = []
    for value in snapshot.get("deals") or []:
        if not isinstance(value, dict):
            continue
        deals.append(
            {
                "sales_deal_id": value.get("sales_deal_id"),
                "title": value.get("title") or value.get("deal_title_snapshot"),
                "body": value.get("body"),
            }
        )
    output = {
        "id": str(report.id),
        "submission_id": str(submission.id),
        "source_activity_id": (
            str(report.source_activity_id) if report.source_activity_id is not None else None
        ),
        "report_date": report.report_date.isoformat(),
        "submitted_at": submission.submitted_at.isoformat(),
        "title": snapshot.get("title"),
        "meeting_shared": {
            "common_report": snapshot.get("common_body"),
            "unassigned_report": snapshot.get("unassigned_body"),
        },
        "deal_reports": deals,
    }
    if score is not None:
        output["score"] = round(float(score), 6)
    return output


def _base_statement(
    *,
    member: Member,
    customer_company_id: UUID,
):
    conditions = [
        Report.team_id == member.team_id,
        Report.report_kind == "meeting",
        Report.status_code.in_(("approved", "submitted")),
        ReportSubmission.id == Report.current_submission_id,
        _company_scope(customer_company_id, member.team_id),
    ]
    return select(Report, ReportSubmission).join(
        ReportSubmission,
        and_(
            ReportSubmission.report_id == Report.id,
            ReportSubmission.id == Report.current_submission_id,
        ),
    ).where(*conditions)


async def recent_reports(
    db: AsyncSession,
    *,
    member: Member,
    customer_company_id: UUID,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """고객사의 최신 확정 보고서 3건을 원문 구조로 읽는다."""
    rows = (
        await db.execute(
            _base_statement(
                member=member,
                customer_company_id=customer_company_id,
            )
            .order_by(Report.report_date.desc(), ReportSubmission.submitted_at.desc(), Report.id)
            .limit(limit)
        )
    ).all()
    return [_record(report, submission) for report, submission in rows]


async def reports_by_ids(
    db: AsyncSession,
    *,
    member: Member,
    customer_company_id: UUID,
    report_ids: set[UUID],
) -> list[dict[str, Any]]:
    """RAG 결과에서 고른 현재 보고서 원문을 같은 회사 범위로 다시 읽는다."""
    if not report_ids:
        return []
    rows = (
        await db.execute(
            _base_statement(
                member=member,
                customer_company_id=customer_company_id,
            ).where(Report.id.in_(report_ids))
        )
    ).all()
    return [_record(report, submission) for report, submission in rows]


async def search_historical_reports(
    db: AsyncSession,
    *,
    member: Member,
    customer_company_id: UUID,
    query: str,
    limit: int = 5,
    search_info: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """RAG 코퍼스 전체에서 중요한 보고서 문맥을 검색한다."""
    indexed = (
        await db.execute(select(func.to_regclass("public.report_context_chunk")))
    ).scalar_one_or_none()
    base = _base_statement(
        member=member,
        customer_company_id=customer_company_id,
    )
    tokens = sorted(_tokens(query))
    if indexed:
        base = base.join(
            ReportContextChunk,
            ReportContextChunk.report_submission_id == ReportSubmission.id,
        )
        content = ReportContextChunk.content
    else:
        # migration 전 개발 DB에서도 브리핑 자체는 멈추지 않는다.
        content = cast(ReportSubmission.snapshot, Text)
    if indexed:
        ts_query = func.to_tsquery("simple", " | ".join(tokens))
        keyword_score = func.ts_rank_cd(func.to_tsvector("simple", content), ts_query)
    else:
        words = func.regexp_split_to_array(func.lower(content), r"[^\w가-힣]+")
        keyword_score = sum(
            (case((literal(token) == func.any(words), 1.0), else_=0.0) for token in tokens),
            literal(0.0),
        ) / max(len(tokens), 1)
    candidate_limit = max(20, limit * 4)
    keyword_rows = []
    corpus = _base_statement(
        member=member,
        customer_company_id=customer_company_id,
    )
    if indexed:
        corpus = corpus.join(
            ReportContextChunk,
            ReportContextChunk.report_submission_id == ReportSubmission.id,
        )
    corpus_count = int(
        (
            await db.execute(select(func.count()).select_from(corpus.subquery()))
        ).scalar_one()
    )
    if tokens:
        keyword_rows = (
            await db.execute(
                base.add_columns(keyword_score.label("score"))
                .where(keyword_score > 0)
                .order_by(keyword_score.desc(), Report.report_date.desc(), Report.id)
                .limit(candidate_limit)
            )
        ).all()

    vector_rows = []
    if search_info is not None:
        search_info.update(
            method="keyword",
            status="completed",
            corpus="indexed" if indexed else "snapshot_fallback",
            corpus_count=corpus_count,
        )
    if indexed and settings.embedding_configured and query.strip():
        try:
            query_vector = (await embeddings.embed([query]))[0]
            dimensions = settings.embedding_dimensions
            distance = cast(
                ReportContextChunk.embedding_vector, Vector(dimensions)
            ).cosine_distance(query_vector)
            vector_rows = (
                await db.execute(
                    base.add_columns((1 - distance).label("score"))
                    .where(
                        func.vector_dims(ReportContextChunk.embedding_vector) == dimensions,
                        ReportContextChunk.embedding_model == embeddings.model_identity(),
                        distance <= 1 - settings.document_search_min_similarity,
                    )
                    .order_by(distance, Report.report_date.desc(), Report.id)
                    .limit(candidate_limit)
                )
            ).all()
            if search_info is not None:
                search_info["method"] = "hybrid"
        except embeddings.EmbeddingError:
            if search_info is not None:
                search_info["status"] = "embedding_unavailable"

    merged: dict[UUID, tuple[Report, ReportSubmission, float]] = {}
    for ranking in (keyword_rows, vector_rows):
        for rank, (report, submission, _score) in enumerate(ranking, 1):
            previous = merged.get(report.id, (report, submission, 0.0))[2]
            merged[report.id] = (report, submission, previous + 1 / (60 + rank))
    if not merged:
        fallback = (
            await db.execute(
                base.order_by(
                    Report.report_date.desc(), ReportSubmission.submitted_at.desc(), Report.id
                ).limit(limit)
            )
        ).all()
        if search_info is not None:
            search_info["method"] = "recent_fallback"
            search_info["retrieved_count"] = len(fallback)
        return [_record(report, submission, score=0) for report, submission in fallback]
    ranked = sorted(merged.values(), key=lambda value: (-value[2], str(value[0].id)))[:limit]
    if search_info is not None:
        search_info["retrieved_count"] = len(ranked)
    return [_record(report, submission, score=score) for report, submission, score in ranked]


async def embed_submission(submission_id: UUID) -> None:
    """DB trigger가 적재한 보고서 문맥에 선택적 의미검색 벡터를 채운다."""
    if not settings.embedding_configured:
        return
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        indexed = (
            await session.execute(select(func.to_regclass("public.report_context_chunk")))
        ).scalar_one_or_none()
        if not indexed:
            return
        chunk = (
            await session.execute(
                select(ReportContextChunk).where(
                    ReportContextChunk.report_submission_id == submission_id
                )
            )
        ).scalar_one_or_none()
        if chunk is None or chunk.embedding_model == embeddings.model_identity():
            return
        chunk.embedding_vector = (await embeddings.embed([chunk.content]))[0]
        chunk.embedding_model = embeddings.model_identity()
        chunk.indexed_at = func.now()
        await session.commit()


async def embed_submission_quietly(submission_id: UUID) -> None:
    try:
        await embed_submission(submission_id)
    except Exception as error:
        log_agent_error(
            error,
            stage="report_context.embedding",
            error_code="report_context_embedding_failed",
        )
