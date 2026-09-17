"""미팅이 다루는 상품과, 연결 조건에 걸리는 자료실 문서를 찾는다.

브리핑 입력을 만드는 쪽(``contract_schedule_snapshots``)과 입력 지문을 계산하는 쪽
(``briefing_refresh``)이 "이 미팅이 무슨 상품을 다루는가", "그 범위에 어떤 자료가
붙어 있는가"를 똑같은 규칙으로 답해야 해서 여기 한 번만 두었다. 한쪽만 규칙이 달라지면
브리핑에 실린 자료와 "재생성 필요" 판단에 쓰는 자료가 어긋난다.

RAG 검색은 하지 않는다 — 연결 관계만 본다.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Document
from app.models.content import File as FileRow
from app.models.crm import Activity
from app.models.sales import Product, SalesDeal, SalesDealItem
from app.services import document_processing


async def product_ids(db: AsyncSession, *, team_id: UUID, activity: Activity) -> set[UUID]:
    """딜의 대표 상품과 견적 품목만 조회한다. 일정에만 연결된 상품은 제외한다."""
    collected: set[UUID] = set()
    if activity.sales_deal_id is None:
        return collected

    return await product_ids_for_deals(
        db, team_id=team_id, sales_deal_ids=[activity.sales_deal_id]
    )


async def product_ids_for_deals(
    db: AsyncSession, *, team_id: UUID, sales_deal_ids: list[UUID]
) -> set[UUID]:
    """여러 후보 딜의 대표 상품과 견적 품목을 한 번에 모은다."""
    collected: set[UUID] = set()
    if not sales_deal_ids:
        return collected

    deal_product_ids = (
        await db.execute(
            select(SalesDeal.product_id).where(
                SalesDeal.id.in_(sales_deal_ids),
                SalesDeal.team_id == team_id,
                SalesDeal.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    collected.update(product_id for product_id in deal_product_ids if product_id is not None)

    item_product_ids = (
        (
            await db.execute(
                select(SalesDealItem.product_id)
                .join(SalesDeal, SalesDeal.id == SalesDealItem.sales_deal_id)
                .where(
                    SalesDealItem.sales_deal_id.in_(sales_deal_ids),
                    SalesDeal.team_id == team_id,
                    SalesDeal.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    collected.update(item_product_ids)
    return collected


async def mentioned_product_ids(
    db: AsyncSession, *, team_id: UUID, values: Any
) -> set[UUID]:
    """확정 보고서에 정확한 상품명이 등장하면 그 상품 자료 범위도 연다."""
    text = json.dumps(values, ensure_ascii=False).casefold()
    if not text:
        return set()
    products = (
        await db.execute(
            select(Product.id, Product.name).where(
                Product.team_id == team_id,
                Product.active.is_(True),
            )
        )
    ).all()
    # ponytail: 상품 별칭은 실제 누락 사례가 생길 때 추가한다.
    return {
        product_id
        for product_id, name in products
        if (key := name.strip().casefold()) and key in text
    }


async def list_documents(
    db: AsyncSession, *, team_id: UUID, scopes: list[Any], member=None
) -> list[dict[str, object]]:
    """연결 조건에 걸리는 문서를 완료된 파일 하나씩으로 추린다.

    처리가 끝나지 않은 파일은 내용을 읽을 수 없어 근거로 쓸 수 없으므로 제외한다.
    """
    if not scopes:
        return []
    rows = (
        await db.execute(
            select(Document, FileRow)
            .join(FileRow, FileRow.document_id == Document.id)
            .where(
                Document.team_id == team_id,
                *document_processing.document_access(member),
                Document.deleted_at.is_(None),
                FileRow.processing_status == "completed",
                or_(*scopes),
            )
            # 예전 자료에 여러 행이 남아 있어, 문서마다 첫 행만 담도록 정렬해 둔다.
            .order_by(
                Document.created_at.desc(),
                Document.id,
                FileRow.version_no.desc().nullslast(),
                FileRow.uploaded_at.desc(),
                FileRow.id.desc(),
            )
        )
    ).all()

    documents: dict[UUID, dict[str, object]] = {}
    for document, file_row in rows:
        if document.id in documents:
            continue
        documents[document.id] = {
            "document_id": str(document.id),
            "document_no": document.document_no,
            "category_code": document.category_code,
            "title": document.title,
            "file_id": str(file_row.id),
            "file_name": file_row.file_name,
            # 자료요약 Agent 가 저장해 둔 요약. processing_status 가 completed 인 행만
            # 담으므로 승인 전 초안이 새어 나가지 않는다.
            "summary_markdown": file_row.summary_markdown,
            "uploaded_at": file_row.uploaded_at.isoformat(),
        }
    return list(documents.values())
