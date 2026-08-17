from collections import Counter
from datetime import timedelta
from uuid import uuid5

from sqlalchemy.dialects import postgresql

from scripts.seed_demo_activities import PRODUCT_NAMES, REFERENCE_DATE, product_id
from scripts.seed_demo_auth import EMPTY_TEAM_ID, FILLED_TEAM_ID
from scripts.seed_demo_contracts import (
    CONTRACT_SEEDS,
    PIPELINE_STAGE_SEEDS,
    contract_id,
    contract_row,
    contract_upsert,
    pipeline_stage_id,
    pipeline_stage_row,
    pipeline_stage_upsert,
)
from scripts.seed_demo_customers import OWNER_IDS, company_id


def test_demo_contract_seed_shape_is_fixed_and_lossless():
    stage_rows = {seed.key: pipeline_stage_row(seed) for seed in PIPELINE_STAGE_SEEDS}
    contract_rows = {seed.contract_no: contract_row(seed) for seed in CONTRACT_SEEDS}

    assert REFERENCE_DATE.isoformat() == "2026-08-17"
    assert len(stage_rows) == len(PIPELINE_STAGE_SEEDS) == 8
    assert len(contract_rows) == len(CONTRACT_SEEDS) == 61
    assert len({row["id"] for row in stage_rows.values()}) == 8
    assert len({row["id"] for row in contract_rows.values()}) == 61
    assert all(row["team_id"] == FILLED_TEAM_ID != EMPTY_TEAM_ID for row in stage_rows.values())
    assert all(row["team_id"] == FILLED_TEAM_ID != EMPTY_TEAM_ID for row in contract_rows.values())

    assert [seed.key for seed in PIPELINE_STAGE_SEEDS] == [
        "needs",
        "demo",
        "quote",
        "sent",
        "reviewing",
        "won",
        "delivered",
        "lost",
    ]
    assert [seed.position for seed in PIPELINE_STAGE_SEEDS] == list(range(8))
    assert Counter(seed.outcome_code for seed in PIPELINE_STAGE_SEEDS) == {
        "in_progress": 5,
        "confirmed": 2,
        "cancelled": 1,
    }
    assert all(
        row["id"] == pipeline_stage_id(key) == uuid5(FILLED_TEAM_ID, f"pipeline-stage:{key}")
        for key, row in stage_rows.items()
    )

    assert Counter(seed.product_name for seed in CONTRACT_SEEDS) == {
        "CardioView X7": 26,
        "SonoFlex Pro": 21,
        "OrthoScan Mini": 14,
    }
    assert {seed.product_name for seed in CONTRACT_SEEDS} == set(PRODUCT_NAMES)
    assert {
        "전극 패드 (소모품)",
        "유지보수 (1년)",
        "유지보수 (3년)",
    }.isdisjoint(seed.product_name for seed in CONTRACT_SEEDS)
    assert Counter(seed.owner_name for seed in CONTRACT_SEEDS) == {
        "김지훈": 35,
        "이수민": 15,
        "박도윤": 7,
        "최가은": 4,
    }
    assert Counter(seed.stage_key for seed in CONTRACT_SEEDS) == {
        "needs": 3,
        "demo": 2,
        "quote": 2,
        "sent": 3,
        "reviewing": 2,
        "won": 46,
        "delivered": 1,
        "lost": 2,
    }
    assert Counter(seed.contract_type for seed in CONTRACT_SEEDS) == {
        "new_installation": 39,
        "expansion": 21,
        "consumables_supply": 1,
    }

    for seed in CONTRACT_SEEDS:
        row = contract_rows[seed.contract_no]
        assert (
            row["id"]
            == contract_id(seed.contract_no)
            == uuid5(FILLED_TEAM_ID, f"contract:{seed.contract_no}")
        )
        assert row["customer_company_id"] == company_id(seed.company_name)
        assert row["owner_member_id"] == OWNER_IDS[seed.owner_name]
        assert row["product_id"] == product_id(seed.product_name)
        assert row["stage_id"] == pipeline_stage_id(seed.stage_key)
        assert row["contract_date"] == REFERENCE_DATE + timedelta(days=seed.day_offset)
        assert row["contact_id"] is None
        assert row["description"] is None
        assert row["ends_on"] is None
        assert row["warranty_terms"] is None
        assert row["expected_delivery_at"] is None
        assert row["memo"] is None
        assert row["deleted_at"] is None
        assert row["title"] == f"{seed.company_name} {seed.product_name}"
        assert row["amount"] > 0

    assert contract_rows["FM-CT-2026-0039"]["contract_date"] == REFERENCE_DATE
    assert contract_rows["FM-CT-2024-0001"]["contract_date"] == REFERENCE_DATE + timedelta(
        days=-704
    )
    assert contract_rows["FM-CT-2026-0013"]["stage_id"] == pipeline_stage_id("delivered")
    assert contract_rows["FM-CT-2026-0044"]["position"] == 3
    assert contract_rows["FM-CT-2026-0040"]["position"] == 3


def test_demo_contract_upserts_compile_for_postgresql():
    dialect = postgresql.dialect()

    for seed in PIPELINE_STAGE_SEEDS:
        sql = str(pipeline_stage_upsert(pipeline_stage_row(seed)).compile(dialect=dialect))
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert "RETURNING public.pipeline_stage.id" in sql
        assert "team_id = excluded.team_id" not in sql

    for seed in CONTRACT_SEEDS:
        sql = str(contract_upsert(contract_row(seed)).compile(dialect=dialect))
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert "RETURNING public.contract.id" in sql
        assert "team_id = excluded.team_id" not in sql
        assert "contract_no = excluded.contract_no" not in sql
