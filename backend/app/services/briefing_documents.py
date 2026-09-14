"""브리핑 실행에 고정한 제품 자료와 RAG 근거의 화면 표현."""

from uuid import UUID

from sqlalchemy import select

from app.models.content import Document, File
from app.services.document_processing import document_access


async def visible_documents(db, *, team_id: UUID, context: dict, member=None) -> dict:
    products = context.get("product_documents") or []
    sources = context.get("sources") or []
    summaries = {item["file_id"]: item for item in context.get("summaries") or []}
    file_ids = set()
    for item in [*products, *sources]:
        try:
            file_ids.add(UUID(str(item["file_id"])))
        except (KeyError, ValueError, TypeError):
            continue
    visible = set()
    if file_ids:
        visible = set(
            (
                await db.execute(
                    select(File.id, Document.id)
                    .join(Document, Document.id == File.document_id)
                    .where(
                        File.id.in_(file_ids),
                        Document.team_id == team_id,
                        Document.deleted_at.is_(None),
                        *document_access(member),
                        File.processing_status == "completed",
                    )
                )
            ).all()
        )

    def allowed(item):
        try:
            return (UUID(str(item["file_id"])), UUID(str(item["document_id"]))) in visible
        except (KeyError, ValueError, TypeError):
            return False

    related = {}
    for source in sources:
        if not allowed(source):
            continue
        key = str(source["document_id"])
        item = related.setdefault(
            key,
            {
                "document_id": key,
                "file_id": str(source["file_id"]),
                "file_name": source.get("file_name", "문서"),
                "summary_markdown": summaries.get(str(source["file_id"]), {}).get(
                    "summary_markdown"
                ),
                "excerpts": [],
            },
        )
        item["excerpts"].append(
            {
                "content": source.get("content", ""),
                "page_start": source.get("page_start"),
                "page_end": source.get("page_end"),
            }
        )
    return {
        "related": list(related.values()),
        "product": [
            {
                key: item.get(key)
                for key in ("document_id", "file_id", "file_name", "summary_markdown")
            }
            for item in products
            if allowed(item)
        ],
        "search": context.get("search") or {"method": "unknown", "status": "legacy"},
    }
