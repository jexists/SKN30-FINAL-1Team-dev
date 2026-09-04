"""미팅에 관련된 자료실 문서 조회.

AI 브리핑과는 분리된 경로다. LLM 도 실행 이력(agent_run)도 거치지 않고 연결 관계만
보므로, 미팅을 열 때마다 새로 조회해도 된다 — 브리핑이 만들어진 뒤에 올라온 자료가
곧바로 보이는 것이 이 모듈이 따로 있는 이유다.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Document
from app.models.content import File as FileRow
from app.models.crm import Activity
from app.models.sales import SalesDeal, SalesDealItem
from app.services import document_processing


async def _product_ids(db: AsyncSession, *, team_id: UUID, activity: Activity) -> set[UUID]:
    """이 미팅이 다루는 상품. 미팅 자체와 딜, 그리고 딜의 견적 품목까지 본다."""
    product_ids: set[UUID] = set()
    if activity.product_id is not None:
        product_ids.add(activity.product_id)
    if activity.sales_deal_id is None:
        return product_ids

    deal_product_id = (
        await db.execute(
            select(SalesDeal.product_id).where(
                SalesDeal.id == activity.sales_deal_id,
                SalesDeal.team_id == team_id,
            )
        )
    ).scalar_one_or_none()
    if deal_product_id is not None:
        product_ids.add(deal_product_id)

    item_product_ids = (
        (
            await db.execute(
                select(SalesDealItem.product_id).where(
                    SalesDealItem.sales_deal_id == activity.sales_deal_id
                )
            )
        )
        .scalars()
        .all()
    )
    product_ids.update(item_product_ids)
    return product_ids


async def _documents(
    db: AsyncSession, *, team_id: UUID, scopes: list[Any]
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
            "document_id": document.id,
            "document_no": document.document_no,
            "category_code": document.category_code,
            "title": document.title,
            "file_id": file_row.id,
            "file_name": file_row.file_name,
            # 자료요약 Agent 가 저장해 둔 요약. processing_status 가 completed 인 행만
            # 담으므로 승인 전 초안이 새어 나가지 않는다.
            "summary_markdown": file_row.summary_markdown,
            "uploaded_at": file_row.uploaded_at,
        }
    return list(documents.values())


async def list_for_activity(
    db: AsyncSession,
    *,
    team_id: UUID,
    activity: Activity,
    customer_company_id: UUID | None,
) -> dict[str, list[dict[str, object]]]:
    """미팅 화면에 세울 자료를 성격별로 나눠 돌려준다.

    ``related`` 는 이 딜·고객사에 붙은 자료고, ``product`` 는 이 미팅이 다루는 상품에
    붙은 자료다. 상품 자료는 고객사와 무관한 공용 자료(카탈로그·스펙 등)라 같은 목록에
    섞으면 어느 쪽이 이 고객사 것인지 구분할 수 없어 따로 나눈다.
    """
    related = await _documents(
        db,
        team_id=team_id,
        scopes=document_processing.document_scopes(activity.sales_deal_id, customer_company_id),
    )
    product_ids = await _product_ids(db, team_id=team_id, activity=activity)
    product = await _documents(
        db,
        team_id=team_id,
        scopes=[Document.product_id.in_(product_ids)] if product_ids else [],
    )
    # 예전 자료는 상품과 고객사를 함께 들고 있을 수 있다. 양쪽에 같은 문서를 세우지 않는다.
    related_ids = {item["document_id"] for item in related}
    return {
        "related": related,
        "product": [item for item in product if item["document_id"] not in related_ids],
    }
