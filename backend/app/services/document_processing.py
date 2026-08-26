"""자료요약 Agent의 비동기 처리와 RAG 조회."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import document_summary
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.content import Document, DocumentChunk
from app.models.content import File as FileRow
from app.services import embeddings, storage
from app.services.document_extraction import ExtractionError, extract_document
from app.services.llm import LLMError
from app.services.ocr import OcrError


def _safe_error(error: Exception) -> str:
    value = str(error)
    return value if value and len(value) <= 120 else type(error).__name__


async def _mark_failed(file_id: UUID, error: Exception) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = (
            await session.execute(select(FileRow).where(FileRow.id == file_id))
        ).scalar_one_or_none()
        if row is None:
            return
        row.processing_status = "failed"
        row.processing_error = _safe_error(error)
        row.processed_at = datetime.now(UTC)
        await session.commit()


async def execute(file_id: UUID) -> None:
    """원본 파일을 추출·요약·청크화한다. 요청 세션과 분리해 실행한다."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(
            select(FileRow, Document.team_id)
            .join(Document, Document.id == FileRow.document_id)
            .where(FileRow.id == file_id)
        )
        result_row = result.one_or_none()
        if result_row is None:
            return
        row, team_id = result_row
        if row.document_id is None:
            return
        source = {
            "file_name": row.file_name,
            "media_type": row.media_type,
            "storage_key": row.storage_key,
            "document_id": row.document_id,
            "team_id": team_id,
        }
        await session.commit()

    try:
        content = await storage.download(storage_key=source["storage_key"])
        try:
            extracted = extract_document(
                file_name=source["file_name"],
                media_type=source["media_type"],
                content=content,
            )
        except ExtractionError as error:
            if str(error) not in {"ocr_required", "ocr_provider_required"}:
                raise
            from app.services import ocr

            source_url = None
            if settings.ocr_provider == "runpod":
                try:
                    source_url = await storage.signed_url(
                        storage_key=source["storage_key"],
                        expires_in=settings.ocr_runpod_signed_url_expires_seconds,
                    )
                except storage.StorageError:
                    # 서명 URL을 만들 수 없는 테스트·로컬 환경에서는 작은 파일만 inline 전송한다.
                    source_url = None
            extracted = await ocr.extract_document(
                file_name=source["file_name"],
                media_type=source["media_type"],
                content=content,
                source_url=source_url,
            )
        summary = await document_summary.run(
            document_summary.input_snapshot(
                file_name=source["file_name"],
                media_type=source["media_type"],
                extracted=extracted,
            )
        )
        chunk_values = document_summary.chunks(
            extracted.markdown,
            pages=extracted.payload.get("pages"),
        )
        vectors: list[list[float]] | None = None
        embedding_error: str | None = None
        if chunk_values:
            if settings.embedding_configured:
                try:
                    vectors = await embeddings.embed([item["content"] for item in chunk_values])
                except embeddings.EmbeddingError as error:
                    # 문서 처리 자체는 보존하고, 임베딩이 없으면 키워드 RAG로 대체한다.
                    embedding_error = _safe_error(error)

        payload = dict(extracted.payload)
        payload.update(
            {
                "file_name": source["file_name"],
                "media_type": source["media_type"],
                "extractor_version": "document_extraction.v1",
            }
        )
        summary_payload = summary.model_dump()
        if embedding_error:
            summary_payload["embedding_status"] = embedding_error

        async with sessionmaker() as session:
            row = (
                await session.execute(
                    select(FileRow).where(FileRow.id == file_id).with_for_update(of=FileRow)
                )
            ).scalar_one_or_none()
            if row is None:
                return
            await session.execute(delete(DocumentChunk).where(DocumentChunk.file_id == file_id))
            row.extracted_text = extracted.plain_text
            row.extracted_markdown = extracted.markdown
            row.extracted_payload = payload
            row.summary_markdown = _summary_markdown(summary)
            row.summary_payload = summary_payload
            row.processing_error = None
            row.processing_status = "completed"
            row.processed_at = datetime.now(UTC)
            for index, item in enumerate(chunk_values):
                session.add(
                    DocumentChunk(
                        id=uuid4(),
                        team_id=source["team_id"],
                        document_id=row.document_id,
                        file_id=row.id,
                        chunk_no=index,
                        page_start=item.get("page_start"),
                        page_end=item.get("page_end"),
                        section=item.get("section"),
                        content=item["content"],
                        metadata_json={
                            "file_name": source["file_name"],
                            "source_type": payload.get("source_type"),
                        },
                        embedding=None if vectors is None else vectors[index],
                    )
                )
            await session.commit()
    except (
        ExtractionError,
        LLMError,
        OcrError,
        storage.StorageError,
        embeddings.EmbeddingError,
    ) as error:
        await _mark_failed(file_id, error)
    except Exception as error:
        await _mark_failed(file_id, error)


def _summary_markdown(summary: document_summary.DocumentSummaryOutput) -> str:
    lines = ["# 문서 요약", "", "## 핵심 요약", summary.summary or "내용 없음", ""]
    for title, values in (
        ("주요 내용", summary.key_points),
        ("영업 참고사항", summary.sales_relevance),
        ("리스크", summary.risk_flags),
    ):
        lines.extend([f"## {title}", ""])
        lines.extend(f"- {value}" for value in values) if values else lines.append("- 없음")
        lines.append("")
    if summary.extracted_fields:
        lines.extend(["## 추출 필드", ""])
        lines.extend(f"- {key}: {value}" for key, value in summary.extracted_fields.items())
        lines.append("")
    if summary.source_refs:
        lines.extend(["## 출처", ""])
        lines.extend(f"- {value}" for value in summary.source_refs)
    return "\n".join(lines).strip() + "\n"


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[\w가-힣]{2,}", value)}


async def search_chunks(
    db: AsyncSession,
    *,
    team_id: UUID,
    query: str,
    limit: int = 5,
    document_id: UUID | None = None,
    sales_deal_id: UUID | None = None,
) -> list[tuple[DocumentChunk, float]]:
    """임베딩이 있으면 코사인, 없으면 출처 보존 키워드 점수로 검색한다."""
    conditions = [DocumentChunk.team_id == team_id]
    if document_id is not None:
        conditions.append(DocumentChunk.document_id == document_id)
    statement = select(DocumentChunk)
    if sales_deal_id is not None:
        statement = statement.join(Document, Document.id == DocumentChunk.document_id)
        conditions.append(Document.sales_deal_id == sales_deal_id)
    rows = (await db.execute(statement.where(*conditions))).scalars().all()
    query_vector: list[float] | None = None
    if settings.embedding_configured and rows:
        try:
            query_vector = (await embeddings.embed([query]))[0]
        except embeddings.EmbeddingError:
            query_vector = None
    query_tokens = _tokens(query)
    scored: list[tuple[DocumentChunk, float]] = []
    for row in rows:
        if query_vector is not None and isinstance(row.embedding, list):
            score = embeddings.cosine_similarity(query_vector, row.embedding)
        else:
            content_tokens = _tokens(row.content)
            score = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
        if score > 0:
            scored.append((row, score))
    scored.sort(key=lambda item: (-item[1], item[0].chunk_no))
    return scored[:limit]
