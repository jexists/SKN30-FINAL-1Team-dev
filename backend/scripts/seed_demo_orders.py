"""filled 데모팀에만 관계가 정확한 합성 발주 2건과 품목 2건을 반복 가능하게 넣는다."""

import asyncio
from datetime import timedelta
from typing import NamedTuple
from uuid import UUID, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_sessionmaker
from app.models.configuration import PurchaseOrderStatus
from app.models.crm import CustomerCompany
from app.models.sales import Product, PurchaseOrder, PurchaseOrderItem, SalesDeal
from app.models.workspace import Member, Team
from scripts.seed_demo_activities import REFERENCE_DATE, product_id
from scripts.seed_demo_auth import FILLED_TEAM_ID
from scripts.seed_demo_customers import FILLED_TEAM_NAME, company_id
from scripts.seed_demo_sales_deals import sales_deal_id


class PurchaseOrderSeed(NamedTuple):
    order_no: str
    deal_no: str
    company_name: str
    product_name: str
    supplier_name: str
    ordered_day_offset: int
    due_day_offset: int
    expected_receipt_day_offset: int
    stage_code: str
    memo: str | None
    quantity: int
    unit_price: int


# 프론트 발주 5건 중 현재 고객사·상품·계약 관계가 모두 정확한 2건만 옮긴다.
PURCHASE_ORDER_SEEDS = (
    PurchaseOrderSeed(
        "FM-PO-2026-0020",
        "FM-CT-2026-0020",
        "한빛대학교병원",
        "CardioView X7",
        "본사 생산팀",
        -13,
        6,
        6,
        "in_production",
        "분할 납품 1차",
        2,
        24_000_000,
    ),
    PurchaseOrderSeed(
        "FM-PO-2026-0019",
        "FM-CT-2026-0013",
        "서림메디컬센터",
        "OrthoScan Mini",
        "외부 벤더 (메디파츠)",
        -21,
        -7,
        -8,
        "delivered",
        None,
        3,
        8_600_000,
    ),
)


def purchase_order_id(order_no: str) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"purchase-order:{order_no}")


def purchase_order_item_id(order_no: str, position: int) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"purchase-order-item:{order_no}:{position}")


def purchase_order_row(seed: PurchaseOrderSeed, purchase_order_status_id: UUID) -> dict:
    return {
        "id": purchase_order_id(seed.order_no),
        "team_id": FILLED_TEAM_ID,
        "order_no": seed.order_no,
        "sales_deal_id": sales_deal_id(seed.deal_no),
        "supplier_name": seed.supplier_name,
        "purchase_order_status_id": purchase_order_status_id,
        "ordered_on": REFERENCE_DATE + timedelta(days=seed.ordered_day_offset),
        "due_on": REFERENCE_DATE + timedelta(days=seed.due_day_offset),
        "expected_receipt_on": REFERENCE_DATE + timedelta(days=seed.expected_receipt_day_offset),
        "memo": seed.memo,
        "deleted_at": None,
    }


def purchase_order_item_row(seed: PurchaseOrderSeed, position: int = 0) -> dict:
    return {
        "id": purchase_order_item_id(seed.order_no, position),
        "purchase_order_id": purchase_order_id(seed.order_no),
        "product_id": product_id(seed.product_name),
        "quantity": seed.quantity,
        "unit_price": seed.unit_price,
        "position": position,
    }


def purchase_order_upsert(row: dict):
    order_insert = insert(PurchaseOrder).values(**row)
    update_fields = {
        key: getattr(order_insert.excluded, key)
        for key in row
        if key not in {"id", "team_id", "order_no"}
    }
    return order_insert.on_conflict_do_update(
        index_elements=[PurchaseOrder.id],
        set_=update_fields,
        where=and_(
            PurchaseOrder.team_id == FILLED_TEAM_ID,
            PurchaseOrder.order_no == row["order_no"],
        ),
    ).returning(PurchaseOrder.id)


def purchase_order_item_upsert(row: dict):
    item_insert = insert(PurchaseOrderItem).values(**row)
    update_fields = {
        key: getattr(item_insert.excluded, key)
        for key in row
        if key not in {"id", "purchase_order_id", "position"}
    }
    return item_insert.on_conflict_do_update(
        index_elements=[PurchaseOrderItem.id],
        set_=update_fields,
        where=and_(
            PurchaseOrderItem.purchase_order_id == row["purchase_order_id"],
            PurchaseOrderItem.position == row["position"],
        ),
    ).returning(PurchaseOrderItem.id)


async def seed_demo_orders() -> None:
    expected_companies = {
        company_id(seed.company_name): seed.company_name for seed in PURCHASE_ORDER_SEEDS
    }
    expected_products = {
        product_id(seed.product_name): seed.product_name for seed in PURCHASE_ORDER_SEEDS
    }
    expected_sales_deal_seeds = {sales_deal_id(seed.deal_no): seed for seed in PURCHASE_ORDER_SEEDS}
    expected_sales_deal_ids_by_no = {
        seed.deal_no: id_ for id_, seed in expected_sales_deal_seeds.items()
    }
    expected_status_codes = {seed.stage_code for seed in PURCHASE_ORDER_SEEDS}

    async with get_sessionmaker()() as session, session.begin():
        filled_team_name = (
            await session.execute(
                select(Team.name).where(Team.id == FILLED_TEAM_ID).with_for_update()
            )
        ).scalar_one_or_none()
        if filled_team_name != FILLED_TEAM_NAME:
            raise SystemExit("filled 인증 seed를 먼저 실행하세요.")

        status_rows = (
            await session.execute(
                select(PurchaseOrderStatus.id, PurchaseOrderStatus.code)
                .where(
                    PurchaseOrderStatus.team_id == FILLED_TEAM_ID,
                    PurchaseOrderStatus.code.in_(expected_status_codes),
                    PurchaseOrderStatus.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).all()
        status_ids_by_code = {row.code: row.id for row in status_rows}
        if set(status_ids_by_code) != expected_status_codes:
            raise SystemExit("filled 인증 seed를 먼저 실행해 발주 상태를 준비하세요.")

        existing_companies = (
            await session.execute(
                select(CustomerCompany.id, CustomerCompany.team_id, CustomerCompany.name)
                .where(
                    or_(
                        CustomerCompany.id.in_(expected_companies),
                        and_(
                            CustomerCompany.team_id == FILLED_TEAM_ID,
                            CustomerCompany.name.in_(expected_companies.values()),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        expected_company_ids_by_name = {name: id_ for id_, name in expected_companies.items()}
        for row in existing_companies:
            if (
                row.team_id != FILLED_TEAM_ID
                or expected_companies.get(row.id) != row.name
                or expected_company_ids_by_name.get(row.name) != row.id
            ):
                raise SystemExit("합성 발주 고객사 ID, 이름 또는 팀이 충돌합니다.")
        if {row.id for row in existing_companies} != set(expected_companies):
            raise SystemExit("고객 seed를 먼저 실행해 발주 고객사를 준비하세요.")

        existing_products = (
            await session.execute(
                select(Product.id, Product.team_id, Product.name, Product.active)
                .where(
                    or_(
                        Product.id.in_(expected_products),
                        and_(
                            Product.team_id == FILLED_TEAM_ID,
                            Product.name.in_(expected_products.values()),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        expected_product_ids_by_name = {name: id_ for id_, name in expected_products.items()}
        for row in existing_products:
            if (
                row.team_id != FILLED_TEAM_ID
                or expected_products.get(row.id) != row.name
                or expected_product_ids_by_name.get(row.name) != row.id
                or not row.active
            ):
                raise SystemExit("합성 발주 상품 ID, 이름, 팀 또는 상태가 충돌합니다.")
        if {row.id for row in existing_products} != set(expected_products):
            raise SystemExit("일정 seed를 먼저 실행해 발주 상품을 준비하세요.")

        existing_sales_deals = (
            await session.execute(
                select(
                    SalesDeal.id,
                    SalesDeal.team_id,
                    SalesDeal.deal_no,
                    SalesDeal.customer_company_id,
                    SalesDeal.product_id,
                    SalesDeal.owner_member_id,
                    SalesDeal.deleted_at,
                )
                .where(
                    or_(
                        SalesDeal.id.in_(expected_sales_deal_seeds),
                        and_(
                            SalesDeal.team_id == FILLED_TEAM_ID,
                            SalesDeal.deal_no.in_(expected_sales_deal_ids_by_no),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        sales_deals_by_id = {row.id: row for row in existing_sales_deals}
        for row in existing_sales_deals:
            seed = expected_sales_deal_seeds.get(row.id)
            if (
                seed is None
                or row.team_id != FILLED_TEAM_ID
                or row.deal_no != seed.deal_no
                or expected_sales_deal_ids_by_no.get(row.deal_no) != row.id
                or row.customer_company_id != company_id(seed.company_name)
                or row.product_id != product_id(seed.product_name)
                or row.deleted_at is not None
            ):
                raise SystemExit("합성 발주 계약 ID, 번호, 고객사, 상품 또는 팀이 충돌합니다.")
        if set(sales_deals_by_id) != set(expected_sales_deal_seeds):
            raise SystemExit("계약 seed를 먼저 실행해 발주 계약을 준비하세요.")

        expected_owner_ids = {row.owner_member_id for row in existing_sales_deals}
        existing_owners = (
            await session.execute(
                select(Member.id, Member.team_id, Member.active)
                .where(Member.id.in_(expected_owner_ids))
                .with_for_update()
            )
        ).all()
        if {row.id for row in existing_owners} != expected_owner_ids or any(
            row.team_id != FILLED_TEAM_ID or not row.active for row in existing_owners
        ):
            raise SystemExit("합성 발주 계약 담당자 ID, 팀 또는 상태가 충돌합니다.")

        orders = tuple(
            purchase_order_row(seed, status_ids_by_code[seed.stage_code])
            for seed in PURCHASE_ORDER_SEEDS
        )
        items = tuple(purchase_order_item_row(seed) for seed in PURCHASE_ORDER_SEEDS)
        expected_orders = {row["id"]: row for row in orders}
        expected_order_ids_by_no = {row["order_no"]: row["id"] for row in orders}
        expected_items = {row["id"]: row for row in items}
        expected_item_ids_by_order_position = {
            (row["purchase_order_id"], row["position"]): row["id"] for row in items
        }

        existing_orders = (
            await session.execute(
                select(PurchaseOrder.id, PurchaseOrder.team_id, PurchaseOrder.order_no)
                .where(
                    or_(
                        PurchaseOrder.id.in_(expected_orders),
                        and_(
                            PurchaseOrder.team_id == FILLED_TEAM_ID,
                            PurchaseOrder.order_no.in_(expected_order_ids_by_no),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        for row in existing_orders:
            expected = expected_orders.get(row.id)
            if (
                expected is None
                or row.team_id != FILLED_TEAM_ID
                or expected["order_no"] != row.order_no
                or expected_order_ids_by_no.get(row.order_no) != row.id
            ):
                raise SystemExit("합성 발주 ID, 발주번호 또는 팀이 충돌합니다.")

        existing_items = (
            await session.execute(
                select(
                    PurchaseOrderItem.id,
                    PurchaseOrderItem.purchase_order_id,
                    PurchaseOrderItem.position,
                )
                .where(
                    or_(
                        PurchaseOrderItem.id.in_(expected_items),
                        PurchaseOrderItem.purchase_order_id.in_(expected_orders),
                    )
                )
                .with_for_update()
            )
        ).all()
        for row in existing_items:
            expected = expected_items.get(row.id)
            if (
                expected is None
                or expected["purchase_order_id"] != row.purchase_order_id
                or expected["position"] != row.position
                or expected_item_ids_by_order_position.get((row.purchase_order_id, row.position))
                != row.id
            ):
                raise SystemExit("합성 발주 품목 ID, 발주 또는 순서가 충돌합니다.")

        for row in orders:
            upserted_id = (await session.execute(purchase_order_upsert(row))).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 발주 ID, 발주번호 또는 팀이 충돌합니다.")

        for row in items:
            upserted_id = (
                await session.execute(purchase_order_item_upsert(row))
            ).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 발주 품목 ID, 발주 또는 순서가 충돌합니다.")

    print("개발 DB의 filled 합성 팀에 발주 2건과 발주 품목 2건을 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_orders())
