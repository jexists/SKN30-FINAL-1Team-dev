from datetime import UTC, datetime
from uuid import uuid5

from sqlalchemy.dialects import postgresql

from scripts.seed_demo_auth import EMPTY_TEAM_ID, FILLED_TEAM_ID
from scripts.seed_demo_customers import OWNER_IDS, contact_id
from scripts.seed_demo_support import (
    REFERENCE_AT,
    STATUS_CODES,
    SUPPORT_REQUEST_SEEDS,
    SUPPORT_RESPONSE_SEEDS,
    support_request_id,
    support_request_row,
    support_request_upsert,
)


def test_demo_support_seed_shape_is_fixed_and_lossless():
    rows = {seed.mock_id: support_request_row(seed) for seed in SUPPORT_REQUEST_SEEDS}

    assert REFERENCE_AT == datetime(2026, 8, 17, tzinfo=UTC)
    assert [seed.mock_id for seed in SUPPORT_REQUEST_SEEDS] == ["cs-1", "cs-2", "cs-3"]
    assert len(rows) == len(SUPPORT_REQUEST_SEEDS) == 3
    assert len({row["id"] for row in rows.values()}) == 3
    assert all(row["team_id"] == FILLED_TEAM_ID != EMPTY_TEAM_ID for row in rows.values())
    assert SUPPORT_RESPONSE_SEEDS == ()
    assert STATUS_CODES == {"처리중": "in_progress", "처리완료": "completed"}

    assert rows == {
        "cs-1": {
            "id": support_request_id("cs-1"),
            "team_id": FILLED_TEAM_ID,
            "customer_contact_id": contact_id("FM-CU-2026-0001"),
            "assignee_member_id": OWNER_IDS["김지훈"],
            "title": "부팅 시 화면 깜빡임",
            "body": "진료 중 재현되어 사용을 중단한 상태입니다. 기술지원팀 배정이 필요합니다.",
            "is_urgent": True,
            "status_code": "in_progress",
            "registered_at": datetime(2026, 8, 17, tzinfo=UTC),
        },
        "cs-2": {
            "id": support_request_id("cs-2"),
            "team_id": FILLED_TEAM_ID,
            "customer_contact_id": contact_id("FM-CU-2026-0002"),
            "assignee_member_id": OWNER_IDS["김지훈"],
            "title": "프로브 케이블 접촉 불량",
            "body": "프로브 3종 중 1종에서만 발생합니다. 교체용 케이블 재고를 확인하세요.",
            "is_urgent": False,
            "status_code": "in_progress",
            "registered_at": datetime(2026, 8, 16, tzinfo=UTC),
        },
        "cs-3": {
            "id": support_request_id("cs-3"),
            "team_id": FILLED_TEAM_ID,
            "customer_contact_id": contact_id("FM-CU-2026-0003"),
            "assignee_member_id": OWNER_IDS["이수민"],
            "title": "젤 워머 온도 편차",
            "body": "기술지원팀이 원격 점검 중입니다. 결과 회신 예정입니다.",
            "is_urgent": False,
            "status_code": "in_progress",
            "registered_at": datetime(2026, 8, 15, tzinfo=UTC),
        },
    }


def test_demo_support_rows_and_upserts_are_idempotent_and_filled_only():
    first = tuple(support_request_row(seed) for seed in SUPPORT_REQUEST_SEEDS)
    second = tuple(support_request_row(seed) for seed in SUPPORT_REQUEST_SEEDS)

    assert first == second
    assert all(row["team_id"] == FILLED_TEAM_ID for row in first)
    assert all(row["team_id"] != EMPTY_TEAM_ID for row in first)
    assert all(
        row["id"] == uuid5(FILLED_TEAM_ID, f"support-request:{seed.mock_id}")
        for seed, row in zip(SUPPORT_REQUEST_SEEDS, first, strict=True)
    )
    assert len(
        {(row["customer_contact_id"], row["title"], row["registered_at"]) for row in first}
    ) == len(first)

    dialect = postgresql.dialect()
    for row in first:
        sql = str(support_request_upsert(row).compile(dialect=dialect))
        assert "ON CONFLICT (id) DO UPDATE" in sql
        assert "RETURNING public.support_request.id" in sql
        assert "team_id = excluded.team_id" not in sql
        assert "customer_contact_id = excluded.customer_contact_id" not in sql
        assert "title = excluded.title" not in sql
        assert "registered_at = excluded.registered_at" not in sql
