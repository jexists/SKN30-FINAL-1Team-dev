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
from app.services.report_sources import _NON_BODY_KEYS, _shared_body

_CONTRACT_EXPIRING_WITHIN_DAYS = 30
_QUOTE_EXPIRING_WITHIN_DAYS = 14
_FOLLOW_UP_OVERDUE_AFTER_DAYS = 30
_CONTRACT_REVISIT_DUE_AFTER_DAYS = 7
_CONTRACT_REVISIT_URGENT_AFTER_DAYS = 14
_SCHEDULE_SEARCH_PADDING_DAYS = 7
_DEFAULT_PREFERRED_WINDOW_DAYS = 7


def _parse_aware_or_none(value: str) -> datetime | None:
    """ISO 문자열을 tz-aware datetime으로 파싱한다. 형식이 깨졌으면 None.

    LLM 출력이나 클라이언트 요청값은 offset이 없을(naive) 수 있다 — 그런 값은 UTC로 본다.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


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


async def _deal_ids_with_upcoming_activity(
    db: AsyncSession, member: Member, deal_ids: list[UUID]
) -> set[UUID]:
    """앞으로 예정된(starts_at > now) 활동이 이미 있는 딜 id 집합.

    이미 뭔가 잡혀 있으면 0차 선별에서 "다음 미팅 필요"로 다시 올리지 않는다.
    """
    if not deal_ids:
        return set()
    result = await db.execute(
        select(Activity.sales_deal_id).where(
            Activity.team_id == member.team_id,
            Activity.sales_deal_id.in_(deal_ids),
            Activity.deleted_at.is_(None),
            Activity.starts_at > datetime.now(UTC),
        )
    )
    return {deal_id for (deal_id,) in result.all()}


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


async def _recent_finalized_reports(
    db: AsyncSession, member: Member, deal_ids: list[UUID]
) -> list[dict[str, Any]]:
    """작성자가 확정한(submitted) 보고서까지 근거로 쓴다.

    approved 는 팀장 검토까지 끝난 상태인데 그 검토 화면이 아직 없어, approved 만 보면
    방금 확정한 보고서가 영영 입력에 들어오지 못한다. 보고서 확정이 곧 이 파이프라인의
    트리거이기도 하므로(계약에이전트_설계.md 3장) 두 상태를 함께 본다.
    """
    if not deal_ids:
        return []
    result = await db.execute(
        select(Report)
        .where(
            Report.team_id == member.team_id,
            Report.status_code.in_(("approved", "submitted")),
            Report.sales_deal_id.in_(deal_ids),
        )
        .order_by(Report.report_date.desc())
        .limit(5)
    )
    output = []
    shared_by_activity = {}
    for report in result.scalars().all():
        if not isinstance(report.content, dict):
            raise HTTPException(422, "report_source_content_invalid")
        content = {key: value for key, value in report.content.items() if key not in _NON_BODY_KEYS}
        shared = report.content.get("meeting_shared")
        if shared is not None:
            if not isinstance(shared, dict) or report.source_activity_id is None:
                raise HTTPException(422, "report_source_shared_invalid")
            # 딜 본문은 유지하고 공통/미지정 맥락만 별도 전달한다. AI·ML 메타는 제외한다.
            content["meeting_shared"] = {
                "common_report": _shared_body(shared.get("common_report")),
                "unassigned_report": _shared_body(shared.get("unassigned_report")),
            }
            previous = shared_by_activity.get(report.source_activity_id)
            if previous is not None and previous != content["meeting_shared"]:
                raise HTTPException(409, "report_source_shared_conflict")
            shared_by_activity[report.source_activity_id] = content["meeting_shared"]
        output.append(
            {
                "id": str(report.id),
                "sales_deal_id": str(report.sales_deal_id),
                "source_activity_id": (
                    str(report.source_activity_id) if report.source_activity_id else None
                ),
                "report_date": report.report_date.isoformat(),
                "content": content,
            }
        )
    return output


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
    upcoming = await _deal_ids_with_upcoming_activity(db, member, deal_ids)
    today = datetime.now(UTC).date()

    candidates: list[dict[str, Any]] = []
    for deal, stage, company in deals:
        if deal.id in upcoming:
            continue
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
    db: AsyncSession,
    member: Member,
    customer_company_id: UUID,
    sales_deal_id: UUID | None = None,
) -> dict[str, Any]:
    """계약관리 1차 실행(propose_next_meeting) 입력. 위험 판정 신호를 계산해 넣는다.

    sales_deal_id 를 주면 그 딜 하나로 좁힌다. 트리거 기반 파이프라인
    (contract_next_meeting_pipeline)은 영업 건 하나를 가리키는 신호에서 출발하는데,
    회사의 딜을 전부 넣으면 같은 고객사에 딜이 둘 이상일 때 LLM 이 다른 딜을 골라
    답할 수 있다. 그 답을 트리거 딜의 제안으로 저장하면 카드에 이름과 내용이
    어긋난 채 뜨고, 예외도 로그도 남지 않는다.

    기본값이 None 인 것은 회사 단위로 도는 기존 호출부(POST /agent-runs 의 수동 실행,
    agent_runs._build_input)를 그대로 두기 위해서다.
    """
    company = await _company_or_404(db, member, customer_company_id)
    deals = await _open_deals(db, member, customer_company_id)
    if sales_deal_id is not None:
        deals = [(deal, stage) for deal, stage in deals if deal.id == sales_deal_id]
        if not deals:
            # 이 회사의 열린 딜이 아니다(닫혔거나 다른 회사). 빈 스냅샷을 넘기면 LLM 이
            # 근거 없이 지어내므로 여기서 끊는다 — 파이프라인은 이 예외를 받고 종료한다.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="sales_deal_not_found"
            )
    deal_ids = [deal.id for deal, _stage in deals]
    last_activity = await _last_activity_by_deal(db, member, deal_ids)
    today = datetime.now(UTC).date()

    risk_signals: list[dict[str, Any]] = []
    for deal, stage in deals:
        risk_signals.extend(_deal_risk_signals(deal, stage, last_activity.get(deal.id), today))
    # CS 미해결은 딜이 아니라 고객사에 붙는 신호라 딜을 좁혀도 그대로 넣는다. 어느 딜을
    # 고를지 흔드는 값이 아니라, 고른 딜을 언제 만날지 판단하는 맥락이다.
    risk_signals.extend(await _unresolved_support_signals(db, member, customer_company_id))

    return {
        "customer_company": {"id": str(company.id), "name": company.name},
        "sales_deals": [_deal_summary(deal, stage) for deal, stage in deals],
        "risk_signals": risk_signals,
        # 키 이름은 그대로 둔다 — 이 스냅샷은 그대로 LLM 입력 JSON 이 되므로
        # (contract_management._NextMeetingLLMInput) 바꾸려면 프롬프트 버전을
        # 올려야 한다. 함수 이름만 실제 동작(submitted + approved)에 맞춘다.
        "recent_approved_reports": await _recent_finalized_reports(db, member, deal_ids),
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

    now = datetime.now(UTC)
    if preferred_starts_at is not None and preferred_ends_at is not None:
        # 상위 제안(계약관리 1차 실행)이 이미 지난 날짜를 줬을 수 있다 — LLM이 현재
        # 시각을 잘못 가늠했을 때의 방어선이다. preferred_starts_at/ends_at은 LLM 출력이나
        # 클라이언트 요청값을 그대로 받은 문자열이라 형식이 깨졌거나(파싱 실패) offset이
        # 없을(naive) 수 있다 — 둘 다 방어한다.
        parsed_start = _parse_aware_or_none(preferred_starts_at)
        parsed_end = _parse_aware_or_none(preferred_ends_at)
        # 시작이 끝보다 늦으면(LLM 이 날짜를 거꾸로 답한 경우) 탐색 범위가 성립하지 않아
        # 활동 조회도 일정 에이전트 입력도 무의미해진다 — 아래 기본 범위로 넘긴다.
        inverted = (
            parsed_start is not None
            and parsed_end is not None
            and max(parsed_start, now) >= parsed_end
        )
        if parsed_start is None or parsed_end is None or parsed_end <= now or inverted:
            preferred_starts_at = None
            preferred_ends_at = None
        else:
            # 파싱해서 시간대를 붙인 값을 되돌려 담는다. 아래에서 원본 문자열을 다시
            # 파싱하는데 datetime.fromisoformat 은 naive 를 naive 그대로 통과시켜,
            # offset 없는 입력이 여기서는 UTC, contract_management 에서는 Asia/Seoul 로
            # 갈린다 — 같은 글자가 9시간 다르게 읽힌다.
            # max 는 "시작이 이미 지났으면 지금으로 당긴다"를 분기 없이 처리한다.
            preferred_starts_at = max(parsed_start, now).isoformat()
            preferred_ends_at = parsed_end.isoformat()

    if preferred_starts_at is None or preferred_ends_at is None:
        # 계약관리 제안에 구체적인 선호 시간대가 없으면(예: 근거만 있고 날짜 미정),
        # 오늘부터 일주일을 기본 탐색 범위로 둔다.
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
