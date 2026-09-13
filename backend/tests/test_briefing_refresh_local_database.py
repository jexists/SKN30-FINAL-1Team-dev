"""브리핑 자동 갱신을 실제 Postgres 에서 확인한다.

`test_briefing_refresh.py` 는 세션을 흉내 내 규칙을 검증한다. 여기서 보는 것은 그 흉내로는
확인할 수 없는 것 둘이다.

* 중복을 막는 주체가 코드가 아니라 **DB 의 UNIQUE 제약**이라는 것.
* 게시 대상을 고르는 규칙이 **실제로 저장된 행**을 읽어도 같게 동작한다는 것.

실행 방법은 docs/technical/local-test-database.md 를 따른다.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.agent import AgentRun
from app.models.configuration import ActivityCategory
from app.models.crm import Activity, CustomerCompany, CustomerContact
from app.models.workspace import Member, Team
from app.services import briefing_refresh

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not settings.run_integration_tests or not settings.database_url,
        reason="로컬 DB 실통합 테스트는 명시적으로 켠다",
    ),
]

NOW = datetime.now(UTC)


def test_briefing_refresh_against_local_database(monkeypatch):
    url = make_url(settings.async_database_url)
    assert settings.app_env == "test"
    assert url.host == "127.0.0.1" and url.port == 55432
    # 예약은 LLM 설정이 있을 때만 큐에 넣는다. 실제 호출은 하지 않는다.
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))
    asyncio.run(_exercise())


class _Fixture:
    """한 팀·한 담당자·미래 미팅 하나. 정리는 team_id 로 한 번에 지운다."""

    def __init__(self):
        self.team_id = uuid4()
        self.member_id = uuid4()
        self.company_id = uuid4()
        self.contact_id = uuid4()
        self.category_id = uuid4()
        self.activity_id = uuid4()


async def _seed(sessions, fx: _Fixture) -> None:
    async with sessions.begin() as session:
        # member.id 는 auth.users 를 참조한다. 로컬 DB 는 그 표만 만들어 두었다.
        await session.execute(
            text("INSERT INTO auth.users (id) VALUES (:id) ON CONFLICT DO NOTHING"),
            {"id": fx.member_id},
        )
        session.add(Team(id=fx.team_id, name="합성 갱신팀"))
        await session.flush()
        session.add(
            Member(
                id=fx.member_id,
                team_id=fx.team_id,
                display_name="합성 담당자",
                role_code="manager",
                active=True,
            )
        )
        session.add(CustomerCompany(id=fx.company_id, team_id=fx.team_id, name="합성 고객사"))
        session.add(
            ActivityCategory(
                id=fx.category_id,
                team_id=fx.team_id,
                position=1,
                code="meeting",
                name="미팅",
                tone="blue",
            )
        )
        await session.flush()
        session.add(
            CustomerContact(
                id=fx.contact_id,
                company_id=fx.company_id,
                owner_member_id=fx.member_id,
                created_by_member_id=fx.member_id,
                name="합성 고객 담당자",
                phone="01000000000",
            )
        )
        await session.flush()
        session.add(
            Activity(
                id=fx.activity_id,
                team_id=fx.team_id,
                owner_member_id=fx.member_id,
                customer_contact_id=fx.contact_id,
                customer_company_id=fx.company_id,
                activity_category_id=fx.category_id,
                title="합성 미래 미팅",
                # 미래 미팅만 갱신 대상이다.
                starts_at=NOW + timedelta(days=3),
            )
        )


async def _briefing_rows(sessions, activity_id) -> list[AgentRun]:
    async with sessions() as session:
        return list(
            (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.source_refs["activity_id"].as_string() == str(activity_id))
                    .order_by(AgentRun.created_at)
                )
            )
            .scalars()
            .all()
        )


async def _exercise() -> None:
    engine = create_async_engine(settings.async_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    fx = _Fixture()
    try:
        await _seed(sessions, fx)

        # 1) 같은 상태에서 두 번 예약해도 실행은 하나다.
        first = await briefing_refresh.schedule_for_activity(fx.activity_id)
        second = await briefing_refresh.schedule_for_activity(fx.activity_id)
        assert len(first) == 1, "첫 예약이 실행을 하나 만들어야 한다"
        assert second == [], "재료가 그대로면 두 번째 예약은 건너뛴다"
        rows = await _briefing_rows(sessions, fx.activity_id)
        assert len(rows) == 1

        run = rows[0]
        assert run.agent_code == briefing_refresh.BRIEFING_AGENT_CODE
        assert run.status_code == "queued"
        # 요청자는 트리거를 누른 사람이 아니라 미팅 담당자다.
        assert run.requested_by_member_id == fx.member_id
        # 예약 시점에 지문을 남겨 둔다. 아직 실행되지 않은 작업도 같은 조회로 찾힌다.
        # 빈 prompt_version 은 agent_run_prompt_version_check 에 걸린다.
        assert run.prompt_version.strip()
        assert run.source_refs["source_revision"]
        assert run.idempotency_key == briefing_refresh.idempotency_key(
            fx.activity_id, run.source_refs["source_revision"]
        )

        # 2) 중복을 막는 주체가 DB 라는 것을 직접 확인한다. 다른 제약에 먼저 걸려 통과하는
        #    일이 없도록 나머지 컬럼은 예약된 행과 똑같이 채운다.
        with pytest.raises(IntegrityError, match="agent_run_requested_by_member_id"):
            async with sessions.begin() as session:
                session.add(
                    AgentRun(
                        id=uuid4(),
                        team_id=fx.team_id,
                        requested_by_member_id=run.requested_by_member_id,
                        agent_code=run.agent_code,
                        trigger_code="system",
                        idempotency_key=run.idempotency_key,
                        status_code="queued",
                        llm_model_name=run.llm_model_name,
                        prompt_version=run.prompt_version,
                        request_snapshot=run.request_snapshot,
                        request_hash=run.request_hash,
                        source_refs=run.source_refs,
                        input_snapshot={},
                    )
                )

        # 3) 미팅을 고치면 지문이 달라져 새 실행이 생긴다.
        async with sessions.begin() as session:
            activity = await session.get(Activity, fx.activity_id)
            activity.starts_at = NOW + timedelta(days=5)
        third = await briefing_refresh.schedule_for_activity(fx.activity_id)
        assert len(third) == 1, "시작 시각이 바뀌면 새로 예약한다"
        rows = await _briefing_rows(sessions, fx.activity_id)
        assert len(rows) == 2
        assert rows[0].idempotency_key != rows[1].idempotency_key

        # 4) 게시 규칙 — 늦게 끝났어도 옛 자료를 본 실행은 뽑히지 않는다.
        stale, fresh = rows[0], rows[1]
        async with sessions.begin() as session:
            stale_row = await session.get(AgentRun, stale.id)
            fresh_row = await session.get(AgentRun, fresh.id)
            for row, observed, finished, summary in (
                (stale_row, "2026-09-12T09:00:00+00:00", NOW + timedelta(minutes=9), "옛 자료"),
                (fresh_row, "2026-09-12T10:00:00+00:00", NOW + timedelta(minutes=1), "새 자료"),
            ):
                row.status_code = "completed"
                row.finished_at = finished
                row.output_snapshot = {"contract_summary": summary}
                row.source_refs = {**row.source_refs, "source_observed_at": observed}

        from app.api import activities as activities_api

        async with sessions() as session:
            member = await session.get(Member, fx.member_id)
            published, latest = await activities_api._briefing_runs(session, member, fx.activity_id)
        assert published is not None
        assert published.id == fresh.id, "더 나중 상태를 본 실행이 게시된다"
        assert published.output_snapshot["contract_summary"] == "새 자료"
        assert latest is not None

        # 5) 그 뒤 갱신이 실패해도 마지막 성공 브리핑은 남는다.
        async with sessions.begin() as session:
            failed = AgentRun(
                id=uuid4(),
                team_id=fx.team_id,
                requested_by_member_id=fx.member_id,
                agent_code=briefing_refresh.BRIEFING_AGENT_CODE,
                trigger_code="system",
                idempotency_key=uuid4(),
                status_code="failed",
                llm_model_name=run.llm_model_name,
                prompt_version=run.prompt_version,
                request_snapshot={},
                request_hash=None,
                source_refs={"activity_id": str(fx.activity_id)},
                input_snapshot={},
                error_message="합성 실패",
            )
            session.add(failed)
        async with sessions() as session:
            member = await session.get(Member, fx.member_id)
            published, latest = await activities_api._briefing_runs(session, member, fx.activity_id)
        assert published is not None and published.id == fresh.id
        assert latest is not None and latest.status_code == "failed"
    finally:
        try:
            async with sessions.begin() as session:
                await session.execute(delete(AgentRun).where(AgentRun.team_id == fx.team_id))
                await session.execute(delete(Activity).where(Activity.team_id == fx.team_id))
                await session.execute(
                    delete(CustomerContact).where(CustomerContact.company_id == fx.company_id)
                )
                await session.execute(
                    delete(ActivityCategory).where(ActivityCategory.team_id == fx.team_id)
                )
                await session.execute(
                    delete(CustomerCompany).where(CustomerCompany.team_id == fx.team_id)
                )
                await session.execute(delete(Member).where(Member.team_id == fx.team_id))
                await session.execute(delete(Team).where(Team.id == fx.team_id))
                await session.execute(
                    text("DELETE FROM auth.users WHERE id = :id"), {"id": fx.member_id}
                )
        finally:
            await engine.dispose()
