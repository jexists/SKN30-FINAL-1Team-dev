import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from scripts.seed_demo_auth import (
    DEFAULT_PIPELINE_STAGES,
    LOOKUP_DEFAULTS,
    MEMBER_ACCOUNTS,
    TEAM_ID,
    configuration_id,
    insert_missing,
    member_ids_from_args,
    parse_args,
    seed_team_configuration,
)


class FakeResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

    def scalars(self):
        return self


class FakeSession:
    def __init__(self, results):
        self.results = iter(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)


def test_demo_auth_configuration_matches_the_fixed_defaults():
    assert [(table_name, len(rows)) for _model, table_name, rows in LOOKUP_DEFAULTS] == [
        ("customer_contact_status", 5),
        ("activity_category", 6),
        ("activity_action_tag", 11),
        ("sales_deal_type", 5),
        ("purchase_order_status", 6),
        ("quote_status", 5),
        ("contract_status", 5),
    ]
    for _model, _table_name, rows in LOOKUP_DEFAULTS:
        assert len({row["code"] for row in rows}) == len(rows)
        assert [row["position"] for row in rows] == list(range(len(rows)))

    assert [row["stage_code"] for row in DEFAULT_PIPELINE_STAGES] == [
        "needs_validation",
        "product_demo",
        "quote_sent",
        "contract_sent",
        "contract_review",
        "contract_completed",
        "order_in_progress",
        "order_delivered",
        "closed_cancelled",
    ]
    assert [row["position"] for row in DEFAULT_PIPELINE_STAGES] == list(range(9))
    assert [row["phase_code"] for row in DEFAULT_PIPELINE_STAGES] == [
        "sales",
        "sales",
        "quote",
        "contract",
        "contract",
        "contract",
        "order",
        "order",
        "closed",
    ]
    assert [row["outcome_code"] for row in DEFAULT_PIPELINE_STAGES] == [
        "in_progress",
        "in_progress",
        "in_progress",
        "in_progress",
        "in_progress",
        "confirmed",
        "confirmed",
        "confirmed",
        "cancelled",
    ]


def test_demo_auth_configuration_ids_and_inserts_are_repeatable():
    pipeline_id = configuration_id(TEAM_ID, "sales_pipeline", "default")
    assert pipeline_id == UUID("6feb55b1-21eb-1ff4-3d2f-d4b09d5d66cd")
    assert configuration_id(
        pipeline_id,
        "sales_pipeline_stage",
        "needs_validation",
    ) == UUID("446da7c6-52ce-1929-1244-1f94e946e827")

    model = LOOKUP_DEFAULTS[0][0]
    sql = str(
        insert_missing(
            model,
            {
                "id": configuration_id(TEAM_ID, "customer_contact_status", "new"),
                "team_id": TEAM_ID,
                **LOOKUP_DEFAULTS[0][2][0],
            },
        ).compile(dialect=postgresql.dialect())
    )
    assert "ON CONFLICT DO NOTHING" in sql
    assert "DO UPDATE" not in sql


def test_existing_configuration_is_validated_without_being_overwritten():
    team_id = uuid4()
    pipeline_id = uuid4()
    lookup_results = [
        FakeResult(
            [SimpleNamespace(id=uuid4(), team_id=team_id, code=row["code"]) for row in defaults]
        )
        for _model, _table_name, defaults in LOOKUP_DEFAULTS
    ]
    pipeline = SimpleNamespace(
        id=pipeline_id,
        team_id=team_id,
        name="기본 영업",
        description=None,
        status_code="published",
        is_default=True,
        published_at=datetime.now(UTC),
        archived_at=None,
    )
    stages = [
        SimpleNamespace(id=uuid4(), sales_pipeline_id=pipeline_id, **row)
        for row in DEFAULT_PIPELINE_STAGES
    ]
    session = FakeSession([*lookup_results, FakeResult([pipeline]), FakeResult(stages)])

    asyncio.run(seed_team_configuration(session, team_id))

    assert len(session.statements) == 9


def test_configuration_id_collision_stops_before_any_write():
    team_id = uuid4()
    table_name = LOOKUP_DEFAULTS[0][1]
    collision = SimpleNamespace(
        id=configuration_id(team_id, table_name, "proposal"),
        team_id=team_id,
        code="new",
    )
    session = FakeSession([FakeResult([collision])])

    with pytest.raises(SystemExit, match="충돌"):
        asyncio.run(seed_team_configuration(session, team_id))

    assert len(session.statements) == 1


def test_member_accounts_cover_one_team_with_distinct_roles():
    assert len(MEMBER_ACCOUNTS) == 2
    assert [account["key"] for account in MEMBER_ACCOUNTS] == ["manager", "member"]
    assert [account["role_code"] for account in MEMBER_ACCOUNTS] == ["manager", "member"]
    # 이름은 실행 중 구성원을 구분하는 자연키이므로 팀 안에서 겹치면 안 된다.
    assert len({account["display_name"] for account in MEMBER_ACCOUNTS}) == 2
    assert len({account["flag"] for account in MEMBER_ACCOUNTS}) == 2


def test_member_ids_are_read_from_the_two_flags():
    manager = uuid4()
    member = uuid4()

    ids = member_ids_from_args(parse_args(["--manager", str(manager), "--member", str(member)]))

    assert ids == {"manager": manager, "member": member}


def test_malformed_uuid_stops_before_any_write():
    with pytest.raises(SystemExit, match="UUID 형식"):
        member_ids_from_args(parse_args(["--manager", "not-a-uuid", "--member", str(uuid4())]))


def test_the_same_uuid_cannot_fill_two_roles():
    shared = str(uuid4())

    with pytest.raises(SystemExit, match="같은 UUID"):
        member_ids_from_args(parse_args(["--manager", shared, "--member", shared]))


def test_both_flags_are_required():
    with pytest.raises(SystemExit):
        parse_args(["--manager", str(uuid4())])
