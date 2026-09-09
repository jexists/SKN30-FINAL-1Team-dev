"""로컬 전용 DB에서 위임의 중복 방지와 예산 지속을 실제 Postgres 제약으로 확인한다.

tests/test_contract_delegation_runtime.py 는 자체 Session 대역으로 같은 흐름을 검사한다.
여기서는 부분 unique 인덱스와 행 잠금이 실제 DB 에서 동작하는지만 본다.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.agent import AgentRun
from app.models.configuration import SalesDealType
from app.models.crm import CustomerCompany, CustomerContact
from app.models.sales import SalesDeal, SalesPipeline, SalesPipelineStage
from app.models.workspace import Member, Team
from app.services import contract_schedule_delegation as delegation

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not settings.run_integration_tests or not settings.database_url,
        reason="로컬 DB 실통합 테스트는 명시적으로 켠다",
    ),
]

LEASE_OWNER = "test-worker"


class Fixture:
    """테스트가 만든 행의 ID 만 모아 두고 finally 에서 그 범위만 지운다."""

    def __init__(self):
        self.team = uuid4()
        self.other_team = uuid4()
        self.member = uuid4()
        self.stranger = uuid4()
        self.company = uuid4()
        self.contact = uuid4()
        self.pipeline = uuid4()
        self.stage = uuid4()
        self.deal_type = uuid4()
        self.deal = uuid4()
        self.parent = uuid4()
        self.extra_runs: list[UUID] = []


def _window(days: int = 3, hours: int = 6):
    start = datetime.now(UTC) + timedelta(days=days)
    return start, start + timedelta(hours=hours)


def _request_args(reason: str, *, days: int = 3, hours: int = 6, minutes: int = 60) -> dict:
    start, end = _window(days, hours)
    return {
        "preferred_starts_at": start.isoformat(),
        "preferred_ends_at": end.isoformat(),
        "duration_minutes": minutes,
        "reason": reason,
    }


def _parent_run(fx: Fixture, **overrides) -> AgentRun:
    values = dict(
        id=fx.parent,
        team_id=fx.team,
        parent_run_id=None,
        requested_by_member_id=fx.member,
        agent_code="contract_management_next_meeting",
        trigger_code="manual",
        idempotency_key=None,
        status_code="running",
        llm_model_name=settings.llm_model or "test-model",
        prompt_version="test",
        source_refs={"sales_deal_id": str(fx.deal)},
        input_snapshot={"sales_deals": [{"id": str(fx.deal)}]},
        request_hash=None,
        delegation_key=None,
        delegation_state={},
        output_snapshot=None,
        evidence=None,
        error_message=None,
        started_at=datetime.now(UTC),
        finished_at=None,
        lease_owner=LEASE_OWNER,
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    values.update(overrides)
    return AgentRun(**values)


async def _seed(sessions, fx: Fixture) -> None:
    async with sessions.begin() as session:
        session.add_all(
            [
                Team(id=fx.team, name="합성 위임 A팀"),
                Team(id=fx.other_team, name="합성 위임 B팀"),
            ]
        )
        await session.flush()
        # member.id 는 auth.users(id) 를 물리 FK 로 참조한다.
        for member_id in (fx.member, fx.stranger):
            await session.execute(
                text("INSERT INTO auth.users (id) VALUES (:id) ON CONFLICT DO NOTHING"),
                {"id": member_id},
            )
        session.add_all(
            [
                Member(
                    id=fx.member,
                    team_id=fx.team,
                    display_name="합성 담당자",
                    role_code="manager",
                ),
                Member(
                    id=fx.stranger,
                    team_id=fx.other_team,
                    display_name="합성 타팀원",
                    role_code="member",
                ),
            ]
        )
        session.add(CustomerCompany(id=fx.company, team_id=fx.team, name="합성 고객사"))
        await session.flush()
        session.add(
            CustomerContact(
                id=fx.contact,
                company_id=fx.company,
                owner_member_id=fx.member,
                name="합성 담당 연락처",
                phone="000-0000-0000",
                created_by_member_id=fx.member,
            )
        )
        session.add(
            SalesPipeline(
                id=fx.pipeline,
                team_id=fx.team,
                name="합성 파이프라인",
                status_code="published",
                published_at=datetime.now(UTC),
            )
        )
        session.add(
            SalesDealType(
                id=fx.deal_type, team_id=fx.team, code="synthetic", name="합성 유형", position=1
            )
        )
        await session.flush()
        session.add(
            SalesPipelineStage(
                id=fx.stage,
                sales_pipeline_id=fx.pipeline,
                stage_code="product_demo",
                name="제품 시연",
                tone="blue",
                phase_code="sales",
                outcome_code="in_progress",
                position=1,
            )
        )
        await session.flush()
        session.add(
            SalesDeal(
                id=fx.deal,
                team_id=fx.team,
                deal_no="SYNTH-DELEG-001",
                customer_company_id=fx.company,
                customer_contact_id=fx.contact,
                owner_member_id=fx.member,
                sales_pipeline_id=fx.pipeline,
                sales_pipeline_stage_id=fx.stage,
                title="합성 위임 딜",
                sales_deal_type_id=fx.deal_type,
                deal_amount=1_000_000,
                opened_on=date.today(),
                stage_position=1,
            )
        )


async def _cleanup(sessions, fx: Fixture) -> None:
    async with sessions.begin() as session:
        await session.execute(delete(AgentRun).where(AgentRun.parent_run_id == fx.parent))
        await session.execute(delete(AgentRun).where(AgentRun.id.in_([fx.parent, *fx.extra_runs])))
        await session.execute(delete(SalesDeal).where(SalesDeal.id == fx.deal))
        await session.execute(delete(SalesPipelineStage).where(SalesPipelineStage.id == fx.stage))
        await session.execute(delete(SalesPipeline).where(SalesPipeline.id == fx.pipeline))
        await session.execute(delete(SalesDealType).where(SalesDealType.id == fx.deal_type))
        await session.execute(delete(CustomerContact).where(CustomerContact.id == fx.contact))
        await session.execute(delete(CustomerCompany).where(CustomerCompany.id == fx.company))
        await session.execute(delete(Member).where(Member.id.in_([fx.member, fx.stranger])))
        await session.execute(
            text("DELETE FROM auth.users WHERE id = ANY(:ids)"),
            {"ids": [fx.member, fx.stranger]},
        )
        await session.execute(delete(Team).where(Team.id.in_([fx.team, fx.other_team])))
    async with sessions() as session:
        left = (
            await session.execute(select(AgentRun.id).where(AgentRun.parent_run_id == fx.parent))
        ).all()
        assert left == [], "테스트가 만든 자식 실행이 남았다"


def _guard_local_database() -> None:
    url = make_url(settings.async_database_url)
    assert settings.app_env == "test"
    assert url.host == "127.0.0.1" and url.port == 55432
    assert url.database == "salesluv_test" and url.username == "salesluv_test"


def _run(scenario) -> None:
    _guard_local_database()

    async def main():
        engine = create_async_engine(settings.async_database_url)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        fx = Fixture()
        try:
            await _seed(sessions, fx)
            await scenario(sessions, fx)
        finally:
            try:
                await _cleanup(sessions, fx)
            finally:
                await engine.dispose()

    asyncio.run(main())


def _child(fx: Fixture, delegation_key: str | None, run_id: UUID) -> AgentRun:
    return AgentRun(
        id=run_id,
        team_id=fx.team,
        parent_run_id=fx.parent,
        requested_by_member_id=fx.member,
        agent_code="schedule_management",
        trigger_code="manual",
        idempotency_key=None,
        status_code="queued",
        llm_model_name="test-model",
        prompt_version="test",
        source_refs={"sales_deal_id": str(fx.deal)},
        input_snapshot={},
        request_hash=None,
        delegation_key=delegation_key,
        output_snapshot=None,
        evidence=None,
        error_message=None,
        started_at=None,
        finished_at=None,
    )


def test_partial_unique_index_blocks_duplicate_delegation_key():
    """같은 부모 아래 같은 탐색 키의 자식은 DB 가 두 번째를 거부한다."""

    async def scenario(sessions, fx):
        async with sessions.begin() as session:
            session.add(_parent_run(fx))
        first, second = uuid4(), uuid4()
        fx.extra_runs += [first, second]
        async with sessions.begin() as session:
            session.add(_child(fx, "same-key", first))

        with pytest.raises(IntegrityError) as raised:
            async with sessions.begin() as session:
                session.add(_child(fx, "same-key", second))
        # 다른 제약이 우연히 막은 것이 아니라 이 인덱스가 막았는지 확인한다.
        assert "agent_run_parent_delegation_key" in str(raised.value)

        async with sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(AgentRun.id).where(AgentRun.parent_run_id == fx.parent)
                    )
                )
                .scalars()
                .all()
            )
            assert rows == [first]

    _run(scenario)


def test_null_delegation_key_is_not_deduplicated():
    """부분 인덱스이므로 위임과 무관한 자식 실행은 여러 개 허용된다."""

    async def scenario(sessions, fx):
        async with sessions.begin() as session:
            session.add(_parent_run(fx))
        ids = [uuid4(), uuid4()]
        fx.extra_runs += ids
        async with sessions.begin() as session:
            session.add_all([_child(fx, None, run_id) for run_id in ids])

        async with sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(AgentRun.id).where(
                            AgentRun.parent_run_id == fx.parent,
                            AgentRun.delegation_key.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert sorted(rows, key=str) == sorted(ids, key=str)

    _run(scenario)


def test_concurrent_same_search_creates_one_child(monkeypatch):
    """부모 행 잠금이 동시 요청을 직렬화해 탐색 키당 자식이 하나만 생긴다."""
    calls: list[UUID] = []

    async def fake_execute_child(self, child_id):
        calls.append(child_id)
        await asyncio.sleep(0)
        return {
            "status": "no_candidates",
            "reason_code": "no_candidates",
            "schedule_run_id": str(child_id),
            "schedule_candidates": [],
            "applied_conditions": {},
        }

    monkeypatch.setattr(
        delegation.DelegationRuntime, "_execute_child", fake_execute_child, raising=True
    )

    async def scenario(sessions, fx):
        async with sessions.begin() as session:
            session.add(_parent_run(fx))
        async with sessions() as session:
            parent = (
                await session.execute(select(AgentRun).where(AgentRun.id == fx.parent))
            ).scalar_one()
        runtime = delegation.DelegationRuntime(parent, LEASE_OWNER, sessions)
        await runtime.restore()

        args = _request_args("동시 요청 검증")
        first, second = await asyncio.gather(
            runtime.request("call-a", dict(args)),
            runtime.request("call-b", dict(args)),
        )

        assert first["status"] == "no_candidates"
        assert second["status"] == "no_candidates"
        async with sessions() as session:
            children = (
                (
                    await session.execute(
                        select(AgentRun.id).where(
                            AgentRun.parent_run_id == fx.parent,
                            AgentRun.delegation_key.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(children) == 1, f"자식 실행이 {len(children)}개 생겼다"
        assert len(set(calls)) == 1
        state = await runtime.restore()
        assert len(state["searches"]) == 1

    _run(scenario)


def test_search_budget_survives_parent_restart(monkeypatch):
    """예산은 delegation_state 로 DB 에 남아 부모를 다시 만들어도 이어진다."""

    async def fake_execute_child(self, child_id):
        return {
            "status": "no_candidates",
            "reason_code": "no_candidates",
            "schedule_run_id": str(child_id),
            "schedule_candidates": [],
            "applied_conditions": {},
        }

    monkeypatch.setattr(
        delegation.DelegationRuntime, "_execute_child", fake_execute_child, raising=True
    )

    async def fresh_runtime(sessions, fx):
        """부모 재시작을 모사한다. 상태는 DB 에서만 읽는다."""
        async with sessions() as session:
            parent = (
                await session.execute(select(AgentRun).where(AgentRun.id == fx.parent))
            ).scalar_one()
        runtime = delegation.DelegationRuntime(parent, LEASE_OWNER, sessions)
        await runtime.restore()
        return runtime

    async def scenario(sessions, fx):
        async with sessions.begin() as session:
            session.add(_parent_run(fx))

        runtime = await fresh_runtime(sessions, fx)
        first = await runtime.request("call-1", _request_args("첫 탐색", days=3, hours=6))
        assert first["status"] == "no_candidates"

        # 재시작. 아래 요청은 이전 상태를 메모리가 아니라 DB 에서 이어받는다.
        runtime = await fresh_runtime(sessions, fx)
        state = await runtime.restore()
        assert len(state["searches"]) == 1
        assert state["tool_requests"] == 1

        second = await runtime.request(
            "call-2", _request_args("두 번째 탐색 사유", days=3, hours=5)
        )
        assert second["status"] == "no_candidates"

        runtime = await fresh_runtime(sessions, fx)
        third = await runtime.request("call-3", _request_args("세 번째 탐색 사유", days=3, hours=4))
        assert third["status"] == "failed"
        assert third["reason_code"] == "search_limit_exceeded"

        async with sessions() as session:
            children = (
                (
                    await session.execute(
                        select(AgentRun.id).where(
                            AgentRun.parent_run_id == fx.parent,
                            AgentRun.delegation_key.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(children) == 2, "예산을 넘겨 자식이 더 생겼다"

    _run(scenario)


def test_reassigned_deal_denies_delegation():
    """담당이 다른 팀으로 넘어가면 같은 부모라도 탐색이 거부된다."""

    async def scenario(sessions, fx):
        async with sessions.begin() as session:
            session.add(_parent_run(fx))
        async with sessions.begin() as session:
            deal = (
                await session.execute(select(SalesDeal).where(SalesDeal.id == fx.deal))
            ).scalar_one()
            deal.team_id = fx.other_team

        async with sessions() as session:
            parent = (
                await session.execute(select(AgentRun).where(AgentRun.id == fx.parent))
            ).scalar_one()
        runtime = delegation.DelegationRuntime(parent, LEASE_OWNER, sessions)
        await runtime.restore()

        result = await runtime.request("call-scope", _request_args("담당 변경 후 탐색"))
        assert result["status"] == "failed"
        assert result["reason_code"] == "schedule_scope_denied"

        async with sessions() as session:
            children = (
                (
                    await session.execute(
                        select(AgentRun.id).where(AgentRun.parent_run_id == fx.parent)
                    )
                )
                .scalars()
                .all()
            )
        assert children == []

        # 정리 대상 복구. 딜을 원래 팀으로 되돌려야 finally 가 지운다.
        async with sessions.begin() as session:
            deal = (
                await session.execute(select(SalesDeal).where(SalesDeal.id == fx.deal))
            ).scalar_one()
            deal.team_id = fx.team

    _run(scenario)


@pytest.mark.skipif(not settings.llm_configured, reason="LLM 미설정")
def test_delegation_loop_with_real_llm(capsys):
    """실제 모델로 도구 루프를 완주한다. 합성 데이터만 외부로 나간다."""

    async def scenario(sessions, fx):
        starts, ends = _window(days=5, hours=8)
        snapshot = {
            "customer_company": {"id": str(fx.company), "name": "합성 도입 병원"},
            "sales_deals": [
                {
                    "id": str(fx.deal),
                    "deal_no": "SYNTH-DELEG-001",
                    "title": "의료기기 신규 도입",
                    "stage_code": "product_demo",
                    "stage_name": "제품 시연",
                    "deal_amount": 1_000_000,
                    "quote_valid_until": (date.today() + timedelta(days=12)).isoformat(),
                }
            ],
            "risk_signals": [
                {
                    "code": "quote_expiring",
                    "severity": "high",
                    "message": "견적 유효기간이 14일 이내로 남았습니다.",
                    "source_refs": [{"type": "sales_deal", "id": str(fx.deal)}],
                }
            ],
            "recent_approved_reports": [
                {
                    "id": str(uuid4()),
                    "report_date": date.today().isoformat(),
                    "content": {
                        "customer_need": "제품 시연 후 도입 범위와 최종 견적 검토",
                        "next_action": "견적 만료 전 의사결정권자 미팅",
                    },
                }
            ],
            "schedule_constraints": {
                "not_before": starts.isoformat(),
                "not_after": ends.isoformat(),
            },
        }
        async with sessions.begin() as session:
            session.add(_parent_run(fx, input_snapshot=snapshot))
        async with sessions() as session:
            parent = (
                await session.execute(select(AgentRun).where(AgentRun.id == fx.parent))
            ).scalar_one()

        output = await delegation.run(parent, LEASE_OWNER, sessions)

        async with sessions() as session:
            refreshed = (
                await session.execute(select(AgentRun).where(AgentRun.id == fx.parent))
            ).scalar_one()
            children = (
                (await session.execute(select(AgentRun).where(AgentRun.parent_run_id == fx.parent)))
                .scalars()
                .all()
            )
        state = refreshed.delegation_state

        with capsys.disabled():
            print("\n=== 위임 루프 실호출 결과 ===")
            print("모델 호출:", state["model_calls"], "/", 5)
            print("도구 요청:", state["tool_requests"], "/", 4)
            print("탐색 횟수:", len(state["searches"]), "/", 2)
            print("자식 실행:", [(str(c.id)[:8], c.status_code) for c in children])
            print("schedule_status:", output.schedule_status)
            print("schedule_reason_code:", output.schedule_reason_code)
            suggestion = output.next_meeting_suggestion
            print(
                "제안:",
                None
                if suggestion is None
                else (suggestion.preferred_starts_at, suggestion.duration_minutes),
            )

        # 예산은 계약대로 지켜져야 한다.
        assert state["model_calls"] <= 5
        assert state["tool_requests"] <= 4
        assert len(state["searches"]) <= 2
        # 자식은 탐색 횟수와 같고, 모두 이 부모·팀 소속이다.
        assert len(children) == len(state["searches"])
        assert all(c.team_id == fx.team for c in children)
        assert all(c.delegation_key is not None for c in children)
        # 제안이 있으면 실제 후보에서 나온 값이어야 한다.
        if output.next_meeting_suggestion is not None:
            assert output.schedule_status in ("candidates_found", "no_candidates")
            assert str(output.next_meeting_suggestion.sales_deal_id) == str(fx.deal)

    _run(scenario)
