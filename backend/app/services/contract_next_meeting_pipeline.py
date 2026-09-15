"""트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리 시작) 이후 자동으로
"다음 미팅 날짜 제안 → 오늘 기준 유효성 점검"을 이어서 실행하고 결과를 저장한다.

계약에이전트_설계.md 3장·11장의 오케스트레이션이다. 네 트리거 모두 정확히 영업 건 하나를
가리키므로 여러 딜을 비교·랭킹하는 0차 선별은 없다. 라우터는 트리거 커밋 직후 `queue()`만
호출하고, 실제 체이닝은 `BackgroundTasks`로 미룬다 — 실패해도 트리거가 된 원래 요청은
되돌리지 않는다.

캘린더는 여기서 저장한 결과를 조회만 한다(`GET /contract-next-meeting-suggestions`).
화면에서 LLM을 기다리지 않는 대신, 사용자가 보기 전에 미리 계산해 두는 구조다.
"""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.agents import contract_management, schedule_management
from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.services import contract_schedule_snapshots

# 한 딜의 기존 pipeline이 도는 동안 들어온 최신 보고서는 이 시각까지 잠시 미룬다. 현재
# 두 LLM 호출의 timeout 합보다 길고, 정상 완료 시에는 _wake_latest()가 즉시 당겨 준다.
_FOLLOW_UP_DELAY = timedelta(minutes=2)


def queue(background: BackgroundTasks, sales_deal_id: UUID, source_refs: dict[str, str]) -> None:
    """트리거 커밋 직후 라우터가 호출한다. source_refs 는 무엇이 이 실행을 촉발했는지 남긴다."""
    background.add_task(_run_pipeline, sales_deal_id, source_refs)


async def regenerate(
    sales_deal_id: UUID,
    *,
    excluded_dates: list[date] | None = None,
    refresh_reason: str | None = None,
) -> bool:
    """거절·수동 재생성을 영속 작업으로 예약한다. LLM 완료를 HTTP 요청에서 기다리지 않는다."""
    return await _run_pipeline(
        sales_deal_id,
        {"refresh": "explicit"},
        excluded_dates=excluded_dates,
        refresh_reason=refresh_reason,
    )


async def _run_pipeline(
    sales_deal_id: UUID,
    source_refs: dict[str, str],
    *,
    excluded_dates: list[date] | None = None,
    refresh_reason: str | None = None,
) -> bool:
    if not settings.llm_configured:
        return False
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        await _lock_deal(session, sales_deal_id)
        deal = await _open_deal(session, sales_deal_id)
        if deal is None:
            return False
        owner = await _member(session, deal.owner_member_id)
        if owner is None:
            return False
        source_report_id = source_refs.get("report_id")
        try:
            report_id = UUID(source_report_id) if source_report_id else None
        except (TypeError, ValueError):
            return False
        try:
            next_meeting_input = await contract_schedule_snapshots.build_next_meeting_snapshot(
                session,
                owner,
                deal.customer_company_id,
                sales_deal_id=sales_deal_id,
                required_report_id=report_id,
                excluded_dates=excluded_dates,
            )
        except HTTPException:
            return False

        now = datetime.now(UTC)
        active_run_id = await _active_run_id(session, sales_deal_id, now)
        # 아직 worker가 잡지 않은 이전 요청은 취소하고 가장 최신 입력 하나만 남긴다.
        await session.execute(
            update(AgentRun)
            .where(
                AgentRun.agent_code.in_(
                    ("contract_management_next_meeting", "schedule_management")
                ),
                AgentRun.status_code == "queued",
                AgentRun.source_refs["durable_pipeline"].astext == "true",
                AgentRun.source_refs["sales_deal_id"].astext == str(sales_deal_id),
            )
            .values(
                status_code="cancelled",
                current_stage_code="cancelled",
                error_code="agent_run_superseded",
                error_message="agent_run_superseded",
                finished_at=now,
            )
        )

        team_id = deal.team_id
        next_meeting_run_id = uuid4()
        durable_refs = {
            **source_refs,
            "durable_pipeline": True,
            "customer_company_id": str(deal.customer_company_id),
            "sales_deal_id": str(sales_deal_id),
            "excluded_dates": [value.isoformat() for value in (excluded_dates or [])],
            "refresh_reason": refresh_reason,
        }
        if active_run_id is not None:
            durable_refs["waiting_for_run_id"] = str(active_run_id)
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
                source_refs=durable_refs,
                # 스냅샷에는 Python date/time/UUID가 포함될 수 있다. JSONB 저장 경계에서
                # 변환하지 않으면 거절 재추천 INSERT가 실패한다.
                input_snapshot=jsonable_encoder(next_meeting_input),
                output_snapshot=None,
                evidence=None,
                error_message=None,
                error_code=None,
                current_stage_code="queued",
                attempt_count=0,
                request_snapshot={},
                request_hash=None,
                scope_key=f"contract_next_meeting:{sales_deal_id}:{next_meeting_run_id}",
                payload_expires_at=None,
                payload_redacted_at=None,
                lease_owner=None,
                lease_expires_at=None,
                heartbeat_at=None,
                next_attempt_at=(now + _FOLLOW_UP_DELAY if active_run_id else now),
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                created_at=now,
                started_at=None,
                finished_at=None,
            )
        )
        await session.commit()
    return True


async def resume_completed(run_id: UUID) -> bool:
    """worker가 완료한 영속 추천 작업의 다음 단계를 멱등하게 이어 간다."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        run = await session.get(AgentRun, run_id)
        if run is None or run.status_code != "completed":
            return False

        if run.agent_code == "contract_management_next_meeting":
            if not (run.source_refs or {}).get("durable_pipeline"):
                return False
            existing_child = (
                await session.execute(
                    select(AgentRun.id).where(
                        AgentRun.parent_run_id == run.id,
                        AgentRun.agent_code == "schedule_management",
                    )
                )
            ).scalar_one_or_none()
            if existing_child is not None:
                return False
            suggestion = (run.output_snapshot or {}).get("next_meeting_suggestion")
            sales_deal_id = _source_uuid(run.source_refs, "sales_deal_id")
            if sales_deal_id is None:
                return False
            if not suggestion:
                await _wake_latest(session, sales_deal_id, excluding=run.id)
                await session.commit()
                return False
            if not _answers_this_deal(suggestion, sales_deal_id):
                return False
            deal = await _open_deal(session, sales_deal_id)
            if deal is None:
                return False
            owner = await _member(session, deal.owner_member_id)
            if owner is None:
                return False
            excluded_dates = _source_dates(run.source_refs, "excluded_dates")
            try:
                schedule_input = await contract_schedule_snapshots.build_schedule_snapshot(
                    session,
                    owner,
                    sales_deal_id,
                    run,
                    None,
                    None,
                    excluded_dates=excluded_dates,
                )
            except HTTPException:
                return False
            now = datetime.now(UTC)
            child_id = uuid4()
            session.add(
                AgentRun(
                    id=child_id,
                    team_id=deal.team_id,
                    parent_run_id=run.id,
                    requested_by_member_id=None,
                    agent_code="schedule_management",
                    trigger_code="system",
                    idempotency_key=None,
                    status_code="queued",
                    llm_model_name=settings.llm_model,
                    prompt_version=schedule_management.PROMPT_VERSION,
                    source_refs={
                        "durable_pipeline": True,
                        "sales_deal_id": str(sales_deal_id),
                        "parent_run_id": str(run.id),
                        "excluded_dates": [value.isoformat() for value in excluded_dates],
                        "refresh_reason": (run.source_refs or {}).get("refresh_reason"),
                    },
                    input_snapshot=jsonable_encoder(schedule_input),
                    output_snapshot=None,
                    evidence=None,
                    error_message=None,
                    error_code=None,
                    current_stage_code="queued",
                    attempt_count=0,
                    request_snapshot={},
                    request_hash=None,
                    scope_key=f"contract_schedule:{run.id}",
                    payload_expires_at=None,
                    payload_redacted_at=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    heartbeat_at=None,
                    next_attempt_at=now,
                    input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    created_at=now,
                    started_at=None,
                    finished_at=None,
                )
            )
            await session.commit()
            return True

        if run.agent_code != "schedule_management" or not (run.source_refs or {}).get(
            "durable_pipeline"
        ):
            return False
        if (run.output_snapshot or {}).get("decision") != "valid":
            return False
        sales_deal_id = _source_uuid(run.source_refs, "sales_deal_id")
        if sales_deal_id is None:
            return False
        # 이 실행 중 더 최신 보고서가 들어왔다면 낡은 날짜를 잠깐이라도 카드에 덮어쓰지
        # 않는다. 최신 1건을 즉시 깨워 그 결과만 화면에 남긴다.
        if await _wake_latest(session, sales_deal_id):
            await session.commit()
            return False
        already_saved = (
            await session.execute(
                select(ContractNextMeetingSuggestion.schedule_management_run_id).where(
                    ContractNextMeetingSuggestion.sales_deal_id == sales_deal_id
                )
            )
        ).scalar_one_or_none()
        if already_saved == run.id:
            return False
        target_date_value = (run.input_snapshot or {}).get("target_date")
        if not target_date_value:
            return False
        await _upsert_suggestion(
            session,
            run.team_id,
            sales_deal_id,
            run.id,
            target_date=date.fromisoformat(str(target_date_value)),
            target_time=(
                time.fromisoformat(str(run.input_snapshot["target_time"]))
                if (run.input_snapshot or {}).get("target_time")
                else None
            ),
            excluded_dates=_source_dates(run.source_refs, "excluded_dates"),
            refresh_reason=(run.source_refs or {}).get("refresh_reason"),
        )
        return True


async def resume_pending(limit: int = 20) -> int:
    """재시작 전에 완료됐지만 후속 단계가 끊긴 영속 작업을 다시 연결한다."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        child = aliased(AgentRun)
        child_exists = (
            select(child.id)
            .where(
                child.parent_run_id == AgentRun.id,
                child.agent_code == "schedule_management",
            )
            .exists()
        )
        saved_exists = (
            select(ContractNextMeetingSuggestion.id)
            .where(
                ContractNextMeetingSuggestion.schedule_management_run_id == AgentRun.id
            )
            .exists()
        )
        run_ids = list(
            (
                await session.execute(
                    select(AgentRun.id)
                    .where(
                        AgentRun.status_code == "completed",
                        AgentRun.agent_code.in_(
                            ("contract_management_next_meeting", "schedule_management")
                        ),
                        AgentRun.source_refs["durable_pipeline"].astext == "true",
                        or_(
                            and_(
                                AgentRun.agent_code == "contract_management_next_meeting",
                                AgentRun.output_snapshot["next_meeting_suggestion"]
                                .astext.is_not(None),
                                ~child_exists,
                            ),
                            and_(
                                AgentRun.agent_code == "schedule_management",
                                AgentRun.output_snapshot["decision"].astext == "valid",
                                ~saved_exists,
                            ),
                        ),
                    )
                    .order_by(AgentRun.finished_at.asc().nullsfirst())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
    resumed = 0
    for candidate_id in run_ids:
        resumed += int(await resume_completed(candidate_id))
    return resumed


def _source_uuid(source_refs: dict | None, key: str) -> UUID | None:
    try:
        return UUID(str((source_refs or {}).get(key)))
    except (TypeError, ValueError):
        return None


def _source_dates(source_refs: dict | None, key: str) -> list[date]:
    values = (source_refs or {}).get(key) or []
    parsed = []
    for value in values:
        try:
            parsed.append(date.fromisoformat(str(value)))
        except (TypeError, ValueError):
            continue
    return parsed


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


async def _lock_deal(session: AsyncSession, sales_deal_id: UUID) -> None:
    """동시에 들어온 트리거가 서로의 최신 queued 행을 놓치지 않게 딜 단위로 직렬화한다."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"contract_next_meeting:{sales_deal_id}"},
    )


async def _active_run_id(
    session: AsyncSession, sales_deal_id: UUID, now: datetime
) -> UUID | None:
    """lease가 살아 있는 실제 실행만 찾는다. 완료 시각 기반 쿨다운은 두지 않는다."""
    return (
        await session.execute(
            select(AgentRun.id)
            .where(
                AgentRun.source_refs["sales_deal_id"].astext == str(sales_deal_id),
                AgentRun.agent_code.in_(
                    ("contract_management_next_meeting", "schedule_management")
                ),
                AgentRun.status_code == "running",
                AgentRun.lease_expires_at > now,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def _wake_latest(
    session: AsyncSession, sales_deal_id: UUID, *, excluding: UUID | None = None
) -> bool:
    """실행 중 쌓인 최신 보고서 1건을 즉시 실행 가능 상태로 당긴다."""
    conditions = [
        AgentRun.agent_code == "contract_management_next_meeting",
        AgentRun.status_code == "queued",
        AgentRun.source_refs["durable_pipeline"].astext == "true",
        AgentRun.source_refs["sales_deal_id"].astext == str(sales_deal_id),
    ]
    if excluding is not None:
        conditions.append(AgentRun.id != excluding)
    latest_id = (
        await session.execute(
            select(AgentRun.id)
            .where(*conditions)
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_id is None:
        return False
    await session.execute(
        update(AgentRun).where(AgentRun.id == latest_id).values(next_attempt_at=datetime.now(UTC))
    )
    return True


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
    session: AsyncSession,
    team_id: UUID,
    sales_deal_id: UUID,
    schedule_run_id: UUID,
    *,
    target_date: date,
    target_time: time | None,
    excluded_dates: list[date],
    refresh_reason: str | None,
) -> None:
    """sales_deal_id 당 활성 제안은 최대 1개다. 같은 딜에 새 실행이 나오면 덮어쓴다.

    같은 딜의 과거 카드가 있으면 새 날짜와 실행으로 전체 교체한다.
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
        existing.target_date = target_date
        existing.target_time = target_time
        existing.selected_duration_minutes = None
        existing.excluded_dates = [value.isoformat() for value in excluded_dates]
        existing.refresh_reason = refresh_reason
        existing.applied_activity_id = None
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
            target_date=target_date,
            target_time=target_time,
            selected_duration_minutes=None,
            excluded_dates=[value.isoformat() for value in excluded_dates],
            refresh_reason=refresh_reason,
            applied_activity_id=None,
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
