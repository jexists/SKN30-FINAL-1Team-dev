from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
from app.models.crm import Activity, CustomerCompany, CustomerContact
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.schemas.contract_suggestions import ContractNextMeetingSuggestionRead
from app.services import schedule_conflicts

router = APIRouter(tags=["contract-suggestions"])

_SEOUL = ZoneInfo("Asia/Seoul")


def _candidates(schedule_run: AgentRun) -> list[dict]:
    raw = (schedule_run.output_snapshot or {}).get("schedule_candidates") or []
    return [candidate for candidate in raw if isinstance(candidate, dict)]


def _read(
    suggestion: ContractNextMeetingSuggestion,
    deal: SalesDeal,
    company_name: str,
    contact_name: str | None,
    owner_name: str,
    schedule_run: AgentRun,
    next_meeting_run: AgentRun | None,
    candidates: list[dict[str, Any]],
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
        schedule_candidates=candidates,
        status_code=suggestion.status_code,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


def _live_candidates(
    schedule_run: AgentRun, owner_member_id: UUID, booked: Sequence[Activity], now: datetime
) -> list[dict[str, Any]]:
    """지금도 고를 수 있는 후보만, 겹침 여부를 붙여 돌려준다.

    후보는 트리거 시점에 계산해 저장한 값이라(아키텍처 2.1) 사용자가 카드를 볼 때는 낡아
    있을 수 있다. 낡는 방식이 둘인데 화면에서 다루는 방법이 다르다.

    * **이미 지난 후보** — 뺀다. 지난 시각은 잡을 방법이 없어 보여 줄 이유가 없다.
      일정관리 에이전트도 후보를 만들 때 같은 검사를 하지만(schedule_management 의 과거
      후보 제거) 그것은 계산 시점 한 번뿐이라, 며칠 묵은 카드는 후보가 통째로 과거가 된다.
    * **그 자리에 다른 일정이 잡힌 후보** — 남기되 표시만 한다. 겹쳐도 사람이 사정을 알고
      그 시간을 택할 수 있다.
    """
    live: list[dict[str, Any]] = []
    for candidate in _candidates(schedule_run):
        window = schedule_conflicts.parse_candidate_window(candidate)
        if window is None:
            # 시각을 못 읽는 후보는 겹침도 과거도 판단할 수 없다. 고르면 등록이 실패하므로
            # 남기지 않는다.
            continue
        starts_at, ends_at = window
        if starts_at < now:
            continue
        marked: dict[str, Any] = {**candidate, "conflicted": False, "conflict_reason": None}
        conflict = schedule_conflicts.first_conflict(
            booked,
            owner_member_id=owner_member_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        if conflict is not None:
            when = conflict.starts_at.astimezone(_SEOUL).strftime("%m/%d %H:%M")
            marked["conflicted"] = True
            marked["conflict_reason"] = f"{when} {conflict.title}"
        live.append(marked)
    return live


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

    shown = [
        (suggestion, deal, company_name, owner_name, schedule_run)
        for suggestion, deal, company_name, owner_name in rows
        # 아직 실행 중이거나 실패한 제안은 보여줄 내용이 없다 — 다음 트리거가 다시 채운다.
        if (schedule_run := schedule_runs.get(suggestion.schedule_management_run_id)) is not None
        and schedule_run.status_code == "completed"
    ]
    booked = await _booked_activities(db, member.team_id, shown)
    now = datetime.now(UTC)

    results: list[ContractNextMeetingSuggestionRead] = []
    for suggestion, deal, company_name, owner_name, schedule_run in shown:
        candidates = _live_candidates(schedule_run, deal.owner_member_id, booked, now)
        # 고를 수 있는 시간이 하나도 안 남은 카드는 그리지 않는다. 승인할 것이 없어 사용자가
        # 할 수 있는 일이 없고, 지난 날짜를 누르게 만들 뿐이다. 제안 자체는 pending 으로
        # 남겨 둔다 — 그 딜에 새 트리거가 걸리면 후보가 다시 계산돼 카드가 돌아온다.
        if not candidates:
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
                candidates,
            )
        )
    return results


async def _booked_activities(
    db: DbSession,
    team_id: UUID,
    shown: Sequence[tuple[ContractNextMeetingSuggestion, SalesDeal, str, str, AgentRun]],
) -> list[Activity]:
    """보여줄 카드들의 후보 시각을 모두 덮는 기간의 일정을 한 번에 가져온다.

    후보마다 조회하면 카드 수 × 후보 수만큼 왕복이 생긴다. 카드는 대개 담당자 한 사람의
    것이고 후보도 며칠 안에 몰려 있어, 전체 기간을 한 번에 읽는 편이 싸다.

    지난 후보는 어차피 화면에서 빠지므로 기간에 넣지 않는다 — 며칠 묵은 카드까지 범위에
    들어오면 겹침을 볼 일 없는 옛 일정을 함께 읽게 된다.
    """
    now = datetime.now(UTC)
    windows = [
        window
        for _s, _d, _c, _o, schedule_run in shown
        for candidate in _candidates(schedule_run)
        if (window := schedule_conflicts.parse_candidate_window(candidate)) is not None
        and window[0] >= now
    ]
    if not windows:
        return []
    return await schedule_conflicts.load_activities_in_range(
        db,
        team_id=team_id,
        owner_member_ids={deal.owner_member_id for _s, deal, _c, _o, _r in shown},
        range_starts_at=min(start for start, _end in windows),
        range_ends_at=max(end for _start, end in windows),
    )


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
