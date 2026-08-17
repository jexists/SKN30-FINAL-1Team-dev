from collections import Counter
from datetime import timedelta
from uuid import uuid4, uuid5

from sqlalchemy.dialects import postgresql

from scripts.seed_demo_activities import PRODUCT_NAMES, REFERENCE_DATE, product_id
from scripts.seed_demo_auth import EMPTY_TEAM_ID, FILLED_TEAM_ID
from scripts.seed_demo_customers import OWNER_IDS, company_id
from scripts.seed_demo_sales_deals import (
    SALES_DEAL_SEEDS,
    STAGE_CODE_BY_KEY,
    sales_deal_id,
    sales_deal_row,
    sales_deal_upsert,
)


def _references():
    pipeline_id = uuid4()
    stage_ids = {key: uuid4() for key in STAGE_CODE_BY_KEY}
    type_ids = {seed.deal_type_code: uuid4() for seed in SALES_DEAL_SEEDS}
    return pipeline_id, stage_ids, type_ids


def test_demo_sales_deal_seed_uses_saved_pipeline_and_lookup_rows():
    pipeline_id, stage_ids, type_ids = _references()
    rows = {
        seed.deal_no: sales_deal_row(seed, pipeline_id, stage_ids, type_ids)
        for seed in SALES_DEAL_SEEDS
    }

    assert REFERENCE_DATE.isoformat() == "2026-08-17"
    assert len(rows) == len(SALES_DEAL_SEEDS) == 61
    assert len({row["id"] for row in rows.values()}) == 61
    assert all(row["team_id"] == FILLED_TEAM_ID != EMPTY_TEAM_ID for row in rows.values())
    assert set(STAGE_CODE_BY_KEY.values()) == {
        "needs_validation",
        "product_demo",
        "quote_sent",
        "contract_sent",
        "contract_review",
        "contract_completed",
        "order_in_progress",
        "order_delivered",
        "closed_cancelled",
    }
    assert Counter(seed.sales_pipeline_stage_key for seed in SALES_DEAL_SEEDS) == {
        "needs": 3,
        "demo": 2,
        "quote": 2,
        "sent": 3,
        "reviewing": 2,
        "won": 45,
        "order_in_progress": 1,
        "delivered": 1,
        "lost": 2,
    }
    assert Counter(seed.product_name for seed in SALES_DEAL_SEEDS) == {
        "CardioView X7": 26,
        "SonoFlex Pro": 21,
        "OrthoScan Mini": 14,
    }
    assert {seed.product_name for seed in SALES_DEAL_SEEDS} == set(PRODUCT_NAMES)

    for seed in SALES_DEAL_SEEDS:
        row = rows[seed.deal_no]
        assert (
            row["id"]
            == sales_deal_id(seed.deal_no)
            == uuid5(FILLED_TEAM_ID, f"contract:{seed.deal_no}")
        )
        assert row["sales_pipeline_id"] == pipeline_id
        assert row["sales_pipeline_stage_id"] == stage_ids[seed.sales_pipeline_stage_key]
        assert row["sales_deal_type_id"] == type_ids[seed.deal_type_code]
        assert row["customer_company_id"] == company_id(seed.company_name)
        assert row["owner_member_id"] == OWNER_IDS[seed.owner_name]
        assert row["product_id"] == product_id(seed.product_name)
        assert row["opened_on"] == REFERENCE_DATE + timedelta(days=seed.day_offset)
        assert row["closed_on"] == (
            row["opened_on"] if seed.sales_pipeline_stage_key == "lost" else None
        )
        assert row["contract_signed_on"] == (
            row["opened_on"]
            if seed.sales_pipeline_stage_key in {"won", "order_in_progress", "delivered"}
            else None
        )
        assert row["customer_contact_id"] is None
        assert row["quote_no"] is None
        assert row["contract_no"] is None
        assert row["deleted_at"] is None
        assert row["title"] == f"{seed.company_name} {seed.product_name}"
        assert row["deal_amount"] > 0

    assert rows["FM-CT-2026-0020"]["sales_pipeline_stage_id"] == stage_ids["order_in_progress"]
    assert rows["FM-CT-2026-0013"]["sales_pipeline_stage_id"] == stage_ids["delivered"]


def test_demo_sales_deal_upserts_preserve_business_identity():
    pipeline_id, stage_ids, type_ids = _references()
    dialect = postgresql.dialect()

    for seed in SALES_DEAL_SEEDS:
        row = sales_deal_row(seed, pipeline_id, stage_ids, type_ids)
        sql = str(sales_deal_upsert(row).compile(dialect=dialect))
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert "RETURNING public.sales_deal.id" in sql
        assert "team_id = excluded.team_id" not in sql
        assert "deal_no = excluded.deal_no" not in sql
