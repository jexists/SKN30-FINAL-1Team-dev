"""미팅 에이전트에 제공할 권한 범위 내 CRM 읽기 전용 컨텍스트.

기본 CRM은 현재 값이고, 과거 거래/보고서는 미팅 이전에 존재하던 기록만 쓴다.
빈 과거 이력은 조회 범위에서 찾지 못했다는 뜻이지 신규 고객이라는 정답이 아니다.
"""

from datetime import UTC, datetime
from typing import Any, get_args
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Report
from app.models.crm import Activity
from app.models.sales import Product, SalesDeal, SalesDealItem
from app.models.workspace import Member
from app.schemas.customers import CustomerSource

SELECTED_DEAL_LIMIT = 100
RELATED_ITEM_LIMIT = 100
INITIAL_HISTORY_LIMIT = 20
EXTRA_HISTORY_LIMIT = 50
PREVIOUS_REPORT_LIMIT = 5
REPORT_TEXT_LIMIT = 8_000
PRODUCT_DETAIL_LIMIT = 20
_SOURCE_CODES = frozenset(get_args(CustomerSource))
_SEOUL = ZoneInfo("Asia/Seoul")


async def _selection(db, member, activity_id, selected_deal_ids):
    # API는 agent_runs를 import하므로 서비스 모듈을 읽는 시점에는 import하지 않는다.
    from app.api.activities import _activity_row
    from app.api.sales_deals import _sales_deal_row

    if not member.active or member.role_code not in {"member", "manager"}:
        raise HTTPException(status_code=403, detail="member_not_allowed")
    if (
        not selected_deal_ids
        or len(selected_deal_ids) > SELECTED_DEAL_LIMIT
        or any(not isinstance(value, UUID) for value in selected_deal_ids)
        or len(set(selected_deal_ids)) != len(selected_deal_ids)
    ):
        raise HTTPException(status_code=422, detail="selected_deal_ids_invalid")
    activity_row = await _activity_row(db, member, activity_id)
    activity, _, contact, company_id, *_ = activity_row
    # 보고서 작성은 팀장도 본인의 미팅에만 허용된다.
    if activity.owner_member_id != member.id:
        raise HTTPException(status_code=403, detail="activity_not_owned")
    if contact is None or company_id is None or contact.company_id != company_id:
        raise HTTPException(status_code=422, detail="meeting_customer_required")
    if activity.starts_at.tzinfo is None or activity.starts_at.utcoffset() is None:
        raise ValueError("meeting_start_timezone_required")
    rows = []
    for deal_id in selected_deal_ids:
        row = await _sales_deal_row(db, member, deal_id)
        if row[0].customer_company_id != company_id:
            raise HTTPException(status_code=404, detail="deal_not_found")
        rows.append(row)
    return activity_row, rows


def _source(contact_code, deal_code):
    # 기존 자유입력 값은 Other로 단정하지 않는다. 고객값이 없을 때만 딜값을 쓴다.
    value = contact_code if contact_code is not None else deal_code
    return {
        "source_code": value if value in _SOURCE_CODES else None,
        "source_origin": "contact" if contact_code is not None else "deal",
    }


def _products(deal, product_name, items):
    products = [
        {
            "id": item.product_id,
            "product_id": item.product_id,
            "name": item.product_name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
        }
        for item in items[:RELATED_ITEM_LIMIT]
    ]
    if deal.product_id and not any(item["id"] == deal.product_id for item in products):
        products.insert(
            0, {"id": deal.product_id, "product_id": deal.product_id, "name": product_name}
        )
    return products[:RELATED_ITEM_LIMIT], (
        len(products) > RELATED_ITEM_LIMIT or len(items) > RELATED_ITEM_LIMIT
    )


async def _trade_history(db, member, activity, company_id, selected_deal_ids, limit):
    from app.api import sales_deals

    before = activity.starts_at
    rows = (
        await db.execute(
            sales_deals._joined_select(SalesDeal, sales_deals._product.name)
            .where(
                *sales_deals._scope(member),
                SalesDeal.customer_company_id == company_id,
                SalesDeal.id.not_in(selected_deal_ids),
                sales_deals._stage.phase_code == "closed",
                sales_deals._stage.outcome_code == "confirmed",
                # 완료 날짜에는 시간이 없으므로 같은 날의 완료도 과거로 추정하지 않는다.
                SalesDeal.closed_on < before.astimezone(_SEOUL).date(),
                SalesDeal.opened_on <= SalesDeal.closed_on,
                or_(
                    SalesDeal.contract_signed_on.is_(None),
                    SalesDeal.contract_signed_on <= SalesDeal.closed_on,
                ),
                SalesDeal.created_at < before,
                # 수정 이력이 없어 이후에 바뀐 현재 행으로 당시 상태를 복원할 수 없다.
                SalesDeal.updated_at < before,
            )
            .order_by(SalesDeal.closed_on.desc(), SalesDeal.id)
            .limit(limit + 1)
        )
    ).all()
    visible = rows[:limit]
    items = await sales_deals._items_by_deal_ids(db, member, [row[0].id for row in visible])
    history = []
    for deal, product_name in visible:
        deal_items = items.get(deal.id, [])
        products, products_truncated = _products(deal, product_name, deal_items)
        history.append(
            {
                "sales_deal_id": deal.id,
                "customer_company_id": deal.customer_company_id,
                "deal_no": deal.deal_no,
                "title": deal.title,
                "closed_on": deal.closed_on,
                "contract_signed_on": deal.contract_signed_on,
                "contract_amount": deal.contract_amount,
                "outcome_code": "confirmed",
                "products": products,
                "products_truncated": products_truncated,
                "product_metadata_basis": "current_catalog_and_items_not_historical_versions",
            }
        )
    return history, {
        "before": before,
        "limit": limit,
        "truncated": len(rows) > limit,
        "scope": "authorized_same_company_completed_deals_excluding_selected",
        "empty_means": "no_matching_record_not_proof_of_new_client",
        "record_time_policy": "created_and_last_updated_before_meeting",
        "actual_delivery_date_available": False,
    }


async def build_context(
    db: AsyncSession,
    member: Member,
    activity_id: UUID,
    selected_deal_ids: list[UUID],
) -> dict[str, Any]:
    """기본 CRM·완료 거래와 선택 딜별 최근 보고서를 실행 입력으로 고정한다."""
    from app.api.sales_deals import _items_by_deal_ids, _participants_by_deal_ids

    activity_row, rows = await _selection(db, member, activity_id, selected_deal_ids)
    activity, owner_name, contact, company_id, company_name, *_ = activity_row
    items = await _items_by_deal_ids(db, member, selected_deal_ids)
    participants = await _participants_by_deal_ids(db, member, selected_deal_ids)
    grounding, deals = [], []
    for row in rows:
        deal = row[0]
        deal_items = items.get(deal.id, [])
        deal_participants = participants.get(deal.id, [])
        products, products_truncated = _products(deal, row[5], deal_items)
        product_names = list(dict.fromkeys(p["name"] for p in products if p["name"]))
        grounding.append(
            {
                "sales_deal_id": deal.id,
                "deal_no": deal.deal_no,
                "title": deal.title,
                "description": deal.description,
                "product_names": product_names[:RELATED_ITEM_LIMIT],
                "deal_type_name": row[16],
                "pipeline_stage_name": row[10],
            }
        )
        deals.append(
            {
                "id": deal.id,
                "sales_deal_id": deal.id,
                "deal_no": deal.deal_no,
                "title": deal.title,
                "description": deal.description,
                "customer_company_id": deal.customer_company_id,
                "customer_contact_id": deal.customer_contact_id,
                "customer_contact_name": row[4],
                "owner": {"id": deal.owner_member_id, "name": row[1]},
                "deal_type": {"code": row[15], "name": row[16]},
                "pipeline_stage": {
                    "code": row[9],
                    "name": row[10],
                    "phase_code": row[12],
                    "outcome_code": row[13],
                },
                **_source(contact.source_code, deal.source_code),
                "deal_amount": deal.deal_amount,
                "opened_on": deal.opened_on,
                "closed_on": deal.closed_on,
                "contract_no": deal.contract_no,
                "contract_status": {"code": row[20], "name": row[21]},
                "contract_signed_on": deal.contract_signed_on,
                "contract_ends_on": deal.contract_ends_on,
                "contract_amount": deal.contract_amount,
                "contract_payment_terms": deal.contract_payment_terms,
                "warranty_terms": deal.warranty_terms,
                "expected_delivery_at": deal.expected_delivery_at,
                "memo": deal.memo,
                "created_at": deal.created_at,
                "updated_at": deal.updated_at,
                "products": products,
                "products_truncated": products_truncated,
                "participants": [
                    p.model_dump(mode="json") for p in deal_participants[:RELATED_ITEM_LIMIT]
                ],
                "participants_truncated": len(deal_participants) > RELATED_ITEM_LIMIT,
            }
        )
    history, history_metadata = await _trade_history(
        db,
        member,
        activity,
        company_id,
        selected_deal_ids,
        INITIAL_HISTORY_LIMIT,
    )
    previous_reports = [
        await _previous_reports(db, member, activity, deal_id) for deal_id in selected_deal_ids
    ]
    return jsonable_encoder(
        {
            "deals": grounding,
            "crm_context": {
                "snapshot_at": datetime.now(UTC),
                "crm_time_basis": "current_values_not_reconstructed_at_meeting_time",
                "activity": {
                    "id": activity.id,
                    "title": activity.title,
                    "starts_at": activity.starts_at,
                    "ends_at": activity.ends_at,
                    "owner": {"id": activity.owner_member_id, "name": owner_name},
                },
                "company": {"id": company_id, "name": company_name},
                "contact": {
                    "id": contact.id,
                    "name": contact.name,
                    "department": contact.department,
                    "job_title": contact.job_title,
                    "owner_member_id": contact.owner_member_id,
                    "memo": contact.memo,
                    "source_code": (
                        contact.source_code if contact.source_code in _SOURCE_CODES else None
                    ),
                },
                "deals": deals,
                "trade_history": history,
                "trade_history_metadata": history_metadata,
                "previous_reports": previous_reports,
                "related_items_limit": RELATED_ITEM_LIMIT,
            },
        }
    )


def _report_values(values):
    """이전 딜 보고서 본문 값만 최대 8,000자로 제한한다. 루트 content는 받지 않는다."""
    if not isinstance(values, dict):
        return {}, False
    cleaned, remaining, truncated = {}, REPORT_TEXT_LIMIT, False
    excluded = {
        "transcript",
        "raw_transcript",
        "ml",
        "ml_result",
        "meeting_analysis",
        "meeting_shared",
        "common_report",
        "unassigned_report",
        "ai_evidence",
    }
    for key, value in values.items():
        if not isinstance(key, str) or key.lower() in excluded or not isinstance(value, str):
            continue
        if len(cleaned) >= 50 or remaining <= 0:
            truncated = True
            break
        cleaned[key] = value[:remaining]
        truncated |= len(value) > remaining
        remaining -= len(cleaned[key])
    return cleaned, truncated


async def _previous_reports(db, member, activity, sales_deal_id):
    """권한·선택 관계 확인 후 호출한다. 기본 입력과 추가 조회가 같은 조회 규칙을 쓴다."""
    from app.api import reports

    rows = (
        await db.execute(
            reports._joined_select(
                Report.id,
                Report.report_date,
                Report.content["values"].label("values"),
                Activity.starts_at,
                Report.status_code,
            )
            .join(Activity, Report.source_activity_id == Activity.id)
            .where(
                *reports._scope(member),
                Report.sales_deal_id == sales_deal_id,
                Report.report_kind == "meeting",
                Report.status_code.in_(("submitted", "approved")),
                Report.source_activity_id != activity.id,
                Activity.team_id == member.team_id,
                Activity.deleted_at.is_(None),
                Activity.starts_at < activity.starts_at,
                Report.created_at < activity.starts_at,
                Report.updated_at < activity.starts_at,
            )
            .order_by(Activity.starts_at.desc(), Report.id)
            .limit(PREVIOUS_REPORT_LIMIT + 1)
        )
    ).all()
    items = []
    for report_id, report_date, values, meeting_at, status_code in rows[:PREVIOUS_REPORT_LIMIT]:
        cleaned, shortened = _report_values(values)
        items.append(
            {
                "report_id": report_id,
                "sales_deal_id": sales_deal_id,
                "report_date": report_date,
                "meeting_at": meeting_at,
                "status_code": status_code,
                "values": cleaned,
                "values_truncated": shortened,
            }
        )
    return jsonable_encoder(
        {
            "kind": "previous_reports",
            "sales_deal_id": sales_deal_id,
            "items": items,
            "before": activity.starts_at,
            "limit": PREVIOUS_REPORT_LIMIT,
            "truncated": len(rows) > PREVIOUS_REPORT_LIMIT,
            "text_limit_per_report": REPORT_TEXT_LIMIT,
            "scope": "authorized_same_deal_submitted_or_approved_meeting_reports",
            "time_basis": "historical_context_not_current_meeting_facts",
            "empty_means": "no_matching_record_not_proof_of_no_previous_meeting",
        }
    )


async def load_extra_context(
    db: AsyncSession,
    member: Member,
    activity_id: UUID,
    selected_deal_ids: list[UUID],
    kind: str,
    sales_deal_id: UUID,
) -> dict[str, Any]:
    """선택 딜에 묶인 추가 읽기. 빈 조회와 DB/권한 실패를 구분한다."""
    if kind not in {"trade_history", "previous_reports", "product_details"}:
        raise HTTPException(status_code=422, detail="meeting_context_kind_invalid")
    if sales_deal_id not in selected_deal_ids:
        raise HTTPException(status_code=422, detail="context_deal_not_selected")
    activity_row, deal_rows = await _selection(db, member, activity_id, selected_deal_ids)
    activity, _, _, company_id, *_ = activity_row
    if kind == "trade_history":
        items, metadata = await _trade_history(
            db,
            member,
            activity,
            company_id,
            selected_deal_ids,
            EXTRA_HISTORY_LIMIT,
        )
    elif kind == "previous_reports":
        return await _previous_reports(db, member, activity, sales_deal_id)
    else:
        deal = next(row[0] for row in deal_rows if row[0].id == sales_deal_id)
        rows = (
            (
                await db.execute(
                    select(Product)
                    .where(
                        Product.team_id == member.team_id,
                        or_(
                            Product.id == deal.product_id,
                            Product.id.in_(
                                select(SalesDealItem.product_id).where(
                                    SalesDealItem.sales_deal_id == sales_deal_id
                                ),
                            ),
                        ),
                    )
                    .order_by(Product.name, Product.id)
                    .limit(PRODUCT_DETAIL_LIMIT + 1)
                )
            )
            .scalars()
            .all()
        )
        items = [
            {
                "id": product.id,
                "name": product.name,
                "category_code": product.category_code,
                "active": product.active,
                "unit_price": product.unit_price,
                "shelf_life_months": product.shelf_life_months,
                "memo": product.memo,
            }
            for product in rows[:PRODUCT_DETAIL_LIMIT]
        ]
        metadata = {
            "limit": PRODUCT_DETAIL_LIMIT,
            "truncated": len(rows) > PRODUCT_DETAIL_LIMIT,
            "time_basis": "current_catalog_not_historical_price",
            "observed_at": datetime.now(UTC),
        }
    return jsonable_encoder(
        {"kind": kind, "sales_deal_id": sales_deal_id, "items": items, **metadata}
    )
