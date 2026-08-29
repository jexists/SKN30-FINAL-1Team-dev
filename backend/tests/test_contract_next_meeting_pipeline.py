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
        self.commit_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
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
