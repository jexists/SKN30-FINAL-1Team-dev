"""트리거 이후 "다음 미팅 제안 → 일정 후보"를 이어 실행하는 선계산 파이프라인을 확인한다.

실제 체이닝은 백그라운드에서 돌고 실패를 스스로 삼키므로, 여기서는 중복 실행 방어와
제안 상태 저장처럼 결정적으로 확인할 수 있는 부분만 본다
(docs/technical/multiagent/계약에이전트_설계.md 3장).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.models.agent import ContractNextMeetingSuggestion
from app.models.crm import CustomerCompany
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.services import contract_next_meeting_pipeline as pipeline

NOW = datetime(2026, 8, 29, 9, tzinfo=UTC)
_MISSING = object()


class _Result:
    def __init__(self, *, scalar=_MISSING):
        self.scalar = scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.parameters = []
        self.commit_count = 0

    async def execute(self, statement, parameters=None):
        self.statements.append(statement)
        self.parameters.append(parameters)
        assert self.results, "예상보다 많은 쿼리가 실행됐습니다."
        return self.results.pop(0)

    async def commit(self):
        self.commit_count += 1


def _member() -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )


def _deal(owner: Member) -> SalesDeal:
    company = CustomerCompany(id=uuid4(), team_id=owner.team_id, name="합성 병원")
    return SalesDeal(
        id=uuid4(),
        team_id=owner.team_id,
        deal_no="D-2026-0001",
        customer_company_id=company.id,
        customer_contact_id=None,
        owner_member_id=owner.id,
        product_id=uuid4(),
        sales_pipeline_id=uuid4(),
        sales_pipeline_stage_id=uuid4(),
        title="합성 계약건",
        description=None,
        sales_deal_type_id=uuid4(),
        deal_amount=1_000_000,
        opened_on=NOW.date(),
        stage_position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _suggestion(deal: SalesDeal, schedule_run_id: UUID, *, status_code: str = "pending"):
    return ContractNextMeetingSuggestion(
        id=uuid4(),
        team_id=deal.team_id,
        sales_deal_id=deal.id,
        schedule_management_run_id=schedule_run_id,
        status_code=status_code,
        created_at=NOW,
        updated_at=NOW,
    )


def test_queue_defers_the_chain_to_the_background():
    """트리거가 된 요청은 파이프라인 실패와 무관해야 한다 — 응답 뒤로 미룬다."""

    class _Background:
        def __init__(self):
            self.tasks = []

        def add_task(self, func, *args):
            self.tasks.append((func, args))

    background = _Background()
    sales_deal_id = uuid4()
    pipeline.queue(background, sales_deal_id, {"report_id": "r-1"})

    assert background.tasks == [(pipeline._run_pipeline, (sales_deal_id, {"report_id": "r-1"}))]


def test_reserve_locks_the_deal_before_looking():
    """잠금이 조회보다 먼저 걸려야 한다 — 순서가 뒤집히면 막지 못하는 틈이 그대로 남는다."""
    sales_deal_id = uuid4()
    db = _Db(_Result(), _Result(scalar=None))

    assert asyncio.run(pipeline._reserve(db, sales_deal_id)) is True
    assert "pg_advisory_xact_lock" in str(db.statements[0])
    # 잠금은 딜 단위다 — 키가 고정이면 서로 다른 딜까지 줄을 세운다.
    assert str(sales_deal_id) in db.parameters[0]["key"]


def test_reserve_gives_up_when_another_run_holds_the_deal():
    """다른 실행이 이미 자리를 잡고 있으면 LLM 을 부르기 전에 물러난다."""
    db = _Db(_Result(), _Result(scalar=uuid4()))

    assert asyncio.run(pipeline._reserve(db, uuid4())) is False


def test_skips_a_deal_that_just_ran():
    """트리거 한 번이 LLM 두 번이라, 같은 딜에 몰려 들어오면 건너뛴다."""
    sales_deal_id = uuid4()
    found_db = _Db(_Result(scalar=uuid4()))
    assert asyncio.run(pipeline._ran_recently(found_db, sales_deal_id)) is True

    empty_db = _Db(_Result(scalar=None))
    assert asyncio.run(pipeline._ran_recently(empty_db, sales_deal_id)) is False

    sql = str(empty_db.statements[0])
    # 진행 중이거나 쿨다운 안에 시작한 실행이 있으면 막는다.
    assert "source_refs" in sql
    assert "agent_run.status_code IN" in sql
    assert "agent_run.started_at >=" in sql


def test_upsert_revives_a_dismissed_suggestion():
    """닫아 둔 제안도 그 딜에 새 변화가 생기면 다시 올라온다."""
    owner = _member()
    deal = _deal(owner)
    dismissed = _suggestion(deal, uuid4(), status_code="dismissed")
    dismissed.updated_at = NOW - timedelta(days=1)
    new_run_id = uuid4()
    db = _Db(_Result(scalar=dismissed))

    asyncio.run(pipeline._upsert_suggestion(db, deal.team_id, deal.id, new_run_id))

    assert dismissed.status_code == "pending"
    assert dismissed.schedule_management_run_id == new_run_id
    assert dismissed.updated_at > NOW - timedelta(days=1)
    assert db.commit_count == 1


def test_does_nothing_without_an_llm(monkeypatch):
    """LLM 설정이 없으면 조용히 끝난다 — 실행 기록도 남기지 않는다."""
    monkeypatch.setattr(
        pipeline.settings.__class__, "llm_configured", property(lambda _self: False)
    )
    assert asyncio.run(pipeline._run_pipeline(uuid4(), {})) is None


@pytest.mark.parametrize("minutes", [0, 9])
def test_cooldown_covers_the_declared_window(minutes):
    """쿨다운 값이 바뀌면 이 시험이 먼저 알린다."""
    assert timedelta(minutes=minutes) < pipeline._COOLDOWN


def test_keeps_a_suggestion_about_the_triggering_deal():
    """LLM 이 트리거 딜을 답했거나 딜 ID 를 비워 두면 그대로 이어 간다."""
    sales_deal_id = uuid4()

    assert pipeline._answers_this_deal({"sales_deal_id": str(sales_deal_id)}, sales_deal_id) is True
    assert (
        pipeline._answers_this_deal({"reason": "근거만 있고 딜 ID 는 없다"}, sales_deal_id) is True
    )
    assert pipeline._answers_this_deal({"sales_deal_id": None}, sales_deal_id) is True


def test_drops_a_suggestion_about_another_deal():
    """같은 고객사의 다른 딜을 답하면 버린다 — 트리거 딜 제안으로 저장되면 안 된다."""
    sales_deal_id = uuid4()
    other_deal_id = uuid4()

    assert (
        pipeline._answers_this_deal({"sales_deal_id": str(other_deal_id)}, sales_deal_id) is False
    )
