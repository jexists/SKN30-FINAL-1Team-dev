"""브리핑 실행에 고정한 제품 자료·RAG 근거·C/S의 화면 표현."""

from uuid import UUID

from sqlalchemy import select

from app.models.content import Document, File
from app.models.crm import SupportRequest
from app.services.document_processing import document_access


async def visible_documents(db, *, team_id: UUID, context: dict, member=None) -> dict:
    products = context.get("product_documents") or []
    sources = context.get("sources") or []
    summaries = {item["file_id"]: item for item in context.get("summaries") or []}
    differences_by_document: dict[str, list[dict]] = {}
    for difference in context.get("contract_differences") or []:
        document_id = str(difference.get("document_id") or "")
        if document_id:
            differences_by_document.setdefault(document_id, []).append(difference)
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
                "contract_differences": differences_by_document.get(key, []),
            },
        )
        item["excerpts"].append(
            {
                "content": source.get("content", ""),
                "chunk_id": source.get("chunk_id"),
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


async def visible_support_requests(db, *, member, snapshot: dict) -> list[dict]:
    """브리핑이 읽은 C/S 중 지금도 볼 수 있는 건. 화면은 이 목록으로 C/S 상세 링크를 단다.

    제목·상태는 실행 당시가 아니라 지금 값을 보여준다. 지운 건과 권한 밖의 건은 C/S 화면과
    같은 규칙(``app.api.support._scope``)으로 걸러낸다. 순서는 브리핑이 읽은 순서를 따른다.
    """
    ids = []
    for item in snapshot.get("support_requests") or []:
        try:
            ids.append(UUID(str(item["id"])))
        except (KeyError, ValueError, TypeError):
            continue
    if not ids:
        return []
    conditions = [
        SupportRequest.id.in_(ids),
        SupportRequest.team_id == member.team_id,
        SupportRequest.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(SupportRequest.assignee_member_id == member.id)
    rows = (
        await db.execute(
            select(
                SupportRequest.id,
                SupportRequest.title,
                SupportRequest.status_code,
                SupportRequest.is_urgent,
            ).where(*conditions)
        )
    ).all()
    current = {row[0]: row for row in rows}
    return [
        {
            "id": str(request_id),
            "title": current[request_id][1],
            "status_code": current[request_id][2],
            "is_urgent": current[request_id][3],
        }
        for request_id in ids
        if request_id in current
    ]
