"""트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리 시작) 이후 자동으로
"다음 미팅 제안 → 일정 후보"를 이어서 실행하고 결과를 저장한다.

계약에이전트_설계.md 3장·11장의 오케스트레이션이다. 네 트리거 모두 정확히 영업 건 하나를
가리키므로 여러 딜을 비교·랭킹하는 0차 선별은 없다. 라우터는 트리거 커밋 직후 `queue()`만
호출하고, 실제 체이닝은 `BackgroundTasks`로 미룬다 — 실패해도 트리거가 된 원래 요청은
되돌리지 않는다.

캘린더는 여기서 저장한 결과를 조회만 한다(`GET /contract-next-meeting-suggestions`).
화면에서 LLM을 기다리지 않는 대신, 사용자가 보기 전에 미리 계산해 두는 구조다.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import contract_management, schedule_management
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.services import agent_runs as agent_run_service
from app.services import contract_schedule_snapshots

# 같은 딜에 트리거가 몰려도(예: 칸반에서 단계를 연달아 옮김) 이 시간 안에는 다시 돌리지
# 않는다. 트리거 한 번이 LLM 호출 두 번이라 그대로 두면 비용이 그대로 곱해진다.
_COOLDOWN = timedelta(minutes=10)


def queue(background: BackgroundTasks, sales_deal_id: UUID, source_refs: dict[str, str]) -> None:
    """트리거 커밋 직후 라우터가 호출한다. source_refs 는 무엇이 이 실행을 촉발했는지 남긴다."""
    background.add_task(_run_pipeline, sales_deal_id, source_refs)


async def _run_pipeline(sales_deal_id: UUID, source_refs: dict[str, str]) -> None:
    if not settings.llm_configured:
        return
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        if await _ran_recently(session, sales_deal_id):
            return
        deal = await _open_deal(session, sales_deal_id)
        if deal is None:
            return
        owner = await _member(session, deal.owner_member_id)
        if owner is None:
            return
        try:
            next_meeting_input = await contract_schedule_snapshots.build_next_meeting_snapshot(
                session, owner, deal.customer_company_id
            )
        except HTTPException:
            return

        team_id = deal.team_id
        next_meeting_run_id = uuid4()
        session.add(
            AgentRun(
                id=next_meeting_run_id,
                team_id=team_id,
                parent_run_id=None,
                requested_by_member_id=None,
                agent_code="contract_management_next_meeting",
                trigger_code="system",
                idempotency_key=None,
                status_code="queued",
                llm_model_name=settings.llm_model,
                prompt_version=contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
                # 이 실행 자체는 회사 단위 스냅샷(build_next_meeting_snapshot)으로 돌지만,
                # 트리거는 영업 건 하나를 가리킨다(파일 상단 docstring) — 쿨다운이 딜별로
                # 직전 실행을 찾아야 해서 sales_deal_id 를 여기 남긴다.
                source_refs={
                    **source_refs,
                    "customer_company_id": str(deal.customer_company_id),
                    "sales_deal_id": str(sales_deal_id),
                },
                input_snapshot=next_meeting_input,
                output_snapshot=None,
                evidence=None,
                error_message=None,
                started_at=None,
                finished_at=None,
            )
        )
        await session.commit()

    await agent_run_service.execute(next_meeting_run_id)

    async with sessionmaker() as session:
        next_meeting_run = await session.get(AgentRun, next_meeting_run_id)
        if next_meeting_run is None or next_meeting_run.status_code != "completed":
            return
        suggestion = (next_meeting_run.output_snapshot or {}).get("next_meeting_suggestion")
        if not suggestion:
            return

        deal = await _open_deal(session, sales_deal_id)
        if deal is None:
            return
        owner = await _member(session, deal.owner_member_id)
        if owner is None:
            return
        try:
            schedule_input = await contract_schedule_snapshots.build_schedule_snapshot(
                session, owner, sales_deal_id, next_meeting_run, None, None, None
            )
        except HTTPException:
            return

        schedule_run_id = uuid4()
        team_id = deal.team_id
        session.add(
            AgentRun(
                id=schedule_run_id,
                team_id=team_id,
                parent_run_id=next_meeting_run.id,
                requested_by_member_id=None,
                agent_code="schedule_management",
                trigger_code="system",
                idempotency_key=None,
                status_code="queued",
                llm_model_name=settings.llm_model,
                prompt_version=schedule_management.PROMPT_VERSION,
                source_refs={
                    "sales_deal_id": str(sales_deal_id),
                    "parent_run_id": str(next_meeting_run.id),
                },
                input_snapshot=schedule_input,
                output_snapshot=None,
                evidence=None,
                error_message=None,
                started_at=None,
                finished_at=None,
            )
        )
        await session.commit()

    await agent_run_service.execute(schedule_run_id)

    async with sessionmaker() as session:
        schedule_run = await session.get(AgentRun, schedule_run_id)
        if schedule_run is None or schedule_run.status_code != "completed":
            return
        candidates = (schedule_run.output_snapshot or {}).get("schedule_candidates") or []
        if not candidates:
            return
        await _upsert_suggestion(session, team_id, sales_deal_id, schedule_run_id)


async def _ran_recently(session: AsyncSession, sales_deal_id: UUID) -> bool:
    """이 딜에 대한 파이프라인이 방금 돌았거나 지금 돌고 있으면 True.

    아직 시작 전(queued)이거나 진행 중(running)인 실행은 시각과 무관하게 막는다 — 트리거가
    거의 동시에 두 번 들어온 경우다.
    """
    since = datetime.now(UTC) - _COOLDOWN
    found = (
        await session.execute(
            select(AgentRun.id)
            .where(
                AgentRun.source_refs["sales_deal_id"].astext == str(sales_deal_id),
                AgentRun.agent_code == "contract_management_next_meeting",
                or_(
                    AgentRun.status_code.in_(("queued", "running")),
                    AgentRun.started_at >= since,
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return found is not None


async def _open_deal(session: AsyncSession, sales_deal_id: UUID) -> SalesDeal | None:
    return (
        await session.execute(
            select(SalesDeal).where(SalesDeal.id == sales_deal_id, SalesDeal.deleted_at.is_(None))
        )
    ).scalar_one_or_none()


async def _member(session: AsyncSession, member_id: UUID) -> Member | None:
    return (
        await session.execute(select(Member).where(Member.id == member_id))
    ).scalar_one_or_none()


async def _upsert_suggestion(
    session: AsyncSession, team_id: UUID, sales_deal_id: UUID, schedule_run_id: UUID
) -> None:
    """sales_deal_id 당 활성 제안은 최대 1개다. 같은 딜에 새 실행이 나오면 덮어쓴다.

    사용자가 닫아 둔(dismissed) 제안도 pending 으로 되돌린다 — 그 딜에 새 변화가 생겼다는
    뜻이라 다시 보여줄 근거가 생긴 것으로 본다.
    """
    now = datetime.now(UTC)
    existing = (
        await session.execute(
            select(ContractNextMeetingSuggestion).where(
                ContractNextMeetingSuggestion.sales_deal_id == sales_deal_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.schedule_management_run_id = schedule_run_id
        existing.status_code = "pending"
        existing.updated_at = now
        await session.commit()
        return
    session.add(
        ContractNextMeetingSuggestion(
            id=uuid4(),
            team_id=team_id,
            sales_deal_id=sales_deal_id,
            schedule_management_run_id=schedule_run_id,
            status_code="pending",
            created_at=now,
            updated_at=now,
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        # 같은 딜에 대해 트리거가 동시에 겹쳐 UNIQUE(sales_deal_id) 에 걸렸다 — 다른 실행이
        # 이미 upsert했다는 뜻이니 이 결과는 버리고 조용히 넘어간다.
        await session.rollback()
