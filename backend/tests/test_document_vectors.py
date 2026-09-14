"""실제 pgvector 검색. 전용 로컬 DB에서만 활성화하며 트랜잭션을 롤백한다."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.models.content import DocumentChunk
from app.services import document_processing, embeddings
from app.services.briefing_documents import visible_documents


@pytest.mark.anyio
async def test_real_pgvector_hybrid_scope_and_saved_evidence(monkeypatch):
    if not settings.run_integration_tests:
        pytest.skip("전용 로컬 pgvector DB에서 명시적으로 실행")
    from sqlalchemy.engine import make_url

    url = make_url(settings.async_database_url)
    assert url.host == "127.0.0.1" and url.port == 55439
    assert url.database == "salesluv_rag_test"
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                for statement in (
                    "CREATE TABLE public.team (id uuid PRIMARY KEY)",
                    "CREATE TABLE public.member (id uuid PRIMARY KEY, "
                    "team_id uuid, role_code text)",
                    "CREATE TABLE public.sales_deal (id uuid PRIMARY KEY, "
                    "customer_company_id uuid)",
                    "CREATE TABLE public.document (id uuid PRIMARY KEY, team_id uuid, "
                    "sales_deal_id uuid, customer_company_id uuid, product_id uuid, "
                    "deleted_at timestamptz, created_by_member_id uuid)",
                    "CREATE TABLE public.file (id uuid PRIMARY KEY, document_id uuid, "
                    "processing_status text, version_no integer)",
                    "CREATE TABLE public.document_chunk (id uuid PRIMARY KEY, team_id uuid, "
                    "document_id uuid, file_id uuid, chunk_no integer, page_start integer, "
                    "page_end integer, section text, content text, "
                    "metadata jsonb, embedding jsonb, "
                    "created_at timestamptz DEFAULT now())",
                ):
                    await connection.execute(text(statement))
                migration = (
                    Path(__file__).parents[1] / "sql/20260912_0031_document_vectors.sql"
                ).read_text()
                migration = "\n".join(
                    line for line in migration.splitlines() if not line.startswith("--")
                )
                for statement in migration.split(";"):
                    if statement.strip() and statement.strip() not in {"BEGIN", "COMMIT"}:
                        await connection.execute(text(statement))
                monkeypatch.setattr(settings, "embedding_provider", "local")
                monkeypatch.setattr(settings, "embedding_dimensions", 384)
                vector = [1.0] + [0.0] * 383

                async def embed(_texts):
                    return [vector]

                monkeypatch.setattr(embeddings, "embed", embed)
                team, company, product = uuid4(), uuid4(), uuid4()
                owner, manager, peer = uuid4(), uuid4(), uuid4()
                for member_id, role in ((owner, "member"), (manager, "manager"), (peer, "member")):
                    await connection.execute(
                        text("INSERT INTO member VALUES (:id, :team, :role)"),
                        {"id": member_id, "team": team, "role": role},
                    )
                member = SimpleNamespace(id=owner, team_id=team, role_code="member")
                db = AsyncSession(bind=connection, expire_on_commit=False)
                records = []
                # Relevant semantic match has no overlapping query token.
                for kind in (
                    "semantic",
                    "keyword",
                    "other_team",
                    "deleted",
                    "unrelated",
                    "old",
                    "wrong_model",
                    "peer",
                    "other_dimensions",
                ):
                    doc, file = uuid4(), uuid4()
                    doc_team = uuid4() if kind == "other_team" else team
                    await connection.execute(
                        text(
                            "INSERT INTO document VALUES "
                            "(:id, :team, NULL, :company, :product, :deleted, :creator)"
                        ),
                        {
                            "id": doc,
                            "team": doc_team,
                            "company": None if kind in {"semantic", "unrelated"} else company,
                            "product": product if kind == "semantic" else None,
                            "deleted": None,
                            "creator": peer
                            if kind == "peer"
                            else manager
                            if kind == "semantic"
                            else owner,
                        },
                    )
                    if kind == "deleted":
                        await connection.execute(
                            text("UPDATE document SET deleted_at=now() WHERE id=:id"), {"id": doc}
                        )
                    await connection.execute(
                        text("INSERT INTO file VALUES (:id, :doc, 'completed', 1)"),
                        {"id": file, "doc": doc},
                    )
                    if kind == "old":
                        await connection.execute(
                            text("INSERT INTO file VALUES (:id, :doc, 'completed', 2)"),
                            {"id": uuid4(), "doc": doc},
                        )
                    row = DocumentChunk(
                        id=uuid4(),
                        team_id=doc_team,
                        document_id=doc,
                        file_id=file,
                        chunk_no=0,
                        page_start=2,
                        page_end=2,
                        section=None,
                        content="대금 결제" if kind == "keyword" else "검수 이후 입금",
                        metadata_json={},
                        embedding=None,
                        embedding_vector=[0.0, 1.0] + [0.0] * 382 if kind == "keyword" else vector,
                        embedding_model="other:model:384"
                        if kind == "wrong_model"
                        else embeddings.model_identity(),
                    )
                    db.add(row)
                    if kind == "other_dimensions":
                        row.embedding_vector = [1.0] + [0.0] * 1535
                        row.embedding_model = "other:model:1536"
                    records.append((kind, row))
                await db.flush()
                info = {}
                matches = await document_processing.search_chunks(
                    db,
                    team_id=team,
                    query="대금 결제",
                    customer_company_id=company,
                    product_ids={product},
                    search_info=info,
                    member=member,
                )
                found = {row.id for row, _ in matches}
                assert found == {row.id for kind, row in records if kind in {"semantic", "keyword"}}
                assert info == {"method": "hybrid", "status": "completed"}
                # Saved excerpts are filtered again on read after a document is deleted.
                context = {
                    "sources": [
                        {
                            "document_id": str(row.document_id),
                            "file_id": str(row.file_id),
                            "file_name": "합성.pdf",
                            "content": row.content,
                        }
                        for _, row in records
                    ],
                    "search": info,
                }
                shown = await visible_documents(db, team_id=team, context=context, member=member)
                assert not {
                    str(row.document_id)
                    for kind, row in records
                    if kind in {"other_team", "deleted", "peer"}
                } & {item["document_id"] for item in shown["related"]}

                async def unavailable(_texts):
                    raise embeddings.EmbeddingError("synthetic_unavailable")

                monkeypatch.setattr(embeddings, "embed", unavailable)
                fallback = await document_processing.search_chunks(
                    db,
                    team_id=team,
                    query="대금 결제",
                    customer_company_id=company,
                    search_info=info,
                )
                assert len(fallback) == 1 and fallback[0][0].content == "대금 결제"
                assert info["status"] == "embedding_unavailable"
                await db.close()
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("vector", [[0.0] * 384, [float("nan")] * 384, [1.0], [True] * 384])
def test_rejects_invalid_embeddings(vector, monkeypatch):
    monkeypatch.setattr(settings, "embedding_dimensions", 384)
    with pytest.raises(embeddings.EmbeddingError):
        embeddings.validate_vectors([vector], 1)
