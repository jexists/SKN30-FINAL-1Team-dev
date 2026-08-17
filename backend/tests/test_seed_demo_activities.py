from collections import Counter
from datetime import timedelta
from uuid import uuid5

from scripts.seed_demo_activities import (
    ACTION_TAG_CODES,
    ACTIVITY_SEEDS,
    CATEGORY_CODES,
    PRODUCT_NAMES,
    REFERENCE_DATE,
    SEOUL,
    activity_id,
    activity_row,
    product_id,
)
from scripts.seed_demo_auth import EMPTY_TEAM_ID, FILLED_TEAM_ID


def test_demo_activity_seed_shape_is_fixed_and_synthetic():
    category_ids = {
        code: uuid5(FILLED_TEAM_ID, f"activity-category:{code}") for code in CATEGORY_CODES.values()
    }
    action_tag_ids = {
        code: uuid5(FILLED_TEAM_ID, f"activity-action-tag:{code}")
        for code in ACTION_TAG_CODES.values()
    }
    rows = {
        seed.mock_id: activity_row(seed, category_ids, action_tag_ids) for seed in ACTIVITY_SEEDS
    }

    assert REFERENCE_DATE.isoformat() == "2026-08-17"
    assert SEOUL.key == "Asia/Seoul"
    assert len(rows) == len(ACTIVITY_SEEDS) == 12
    assert set(rows) == {f"a{number}" for number in range(1, 13)}
    assert len({row["id"] for row in rows.values()}) == 12
    assert all(row["team_id"] == FILLED_TEAM_ID != EMPTY_TEAM_ID for row in rows.values())
    assert all(
        row["id"] == activity_id(mock_id) == uuid5(FILLED_TEAM_ID, f"activity:{mock_id}")
        for mock_id, row in rows.items()
    )

    assert set(CATEGORY_CODES.values()) == {
        "visit",
        "demo",
        "education",
        "call",
        "delivery",
        "conference",
        "internal",
    }
    assert set(ACTION_TAG_CODES.values()) == {
        "first_call",
        "meeting",
        "demo_requested",
        "demo_in_progress",
        "demo_completed",
        "quote_completed",
        "contract_completed",
        "product_training",
        "delivery_completed",
        "internal_meeting",
        "weekly_review",
        "monthly_review",
        "quarterly_review",
        "conference",
        "ojt",
    }
    assert len(ACTION_TAG_CODES) == len(set(ACTION_TAG_CODES.values())) == 15
    assert all(
        code.isascii() and code.replace("_", "").islower() for code in ACTION_TAG_CODES.values()
    )
    assert Counter(row["activity_type"] for row in rows.values()) == {
        "meeting": 10,
        "task": 2,
    }
    assert Counter(seed.owner_name for seed in ACTIVITY_SEEDS) == {
        "김지훈": 7,
        "이수민": 2,
        "박도윤": 2,
        "김서현": 1,
    }

    assert {mock_id for mock_id, row in rows.items() if row["customer_contact_id"] is None} == {
        "a4",
        "a5",
        "a9",
        "a12",
    }
    assert sum(row["customer_contact_id"] is not None for row in rows.values()) == 8
    assert Counter(seed.product_name for seed in ACTIVITY_SEEDS) == {
        "CardioView X7": 4,
        "OrthoScan Mini": 4,
        "SonoFlex Pro": 2,
        None: 2,
    }
    assert set(PRODUCT_NAMES) == {"CardioView X7", "OrthoScan Mini", "SonoFlex Pro"}
    assert len({product_id(name) for name in PRODUCT_NAMES}) == 3
    assert all(
        product_id(name) == uuid5(FILLED_TEAM_ID, f"product:{name}") for name in PRODUCT_NAMES
    )

    assert {mock_id for mock_id, row in rows.items() if row["completed_at"] is not None} == {
        "a1",
        "a5",
        "a6",
        "a10",
    }
    assert {mock_id for mock_id, row in rows.items() if row["all_day"]} == {"a5"}
    assert rows["a5"]["ends_at"] is None
    assert rows["a12"]["activity_action_tag_id"] is None
    for seed in ACTIVITY_SEEDS:
        row = rows[seed.mock_id]
        assert row["activity_category_id"] == category_ids[CATEGORY_CODES[seed.kind]]
        assert row["activity_action_tag_id"] == (
            action_tag_ids[ACTION_TAG_CODES[seed.stage]] if seed.stage else None
        )

    for seed in ACTIVITY_SEEDS:
        row = rows[seed.mock_id]
        assert row["starts_at"].date() == REFERENCE_DATE + timedelta(days=seed.day_offset)
        assert row["starts_at"].timetz().replace(tzinfo=None) == seed.start_time
        assert row["starts_at"].tzinfo == SEOUL
        if seed.duration_minutes is None:
            assert row["ends_at"] is None
        else:
            assert row["ends_at"] - row["starts_at"] == timedelta(minutes=seed.duration_minutes)
