"""트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리 시작) 이후 자동으로
"다음 미팅 제안 → 일정 후보"를 이어서 실행하고 결과를 저장한다.

계약에이전트_설계.md 3장·11장의 오케스트레이션이다. 네 트리거 모두 정확히 영업 건 하나를
가리키므로 여러 딜을 비교·랭킹하는 0차 선별은 없다. 라우터는 트리거 커밋 직후 `queue()`만
호출하고, 실제 체이닝은 `BackgroundTasks`로 미룬다 — 실패해도 트리거가 된 원래 요청은
되돌리지 않는다.

캘린더는 여기서 저장한 결과를 조회만 한다(`GET /contract-next-meeting-suggestions`).
화면에서 LLM을 기다리지 않는 대신, 사용자가 보기 전에 미리 계산해 두는 구조다.

일정 후보가 0개로 끝나면 선호 기간을 넓혀 일정관리만 한 번 더 돌린다. 계약관리에게
대체 시간을 되묻는 왕복 협상이 아니다 — 되물어도 같은 폭을 다시 줄 수 있어 원인이
남는다(`_queue_widened_retry`).
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import or_, select, text
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

logger = logging.getLogger(__name__)

# 같은 딜에 트리거가 몰려도(예: 칸반에서 단계를 연달아 옮김) 이 시간 안에는 다시 돌리지
# 않는다. 트리거 한 번이 LLM 호출 두 번이라 그대로 두면 비용이 그대로 곱해진다.
_COOLDOWN = timedelta(minutes=10)

# 후보가 0개일 때 선호 기간을 이만큼으로 넓혀 한 번만 다시 돌린다. 기본 탐색 범위와
# 같은 폭이다 — 실 데이터에서 이 폭으로 돈 실행 55건은 후보 0개가 하나도 없었다.
_RETRY_WINDOW_DAYS = 7


def queue(background: BackgroundTasks, sales_deal_id: UUID, source_refs: dict[str, str]) -> None:
    """트리거 커밋 직후 라우터가 호출한다. source_refs 는 무엇이 이 실행을 촉발했는지 남긴다."""
    background.add_task(_run_pipeline, sales_deal_id, source_refs)


async def _run_pipeline(sales_deal_id: UUID, source_refs: dict[str, str]) -> None:
    if not settings.llm_configured:
        return
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        if not await _reserve(session, sales_deal_id):
            return
        deal = await _open_deal(session, sales_deal_id)
        if deal is None:
            return
        owner = await _member(session, deal.owner_member_id)
        if owner is None:
            return
        source_report_id = source_refs.get("report_id")
        try:
            report_id = UUID(source_report_id) if source_report_id else None
        except (TypeError, ValueError):
            return
        try:
            next_meeting_input = await contract_schedule_snapshots.build_next_meeting_snapshot(
                session,
                owner,
                deal.customer_company_id,
                sales_deal_id=sales_deal_id,
                required_report_id=report_id,
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
                # 스냅샷도 이 딜 하나로 좁혀서 넣는다(build_next_meeting_snapshot 의
                # sales_deal_id). 쿨다운도 딜별로 직전 실행을 찾아야 해서 여기 남긴다.
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
        if not _answers_this_deal(suggestion, sales_deal_id):
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

        team_id = deal.team_id
        schedule_run_id = _add_schedule_run(
            session,
            team_id=team_id,
            sales_deal_id=sales_deal_id,
            parent_run_id=next_meeting_run.id,
            input_snapshot=schedule_input,
        )
        await session.commit()

    await agent_run_service.execute(schedule_run_id)

    async with sessionmaker() as session:
        schedule_run = await session.get(AgentRun, schedule_run_id)
        if schedule_run is None or schedule_run.status_code != "completed":
            return
        if _has_candidates(schedule_run):
            await _upsert_suggestion(session, team_id, sales_deal_id, schedule_run_id)
            return
        retry_run_id = await _queue_widened_retry(
            session,
            team_id=team_id,
            sales_deal_id=sales_deal_id,
            next_meeting_run_id=next_meeting_run_id,
            schedule_run=schedule_run,
        )

    if retry_run_id is None:
        return

    await agent_run_service.execute(retry_run_id)

    async with sessionmaker() as session:
        retry_run = await session.get(AgentRun, retry_run_id)
        if retry_run is None or not _has_candidates(retry_run):
            # 넓혀도 빈손이면 카드가 뜨지 않는다. 화면에는 아무 흔적이 없으므로 로그에만
            # 남긴다 — 사용자에게 알리는 방법은 아직 없다(아키텍처 7.3).
            logger.info(
                "일정 후보가 선호 기간을 넓혀 다시 돌린 뒤에도 0개입니다 "
                "(sales_deal_id=%s, schedule_run_id=%s, retry_run_id=%s)",
                sales_deal_id,
                schedule_run_id,
                retry_run_id,
            )
            return
        await _upsert_suggestion(session, team_id, sales_deal_id, retry_run_id)


async def _queue_widened_retry(
    session: AsyncSession,
    *,
    team_id: UUID,
    sales_deal_id: UUID,
    next_meeting_run_id: UUID,
    schedule_run: AgentRun,
) -> UUID | None:
    """후보가 0개로 끝난 일정관리 실행을 선호 기간만 넓혀 한 번 더 큐잉한다.

    되묻는 협상이 아니라 재시도다. 계약관리에게 대체 시간을 다시 물어봐도 같은 폭을 다시
    줄 수 있어 원인이 남는다 — 좁은 기간 자체를 여기서 넓힌다.

    실 데이터에서 후보 0개는 일정관리 실행 89건 중 2건이었고 둘 다 선호 기간이 30분
    한 칸이었다. 기본 탐색 범위(7일)로 돈 실행에서는 0개가 없었다. 그래서 넓힐 여지가
    있는 실행만 다시 돌리고, 이미 그만큼 넓었던 실행은 같은 입력으로 LLM 을 한 번 더
    태우는 셈이라 건너뛴다.
    """
    if not _can_widen(schedule_run.input_snapshot):
        return None
    deal = await _open_deal(session, sales_deal_id)
    if deal is None:
        return None
    owner = await _member(session, deal.owner_member_id)
    if owner is None:
        return None
    next_meeting_run = await session.get(AgentRun, next_meeting_run_id)
    if next_meeting_run is None:
        return None
    try:
        schedule_input = await contract_schedule_snapshots.build_schedule_snapshot(
            session,
            owner,
            sales_deal_id,
            next_meeting_run,
            None,
            None,
            None,
            min_window_days=_RETRY_WINDOW_DAYS,
        )
    except HTTPException:
        return None

    retry_run_id = _add_schedule_run(
        session,
        team_id=team_id,
        sales_deal_id=sales_deal_id,
        parent_run_id=next_meeting_run_id,
        input_snapshot=schedule_input,
        widened_from_run_id=schedule_run.id,
    )
    await session.commit()
    logger.info(
        "일정 후보가 0개라 선호 기간을 %s일로 넓혀 다시 돌립니다 "
        "(sales_deal_id=%s, schedule_run_id=%s, retry_run_id=%s)",
        _RETRY_WINDOW_DAYS,
        sales_deal_id,
        schedule_run.id,
        retry_run_id,
    )
    return retry_run_id


def _add_schedule_run(
    session: AsyncSession,
    *,
    team_id: UUID,
    sales_deal_id: UUID,
    parent_run_id: UUID,
    input_snapshot: dict,
    widened_from_run_id: UUID | None = None,
) -> UUID:
    """일정관리 실행을 queued 로 세션에 넣고 그 id 를 준다. 커밋은 호출 쪽에서 한다."""
    run_id = uuid4()
    source_refs = {
        "sales_deal_id": str(sales_deal_id),
        "parent_run_id": str(parent_run_id),
    }
    if widened_from_run_id is not None:
        # 이 실행이 왜 두 번 돌았는지 남긴다. 계보(parent_run_id)는 첫 실행과 같으므로
        # 이 값이 없으면 재시도와 원래 실행을 구분할 방법이 없다.
        source_refs["widened_from_run_id"] = str(widened_from_run_id)
    session.add(
        AgentRun(
            id=run_id,
            team_id=team_id,
            parent_run_id=parent_run_id,
            requested_by_member_id=None,
            agent_code="schedule_management",
            trigger_code="system",
            idempotency_key=None,
            status_code="queued",
            llm_model_name=settings.llm_model,
            prompt_version=schedule_management.PROMPT_VERSION,
            source_refs=source_refs,
            input_snapshot=input_snapshot,
            output_snapshot=None,
            evidence=None,
            error_message=None,
            started_at=None,
            finished_at=None,
        )
    )
    return run_id


def _has_candidates(run: AgentRun) -> bool:
    if run.status_code != "completed":
        return False
    return bool((run.output_snapshot or {}).get("schedule_candidates"))


def _can_widen(input_snapshot: dict | None) -> bool:
    """이 실행의 선호 기간을 넓힐 여지가 있는가.

    기간이 비어 있던 실행은 이미 기본 탐색 범위(7일)로 돌았다. 그런 실행을 다시 돌리면
    입력이 글자 하나 다르지 않아 LLM 호출만 늘어난다.
    """
    window = _window_days(input_snapshot)
    return window is not None and window < _RETRY_WINDOW_DAYS


def _window_days(input_snapshot: dict | None) -> float | None:
    """실행 입력에 담긴 선호 기간의 폭(일). 기간이 없거나 읽을 수 없으면 None."""
    snapshot = input_snapshot or {}
    starts_at = snapshot.get("preferred_starts_at")
    ends_at = snapshot.get("preferred_ends_at")
    if not starts_at or not ends_at:
        return None
    try:
        start = datetime.fromisoformat(starts_at)
        end = datetime.fromisoformat(ends_at)
        # 한쪽만 offset 이 없으면 뺄셈이 TypeError 를 낸다. 우리가 쓴 값이라 그럴 일은
        # 없지만, 여기서 터지면 재시도가 아니라 파이프라인 전체가 멈춘다.
        return (end - start) / timedelta(days=1)
    except (TypeError, ValueError):
        return None


def _answers_this_deal(suggestion: dict, sales_deal_id: UUID) -> bool:
    """1차 실행의 제안이 트리거 딜에 대한 것인지 본다.

    입력을 이 딜로 좁혀도(build_next_meeting_snapshot 의 sales_deal_id) LLM 이 다른 딜
    ID 를 지어낼 수 있다. 그대로 두면 다른 딜의 사유와 선호 시간이 트리거 딜의 제안으로
    저장되고, 카드에는 이름과 내용이 어긋난 채 뜬다 — 예외도 로그도 남지 않는다.

    딜 ID 를 아예 주지 않는 출력은 통과시킨다. 프롬프트가 그 필드를 요구하지 않아 원래
    비어 올 수 있고, 그 경우 어긋날 대상 자체가 없다.
    """
    answered = suggestion.get("sales_deal_id")
    return answered is None or str(answered) == str(sales_deal_id)


async def _reserve(session: AsyncSession, sales_deal_id: UUID) -> bool:
    """이 딜의 실행 자리를 잡는다. 이미 남이 잡고 있으면 False.

    확인(_ran_recently)과 기록(queued AgentRun) 사이에 틈이 있으면 트리거가 겹쳤을 때
    백그라운드 작업 둘이 모두 "최근 실행 없음"으로 판단하고 각자 LLM 을 두 번씩 태운다.
    중복 자체는 제안 저장의 UNIQUE 제약이 걸러 내지만, 그 시점은 비용이 이미 나간 뒤다.

    그래서 확인 앞에 딜 단위 잠금을 세워 확인과 기록을 한 번에 통과시킨다. 표를 새로
    만들지 않아도 되도록 PostgreSQL 의 advisory lock 을 쓴다. 잠금은 이 세션이 커밋하거나
    닫힐 때 저절로 풀리고, LLM 실행은 그 바깥에서 돈다.
    """
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"contract_next_meeting:{sales_deal_id}"},
    )
    return not await _ran_recently(session, sales_deal_id)


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
