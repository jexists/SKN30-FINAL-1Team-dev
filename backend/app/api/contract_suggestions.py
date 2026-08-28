from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
from app.models.crm import CustomerCompany, CustomerContact
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.schemas.contract_suggestions import ContractNextMeetingSuggestionRead

router = APIRouter(tags=["contract-suggestions"])


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
        schedule_candidates=(schedule_run.output_snapshot or {}).get("schedule_candidates") or [],
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
        for run in (
            await db.execute(select(AgentRun).where(AgentRun.id.in_(schedule_run_ids)))
        )
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
        if schedule_run is None or schedule_run.status_code != "completed":
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


@router.post(
    "/contract-next-meeting-suggestions/{sales_deal_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def dismiss_contract_next_meeting_suggestion(
    sales_deal_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    row = (
        await db.execute(
            select(ContractNextMeetingSuggestion, SalesDeal)
            .join(SalesDeal, SalesDeal.id == ContractNextMeetingSuggestion.sales_deal_id)
            .where(
                ContractNextMeetingSuggestion.sales_deal_id == sales_deal_id,
                ContractNextMeetingSuggestion.team_id == member.team_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suggestion_not_found")
    suggestion, deal = row
    if member.role_code == "member" and deal.owner_member_id != member.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suggestion_not_found")
    if suggestion.status_code != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="invalid_state_transition")
    suggestion.status_code = "dismissed"
    suggestion.updated_at = datetime.now(UTC)
    await db.commit()
