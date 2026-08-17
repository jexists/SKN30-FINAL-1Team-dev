from datetime import date
from uuid import uuid5

from sqlalchemy.dialects import postgresql

from scripts.seed_demo_activities import REFERENCE_DATE, product_id
from scripts.seed_demo_auth import EMPTY_TEAM_ID, FILLED_TEAM_ID
from scripts.seed_demo_contracts import contract_id
from scripts.seed_demo_customers import OWNER_IDS, company_id
from scripts.seed_demo_orders import (
    PURCHASE_ORDER_SEEDS,
    purchase_order_id,
    purchase_order_item_id,
    purchase_order_item_row,
    purchase_order_item_upsert,
    purchase_order_row,
    purchase_order_upsert,
)


def test_demo_order_seed_shape_is_fixed_and_lossless():
    owner_by_contract = {
        contract_id("FM-CT-2026-0020"): OWNER_IDS["김지훈"],
        contract_id("FM-CT-2026-0013"): OWNER_IDS["김지훈"],
    }
    order_rows = {
        seed.order_no: purchase_order_row(
            seed,
            owner_by_contract[contract_id(seed.contract_no)],
        )
        for seed in PURCHASE_ORDER_SEEDS
    }
    item_rows = {seed.order_no: purchase_order_item_row(seed) for seed in PURCHASE_ORDER_SEEDS}

    assert REFERENCE_DATE == date(2026, 8, 17)
    assert [seed.order_no for seed in PURCHASE_ORDER_SEEDS] == [
        "FM-PO-2026-0020",
        "FM-PO-2026-0019",
    ]
    assert len(order_rows) == len(item_rows) == len(PURCHASE_ORDER_SEEDS) == 2
    assert len({row["id"] for row in order_rows.values()}) == 2
    assert len({row["id"] for row in item_rows.values()}) == 2
    assert all(row["team_id"] == FILLED_TEAM_ID != EMPTY_TEAM_ID for row in order_rows.values())

    for seed in PURCHASE_ORDER_SEEDS:
        order = order_rows[seed.order_no]
        item = item_rows[seed.order_no]
        assert (
            order["id"]
            == purchase_order_id(seed.order_no)
            == uuid5(FILLED_TEAM_ID, f"purchase-order:{seed.order_no}")
        )
        assert (
            item["id"]
            == purchase_order_item_id(seed.order_no, 0)
            == uuid5(FILLED_TEAM_ID, f"purchase-order-item:{seed.order_no}:0")
        )
        assert order["contract_id"] == contract_id(seed.contract_no)
        assert order["customer_company_id"] == company_id(seed.company_name)
        assert order["owner_member_id"] == owner_by_contract[order["contract_id"]]
        assert order["deleted_at"] is None
        assert item == {
            "id": purchase_order_item_id(seed.order_no, 0),
            "order_id": purchase_order_id(seed.order_no),
            "product_id": product_id(seed.product_name),
            "quantity": seed.quantity,
            "unit_price": seed.unit_price,
            "position": 0,
        }

    assert order_rows["FM-PO-2026-0020"] | {
        "product_id": item_rows["FM-PO-2026-0020"]["product_id"],
        "quantity": item_rows["FM-PO-2026-0020"]["quantity"],
        "unit_price": item_rows["FM-PO-2026-0020"]["unit_price"],
    } == {
        "id": purchase_order_id("FM-PO-2026-0020"),
        "team_id": FILLED_TEAM_ID,
        "order_no": "FM-PO-2026-0020",
        "contract_id": contract_id("FM-CT-2026-0020"),
        "customer_company_id": company_id("한빛대학교병원"),
        "owner_member_id": OWNER_IDS["김지훈"],
        "supplier_name": "본사 생산팀",
        "stage_code": "in_production",
        "ordered_on": date(2026, 8, 4),
        "due_on": date(2026, 8, 23),
        "expected_receipt_on": date(2026, 8, 23),
        "memo": "분할 납품 1차",
        "deleted_at": None,
        "product_id": product_id("CardioView X7"),
        "quantity": 2,
        "unit_price": 24_000_000,
    }
    assert order_rows["FM-PO-2026-0019"] | {
        "product_id": item_rows["FM-PO-2026-0019"]["product_id"],
        "quantity": item_rows["FM-PO-2026-0019"]["quantity"],
        "unit_price": item_rows["FM-PO-2026-0019"]["unit_price"],
    } == {
        "id": purchase_order_id("FM-PO-2026-0019"),
        "team_id": FILLED_TEAM_ID,
        "order_no": "FM-PO-2026-0019",
        "contract_id": contract_id("FM-CT-2026-0013"),
        "customer_company_id": company_id("서림메디컬센터"),
        "owner_member_id": OWNER_IDS["김지훈"],
        "supplier_name": "외부 벤더 (메디파츠)",
        "stage_code": "delivered",
        "ordered_on": date(2026, 7, 27),
        "due_on": date(2026, 8, 10),
        "expected_receipt_on": date(2026, 8, 9),
        "memo": None,
        "deleted_at": None,
        "product_id": product_id("OrthoScan Mini"),
        "quantity": 3,
        "unit_price": 8_600_000,
    }


def test_demo_order_rows_and_upserts_are_idempotent_and_filled_only():
    owner_id = OWNER_IDS["김지훈"]
    first_orders = tuple(purchase_order_row(seed, owner_id) for seed in PURCHASE_ORDER_SEEDS)
    second_orders = tuple(purchase_order_row(seed, owner_id) for seed in PURCHASE_ORDER_SEEDS)
    first_items = tuple(purchase_order_item_row(seed) for seed in PURCHASE_ORDER_SEEDS)
    second_items = tuple(purchase_order_item_row(seed) for seed in PURCHASE_ORDER_SEEDS)

    assert first_orders == second_orders
    assert first_items == second_items
    assert all(row["team_id"] == FILLED_TEAM_ID for row in first_orders)
    assert all(row["team_id"] != EMPTY_TEAM_ID for row in first_orders)
    assert {row["order_id"] for row in first_items} == {row["id"] for row in first_orders}

    dialect = postgresql.dialect()
    for row in first_orders:
        sql = str(purchase_order_upsert(row).compile(dialect=dialect))
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert "RETURNING public.purchase_order.id" in sql
        assert "team_id = excluded.team_id" not in sql
        assert "order_no = excluded.order_no" not in sql

    for row in first_items:
        sql = str(purchase_order_item_upsert(row).compile(dialect=dialect))
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert "RETURNING public.purchase_order_item.id" in sql
        assert "order_id = excluded.order_id" not in sql
        assert "position = excluded.position" not in sql
