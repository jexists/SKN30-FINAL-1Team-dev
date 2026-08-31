"""계약관리·일정관리 에이전트 입력을 DB에서 조립한다.

계약에이전트_설계.md / 일정관리에이전트_설계.md 의 위험 판정·후속 미팅·일정 조율 입력을
실제 팀 데이터로 채운다. 임계값(만료 임박 기준일 등)은 기획에서 확정된 값이 아니라 이
모듈에서 정한 초기값이다 — 운영하면서 조정한다.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.content import Report
from app.models.crm import Activity, CustomerCompany, CustomerContact, SupportRequest
from app.models.sales import SalesDeal, SalesPipelineStage
from app.models.workspace import Member

_CONTRACT_EXPIRING_WITHIN_DAYS = 30
_QUOTE_EXPIRING_WITHIN_DAYS = 14
_FOLLOW_UP_OVERDUE_AFTER_DAYS = 30
_CONTRACT_REVISIT_DUE_AFTER_DAYS = 7
_CONTRACT_REVISIT_URGENT_AFTER_DAYS = 14
_SCHEDULE_SEARCH_PADDING_DAYS = 7
_DEFAULT_PREFERRED_WINDOW_DAYS = 7


async def _company_or_404(
    db: AsyncSession, member: Member, customer_company_id: UUID
) -> CustomerCompany:
    company = (
        await db.execute(
            select(CustomerCompany).where(
                CustomerCompany.id == customer_company_id,
                CustomerCompany.team_id == member.team_id,
            )
        )
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_company_not_found",
        )
    return company


async def _open_deals(
    db: AsyncSession, member: Member, customer_company_id: UUID
) -> list[tuple[SalesDeal, SalesPipelineStage]]:
    """이 회사에서 아직 끝나지 않은 딜을 단계 정보와 함께 가져온다."""
    result = await db.execute(
        select(SalesDeal, SalesPipelineStage)
        .join(
            SalesPipelineStage,
            and_(
                SalesPipelineStage.sales_pipeline_id == SalesDeal.sales_pipeline_id,
                SalesPipelineStage.id == SalesDeal.sales_pipeline_stage_id,
            ),
        )
        .where(
            SalesDeal.team_id == member.team_id,
            SalesDeal.customer_company_id == customer_company_id,
            SalesDeal.deleted_at.is_(None),
            SalesPipelineStage.phase_code != "closed",
        )
    )
    return list(result.all())


async def _member_open_deals(
    db: AsyncSession, member: Member
) -> list[tuple[SalesDeal, SalesPipelineStage, CustomerCompany]]:
    """이 담당자가 소유한, 아직 끝나지 않은 딜을 회사 정보와 함께 가져온다."""
    result = await db.execute(
        select(SalesDeal, SalesPipelineStage, CustomerCompany)
        .join(
            SalesPipelineStage,
            and_(
                SalesPipelineStage.sales_pipeline_id == SalesDeal.sales_pipeline_id,
                SalesPipelineStage.id == SalesDeal.sales_pipeline_stage_id,
            ),
        )
        .join(CustomerCompany, CustomerCompany.id == SalesDeal.customer_company_id)
        .where(
            SalesDeal.team_id == member.team_id,
            SalesDeal.owner_member_id == member.id,
            SalesDeal.deleted_at.is_(None),
            SalesPipelineStage.phase_code != "closed",
        )
    )
    return list(result.all())


async def _last_activity_by_deal(
    db: AsyncSession, member: Member, deal_ids: list[UUID]
) -> dict[UUID, datetime]:
    if not deal_ids:
        return {}
    result = await db.execute(
        select(Activity.sales_deal_id, func.max(Activity.starts_at))
        .where(
            Activity.team_id == member.team_id,
            Activity.sales_deal_id.in_(deal_ids),
            Activity.deleted_at.is_(None),
        )
        .group_by(Activity.sales_deal_id)
    )
    return {deal_id: last_start for deal_id, last_start in result.all()}


async def _unresolved_support_signals(
    db: AsyncSession, member: Member, customer_company_id: UUID
) -> list[dict[str, Any]]:
    """이 회사에 걸린, 아직 처리 중인 C/S 요청."""
    result = await db.execute(
        select(SupportRequest).where(
            SupportRequest.team_id == member.team_id,
            SupportRequest.customer_company_id == customer_company_id,
            SupportRequest.status_code == "in_progress",
        )
    )
    signals: list[dict[str, Any]] = []
    for request in result.scalars().all():
        signals.append(
            {
                "code": "unresolved_support",
                "severity": "high" if request.is_urgent else "medium",
                "sales_deal_id": str(request.sales_deal_id),
                "source_refs": [{"type": "support_request", "id": str(request.id)}],
                "detail": request.title,
            }
        )
    return signals


def _deal_risk_signals(
    deal: SalesDeal, stage: SalesPipelineStage, last_activity_at: datetime | None, today: date
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    ref = [{"type": "sales_deal", "id": str(deal.id)}]

    if deal.contract_ends_on is not None:
        days_left = (deal.contract_ends_on - today).days
        if days_left <= _CONTRACT_EXPIRING_WITHIN_DAYS:
            signals.append(
                {
                    "code": "contract_expiring",
                    "severity": "high" if days_left <= 7 else "medium",
                    "sales_deal_id": str(deal.id),
                    "source_refs": ref,
                    "detail": f"contract_ends_on={deal.contract_ends_on.isoformat()}",
                }
            )

    if deal.quote_valid_until is not None:
        days_left = (deal.quote_valid_until - today).days
        if days_left <= _QUOTE_EXPIRING_WITHIN_DAYS:
            signals.append(
                {
                    "code": "quote_expiring",
                    "severity": "high" if days_left <= 3 else "medium",
                    "sales_deal_id": str(deal.id),
                    "source_refs": ref,
                    "detail": f"quote_valid_until={deal.quote_valid_until.isoformat()}",
                }
            )

    if deal.expected_delivery_at is not None:
        now = datetime.now(UTC)
        expected = deal.expected_delivery_at
        if expected.tzinfo is None:
            expected = expected.replace(tzinfo=UTC)
        if expected < now:
            signals.append(
                {
                    "code": "delivery_delay_risk",
                    "severity": "high",
                    "sales_deal_id": str(deal.id),
                    "source_refs": ref,
                    "detail": f"expected_delivery_at={deal.expected_delivery_at.isoformat()}",
                }
            )

    # 활동이 없으면 딜을 연 시점을 마지막 접촉 기준으로 삼는다. 신규 딜을 곧바로
    # "오래 연락 안 함"으로 잘못 판정하지 않기 위해서다.
    reference_at = last_activity_at or datetime.combine(deal.opened_on, datetime.min.time())
    if reference_at.tzinfo is None:
        reference_at = reference_at.replace(tzinfo=UTC)
    days_since_contact = (datetime.now(UTC) - reference_at).days
    if days_since_contact >= _FOLLOW_UP_OVERDUE_AFTER_DAYS:
        signals.append(
            {
                "code": "follow_up_overdue",
                "severity": "medium",
                "sales_deal_id": str(deal.id),
                "source_refs": ref,
                "detail": f"days_since_contact={days_since_contact}",
            }
        )

    if deal.contract_signed_on is not None:
        days_since_signed = (today - deal.contract_signed_on).days
        if days_since_signed >= _CONTRACT_REVISIT_URGENT_AFTER_DAYS:
            revisit_severity = "high"
        elif days_since_signed >= _CONTRACT_REVISIT_DUE_AFTER_DAYS:
            revisit_severity = "medium"
        else:
            revisit_severity = None
        if revisit_severity is not None:
            signals.append(
                {
                    "code": "contract_revisit_due",
                    "severity": revisit_severity,
                    "sales_deal_id": str(deal.id),
                    "source_refs": ref,
                    "detail": f"contract_signed_on={deal.contract_signed_on.isoformat()}",
                }
            )

    if stage.phase_code == "contract" and (deal.contract_no is None or not deal.deal_amount):
        signals.append(
            {
                "code": "missing_contract_information",
                "severity": "medium",
                "sales_deal_id": str(deal.id),
                "source_refs": ref,
                "detail": "contract_no_or_deal_amount_missing",
            }
        )

    return signals


def _deal_summary(deal: SalesDeal, stage: SalesPipelineStage) -> dict[str, Any]:
    return {
        "id": str(deal.id),
        "title": deal.title,
        "stage_phase_code": stage.phase_code,
        "stage_outcome_code": stage.outcome_code,
        "deal_amount": deal.deal_amount,
        "contract_ends_on": deal.contract_ends_on.isoformat() if deal.contract_ends_on else None,
        "quote_valid_until": (
            deal.quote_valid_until.isoformat() if deal.quote_valid_until else None
        ),
        "expected_delivery_at": (
            deal.expected_delivery_at.isoformat() if deal.expected_delivery_at else None
        ),
    }


async def _recent_approved_reports(
    db: AsyncSession, member: Member, deal_ids: list[UUID]
) -> list[dict[str, Any]]:
    if not deal_ids:
        return []
    result = await db.execute(
        select(Report)
        .where(
            Report.team_id == member.team_id,
            Report.status_code == "approved",
            Report.sales_deal_id.in_(deal_ids),
        )
        .order_by(Report.report_date.desc())
        .limit(5)
    )
    return [
        {
            "id": str(report.id),
            "sales_deal_id": str(report.sales_deal_id),
            "report_date": report.report_date.isoformat(),
            "content": report.content,
        }
        for report in result.scalars().all()
    ]


async def build_candidate_selection_snapshot(db: AsyncSession, member: Member) -> dict[str, Any]:
    """포트폴리오 선별(select_next_meeting_candidates) 입력.

    로그인한 담당자가 맡은 모든 회사·딜을 훑어 위험 신호를 계산한다. 위험 신호 계산 자체는
    결정적 규칙(_deal_risk_signals)을 그대로 쓴다 — 신호가 하나도 없는 딜은 애초에 후보에
    올리지 않아 프롬프트 크기와 LLM 호출 비용을 줄인다. 그 신호들 중 지금 다음 미팅 제안을
    보여줄 딜을 최종 선별하는 것만 LLM에 맡긴다.
    """
    deals = await _member_open_deals(db, member)
    deal_ids = [deal.id for deal, _stage, _company in deals]
    last_activity = await _last_activity_by_deal(db, member, deal_ids)
    today = datetime.now(UTC).date()

    candidates: list[dict[str, Any]] = []
    for deal, stage, company in deals:
        risk_signals = _deal_risk_signals(deal, stage, last_activity.get(deal.id), today)
        if not risk_signals:
            continue
        candidates.append(
            {
                "customer_company_id": str(company.id),
                "customer_company_name": company.name,
                "sales_deal_id": str(deal.id),
                "sales_deal_title": deal.title,
                "stage_code": stage.stage_code,
                "stage_phase_code": stage.phase_code,
                "risk_signals": risk_signals,
            }
        )

    return {"candidates": candidates}


async def build_next_meeting_snapshot(
    db: AsyncSession, member: Member, customer_company_id: UUID
) -> dict[str, Any]:
    """계약관리 1차 실행(propose_next_meeting) 입력. 위험 판정 신호를 계산해 넣는다."""
    company = await _company_or_404(db, member, customer_company_id)
    deals = await _open_deals(db, member, customer_company_id)
    deal_ids = [deal.id for deal, _stage in deals]
    last_activity = await _last_activity_by_deal(db, member, deal_ids)
    today = datetime.now(UTC).date()

    risk_signals: list[dict[str, Any]] = []
    for deal, stage in deals:
        risk_signals.extend(_deal_risk_signals(deal, stage, last_activity.get(deal.id), today))
    risk_signals.extend(await _unresolved_support_signals(db, member, customer_company_id))

    return {
        "customer_company": {"id": str(company.id), "name": company.name},
        "sales_deals": [_deal_summary(deal, stage) for deal, stage in deals],
        "risk_signals": risk_signals,
        "recent_approved_reports": await _recent_approved_reports(db, member, deal_ids),
    }


async def build_briefing_snapshot(
    db: AsyncSession,
    member: Member,
    activity_id: UUID,
) -> dict[str, Any]:
    """확정 미팅에 표시할 브리핑 입력을 일정 ID로 다시 조회한다.

    자료요약 Agent(RAG)가 아직 없어 document_summaries 는 항상 빈 값이다 — 기획 문서의
    "이전 단계 데이터가 없어도 최소 동작해야 한다" 원칙에 따라 비어 있는 채로 진행한다.
    """
    row = (
        await db.execute(
            select(Activity, CustomerCompany)
            .join(CustomerContact, Activity.customer_contact_id == CustomerContact.id)
            .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
            .where(
                Activity.id == activity_id,
                Activity.team_id == member.team_id,
                Activity.deleted_at.is_(None),
                CustomerCompany.team_id == member.team_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="meeting_activity_not_found"
        )
    activity, company = row
    if member.role_code == "member" and activity.owner_member_id != member.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="meeting_activity_not_found"
        )

    customer_company_id = company.id
    company = await _company_or_404(db, member, customer_company_id)
    deals = await _open_deals(db, member, customer_company_id)

    return {
        "customer_company": {"id": str(company.id), "name": company.name},
        "sales_deals": [_deal_summary(deal, stage) for deal, stage in deals],
        "approved_next_meeting": {
            "activity_id": str(activity.id),
            "sales_deal_id": str(activity.sales_deal_id) if activity.sales_deal_id else None,
            "title": activity.title,
            "starts_at": activity.starts_at.isoformat(),
            "ends_at": activity.ends_at.isoformat() if activity.ends_at else None,
            "location": activity.location,
        },
        "document_summaries": [],
    }


async def build_schedule_snapshot(
    db: AsyncSession,
    member: Member,
    sales_deal_id: UUID,
    parent_run: AgentRun | None,
    preferred_starts_at: str | None,
    preferred_ends_at: str | None,
    duration_minutes: int | None,
) -> dict[str, Any]:
    """일정관리 실행 입력. 선호 시간대는 부모 실행(계약관리 제안) 또는 요청값에서 온다."""
    deal = (
        await db.execute(
            select(SalesDeal).where(
                SalesDeal.id == sales_deal_id,
                SalesDeal.team_id == member.team_id,
                SalesDeal.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sales_deal_not_found")

    reason: str | None = None
    if parent_run is not None:
        suggestion = (parent_run.output_snapshot or {}).get("next_meeting_suggestion") or {}
        preferred_starts_at = suggestion.get("preferred_starts_at")
        preferred_ends_at = suggestion.get("preferred_ends_at")
        duration_minutes = suggestion.get("duration_minutes", 60)
        reason = suggestion.get("reason")

    if preferred_starts_at is None or preferred_ends_at is None:
        # 계약관리 제안에 구체적인 선호 시간대가 없으면(예: 근거만 있고 날짜 미정),
        # 오늘부터 일주일을 기본 탐색 범위로 둔다.
        now = datetime.now(UTC)
        window_start = now
        window_end = now + timedelta(days=_DEFAULT_PREFERRED_WINDOW_DAYS)
    else:
        window_start = datetime.fromisoformat(preferred_starts_at)
        window_end = datetime.fromisoformat(preferred_ends_at)

    padding = timedelta(days=_SCHEDULE_SEARCH_PADDING_DAYS)
    activities = (
        (
            await db.execute(
                select(Activity).where(
                    Activity.team_id == member.team_id,
                    Activity.owner_member_id == deal.owner_member_id,
                    Activity.deleted_at.is_(None),
                    Activity.starts_at >= window_start - padding,
                    Activity.starts_at <= window_end + padding,
                )
            )
        )
        .scalars()
        .all()
    )

    return {
        "sales_deal_id": str(deal.id),
        "preferred_starts_at": preferred_starts_at,
        "preferred_ends_at": preferred_ends_at,
        "duration_minutes": duration_minutes or 60,
        "reason": reason,
        "activities": [
            {
                "id": str(activity.id),
                "owner_member_id": str(activity.owner_member_id),
                "starts_at": activity.starts_at.isoformat(),
                "ends_at": activity.ends_at.isoformat() if activity.ends_at else None,
                "all_day": activity.all_day,
            }
            for activity in activities
        ],
    }
