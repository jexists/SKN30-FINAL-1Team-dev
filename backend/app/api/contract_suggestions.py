import logging
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.agents import schedule_management
from app.api.deps import CurrentMember, DbSession
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
from app.models.crm import CustomerCompany, CustomerContact
from app.models.sales import SalesDeal, SalesPipelineStage
from app.models.workspace import Member
from app.schemas.contract_suggestions import (
    ContractNextMeetingGenerationStatusRead,
    ContractNextMeetingSuggestionApply,
    ContractNextMeetingSuggestionApplyRead,
    ContractNextMeetingSuggestionRead,
    ContractNextMeetingSuggestionRefreshRead,
)
from app.services import contract_next_meeting_pipeline

router = APIRouter(tags=["contract-suggestions"])
_SEOUL = ZoneInfo("Asia/Seoul")
logger = logging.getLogger(__name__)


@router.get(
    "/contract-next-meeting-suggestions/generation-status",
    response_model=ContractNextMeetingGenerationStatusRead,
)
async def contract_next_meeting_generation_status(
    member: CurrentMember,
    db: DbSession,
) -> ContractNextMeetingGenerationStatusRead:
    runs = list(
        (
            await db.execute(
                select(AgentRun).where(
                    AgentRun.team_id == member.team_id,
                    AgentRun.status_code.in_(("queued", "running")),
                    AgentRun.source_refs["durable_pipeline"].astext == "true",
                    AgentRun.agent_code.in_(
                        ("contract_management_next_meeting", "schedule_management")
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    deal_ids: set[UUID] = set()
    for run in runs:
        try:
            deal_ids.add(UUID(str((run.source_refs or {}).get("sales_deal_id"))))
        except (TypeError, ValueError):
            continue
    if member.role_code == "member" and deal_ids:
        deal_ids = set(
            (
                await db.execute(
                    select(SalesDeal.id).where(
                        SalesDeal.id.in_(deal_ids),
                        SalesDeal.owner_member_id == member.id,
                        SalesDeal.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    visible_runs = []
    for run in runs:
        try:
            run_deal_id = UUID(str((run.source_refs or {}).get("sales_deal_id")))
        except (TypeError, ValueError):
            continue
        if run_deal_id in deal_ids:
            visible_runs.append(run)
    return ContractNextMeetingGenerationStatusRead(
        generating=bool(visible_runs),
        latest_report_pending=any(
            run.status_code == "queued" and (run.source_refs or {}).get("waiting_for_run_id")
            for run in visible_runs
        ),
        sales_deal_ids=sorted(deal_ids, key=str),
    )


def _read(
    suggestion: ContractNextMeetingSuggestion,
    deal: SalesDeal,
    company_name: str,
    contact_name: str | None,
    owner_name: str,
    schedule_run: AgentRun,
    next_meeting_run: AgentRun | None,
) -> ContractNextMeetingSuggestionRead:
    next_meeting_output = (next_meeting_run.output_snapshot if next_meeting_run else None) or {}
    suggestion_detail = next_meeting_output.get("next_meeting_suggestion") or {}
    return ContractNextMeetingSuggestionRead(
        id=suggestion.id,
        sales_deal_id=suggestion.sales_deal_id,
        customer_company_id=deal.customer_company_id,
        customer_company_name=company_name,
        customer_contact_id=deal.customer_contact_id,
        customer_contact_name=contact_name,
        owner_member_id=deal.owner_member_id,
        owner_display_name=owner_name,
        sales_deal_title=deal.title,
        reason=suggestion_detail.get("reason", ""),
        risks=next_meeting_output.get("risks") or [],
        schedule_management_run_id=suggestion.schedule_management_run_id,
        target_date=suggestion.target_date,
        target_time=suggestion.target_time,
        selected_duration_minutes=suggestion.selected_duration_minutes,
        refresh_reason=suggestion.refresh_reason,
        status_code=suggestion.status_code,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


@router.get(
    "/contract-next-meeting-suggestions",
    response_model=list[ContractNextMeetingSuggestionRead],
)
async def list_contract_next_meeting_suggestions(
    member: CurrentMember,
    db: DbSession,
) -> list[ContractNextMeetingSuggestionRead]:
    """저장된 제안만 조회한다 — LLM을 다시 부르지 않아 화면이 바로 뜬다(설계서 11장)."""
    conditions = [
        ContractNextMeetingSuggestion.team_id == member.team_id,
        ContractNextMeetingSuggestion.status_code == "pending",
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)

    rows = (
        await db.execute(
            select(
                ContractNextMeetingSuggestion, SalesDeal, CustomerCompany.name, Member.display_name
            )
            .join(SalesDeal, SalesDeal.id == ContractNextMeetingSuggestion.sales_deal_id)
            .join(CustomerCompany, CustomerCompany.id == SalesDeal.customer_company_id)
            .join(Member, Member.id == SalesDeal.owner_member_id)
            .where(*conditions)
            .order_by(ContractNextMeetingSuggestion.created_at.desc())
        )
    ).all()
    if not rows:
        return []

    contact_ids = {
        deal.customer_contact_id for _s, deal, _c, _o in rows if deal.customer_contact_id
    }
    contact_names: dict[UUID, str] = {}
    if contact_ids:
        contact_names = dict(
            (
                await db.execute(
                    select(CustomerContact.id, CustomerContact.name).where(
                        CustomerContact.id.in_(contact_ids)
                    )
                )
            ).all()
        )

    schedule_run_ids = {suggestion.schedule_management_run_id for suggestion, _d, _c, _o in rows}
    schedule_runs = {
        run.id: run
        for run in (await db.execute(select(AgentRun).where(AgentRun.id.in_(schedule_run_ids))))
        .scalars()
        .all()
    }
    next_meeting_run_ids = {
        run.parent_run_id for run in schedule_runs.values() if run.parent_run_id is not None
    }
    next_meeting_runs: dict[UUID, AgentRun] = {}
    if next_meeting_run_ids:
        next_meeting_runs = {
            run.id: run
            for run in (
                await db.execute(select(AgentRun).where(AgentRun.id.in_(next_meeting_run_ids)))
            )
            .scalars()
            .all()
        }

    results: list[ContractNextMeetingSuggestionRead] = []
    for suggestion, deal, company_name, owner_name in rows:
        schedule_run = schedule_runs.get(suggestion.schedule_management_run_id)
        # 아직 실행 중이거나 실패한 제안은 보여줄 내용이 없다 — 다음 트리거가 다시 채운다.
        if (
            schedule_run is None
            or schedule_run.status_code != "completed"
            or suggestion.target_date is None
        ):
            continue
        next_meeting_run = (
            next_meeting_runs.get(schedule_run.parent_run_id)
            if schedule_run.parent_run_id
            else None
        )
        results.append(
            _read(
                suggestion,
                deal,
                company_name,
                contact_names.get(deal.customer_contact_id) if deal.customer_contact_id else None,
                owner_name,
                schedule_run,
                next_meeting_run,
            )
        )
    return results


async def _locked_suggestion(
    sales_deal_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> tuple[ContractNextMeetingSuggestion, SalesDeal]:
    row = (
        await db.execute(
            select(ContractNextMeetingSuggestion, SalesDeal)
            .join(SalesDeal, SalesDeal.id == ContractNextMeetingSuggestion.sales_deal_id)
            .where(
                ContractNextMeetingSuggestion.sales_deal_id == sales_deal_id,
                ContractNextMeetingSuggestion.team_id == member.team_id,
            )
            .with_for_update(of=ContractNextMeetingSuggestion)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suggestion_not_found")
    suggestion, deal = row
    if member.role_code == "member" and deal.owner_member_id != member.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suggestion_not_found")
    return suggestion, deal


@router.post(
    "/contract-next-meeting-suggestions/{sales_deal_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reject_contract_next_meeting_suggestion(
    sales_deal_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    suggestion, _deal = await _locked_suggestion(sales_deal_id, member, db)
    if suggestion.status_code != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invalid_state_transition")
    excluded = {
        date.fromisoformat(value)
        for value in (suggestion.excluded_dates or [])
        if isinstance(value, str)
    }
    if suggestion.target_date is not None:
        excluded.add(suggestion.target_date)
    try:
        queued = await contract_next_meeting_pipeline.regenerate(
            sales_deal_id,
            excluded_dates=sorted(excluded),
            refresh_reason="사용자가 기존 추천을 거절했습니다.",
        )
    except Exception:
        logger.exception(
            "recommendation_regeneration_queue_failed",
            extra={"sales_deal_id": str(sales_deal_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="recommendation_refresh_failed",
        ) from None
    if not queued:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="recommendation_refresh_failed",
        )
    # 새 계약관리 작업이 실제로 저장된 뒤에만 기존 카드를 숨긴다. 예약 실패 시에는
    # pending 상태가 유지되어 사용자가 조용히 카드를 잃지 않는다.
    suggestion.status_code = "rejected"
    suggestion.excluded_dates = [value.isoformat() for value in sorted(excluded)]
    suggestion.refresh_reason = "사용자가 기존 추천을 거절했습니다."
    suggestion.updated_at = datetime.now(UTC)
    await db.commit()


@router.post(
    "/contract-next-meeting-suggestions/{sales_deal_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_contract_next_meeting_suggestion(
    sales_deal_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    await _locked_suggestion(sales_deal_id, member, db)
    await db.rollback()
    queued = await contract_next_meeting_pipeline.regenerate(
        sales_deal_id,
        refresh_reason="사용자가 추천 다시 생성을 요청했습니다.",
    )
    if not queued:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="recommendation_refresh_failed",
        )


@router.post(
    "/contract-next-meeting-suggestions/{sales_deal_id}/apply",
    response_model=ContractNextMeetingSuggestionApplyRead,
)
async def apply_contract_next_meeting_suggestion(
    sales_deal_id: UUID,
    payload: ContractNextMeetingSuggestionApply,
    member: CurrentMember,
    db: DbSession,
) -> ContractNextMeetingSuggestionApplyRead:
    suggestion, _deal = await _locked_suggestion(sales_deal_id, member, db)
    if suggestion.status_code != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invalid_state_transition")
    target_date = payload.target_date or suggestion.target_date
    if target_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="target_date_required"
        )
    suggestion.target_date = target_date
    suggestion.selected_duration_minutes = payload.duration_minutes
    suggestion.status_code = "accepted"
    suggestion.updated_at = datetime.now(UTC)
    await db.commit()
    return ContractNextMeetingSuggestionApplyRead(
        sales_deal_id=sales_deal_id,
        target_date=target_date,
        duration_minutes=payload.duration_minutes,
        status_code="accepted",
    )


@router.post(
    "/contract-next-meeting-suggestions/refresh",
    response_model=ContractNextMeetingSuggestionRefreshRead,
)
async def refresh_contract_next_meeting_suggestions(
    member: CurrentMember,
    db: DbSession,
) -> ContractNextMeetingSuggestionRefreshRead:
    conditions = [
        ContractNextMeetingSuggestion.team_id == member.team_id,
        ContractNextMeetingSuggestion.status_code == "pending",
        ContractNextMeetingSuggestion.target_date.is_not(None),
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)
    rows = (
        await db.execute(
            select(ContractNextMeetingSuggestion, SalesDeal, SalesPipelineStage.outcome_code)
            .join(SalesDeal, SalesDeal.id == ContractNextMeetingSuggestion.sales_deal_id)
            .join(SalesPipelineStage, SalesPipelineStage.id == SalesDeal.sales_pipeline_stage_id)
            .where(*conditions)
        )
    ).all()

    replaced_count = 0
    for suggestion, deal, outcome_code in rows:
        try:
            decision = await schedule_management.run(
                {
                    "sales_deal_id": str(deal.id),
                    "target_date": suggestion.target_date,
                    "target_time": suggestion.target_time,
                    "recommendation_status": suggestion.status_code,
                    "deal_outcome_code": outcome_code,
                    "excluded_dates": suggestion.excluded_dates or [],
                    "current_datetime": datetime.now(_SEOUL).isoformat(),
                    "timezone": "Asia/Seoul",
                }
            )
        except Exception:
            # 한 카드의 Agent 실패가 다른 카드 조회와 기존 추천을 지우지 않게 한다.
            continue
        if decision.decision == "ignored":
            suggestion.status_code = "expired"
            suggestion.refresh_reason = decision.reason
            suggestion.updated_at = datetime.now(UTC)
            await db.commit()
            continue
        if decision.decision != "refresh_required":
            continue
        excluded = {
            date.fromisoformat(value)
            for value in (suggestion.excluded_dates or [])
            if isinstance(value, str)
        }
        if suggestion.target_date is not None:
            excluded.add(suggestion.target_date)
        if await contract_next_meeting_pipeline.regenerate(
            deal.id,
            excluded_dates=sorted(excluded),
            refresh_reason=decision.reason,
        ):
            replaced_count += 1
    return ContractNextMeetingSuggestionRefreshRead(
        checked_count=len(rows), replaced_count=replaced_count
    )
