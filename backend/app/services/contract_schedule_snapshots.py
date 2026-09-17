"""계약관리·일정관리 에이전트 입력을 DB에서 조립한다.

계약에이전트_설계.md / 일정관리에이전트_설계.md 의 위험 판정·후속 미팅·일정 조율 입력을
실제 팀 데이터로 채운다. 임계값(만료 임박 기준일 등)은 기획에서 확정된 값이 아니라 이
모듈에서 정한 초기값이다 — 운영하면서 조정한다.
"""

import json
from collections import Counter
from datetime import UTC, date, datetime
from statistics import median
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.content import Document, Report, ReportDeal
from app.models.crm import (
    Activity,
    CustomerCompany,
    CustomerContact,
    SupportRequest,
    SupportResponse,
)
from app.models.sales import Product, SalesDeal, SalesPipelineStage
from app.models.workspace import Member
from app.services import (
    activity_documents,
    contract_document_comparison,
    report_context,
    sales_context,
)
from app.services.embeddings import EmbeddingError
from app.services.report_sources import _body_values, _shared_body
from app.services.storage import StorageError

_SEOUL = ZoneInfo("Asia/Seoul")

_CONTRACT_EXPIRING_WITHIN_DAYS = 30
_QUOTE_EXPIRING_WITHIN_DAYS = 14
_FOLLOW_UP_OVERDUE_AFTER_DAYS = 30
_CONTRACT_REVISIT_DUE_AFTER_DAYS = 7
_CONTRACT_REVISIT_URGENT_AFTER_DAYS = 14
# 자료실 검색 API 의 q 상한과 맞춘다.
_BRIEFING_QUERY_MAX_CHARS = 500
# C/S 상태는 received·diagnosing·in_progress·completed 네 가지고(app/schemas/support.py),
# 끝난 것은 completed 뿐이다. in_progress 만 보면 접수·원인파악 단계의 미해결 요청이
# 위험 신호에서 통째로 빠진다.
_OPEN_SUPPORT_STATUSES = ("received", "diagnosing", "in_progress")
# 브리핑이 도구로 읽는 C/S 수. 미해결 건은 미팅에서 먼저 나올 쟁점이라 넉넉히 두고,
# 처리완료 건은 재발 여부를 볼 만큼만 둔다. 대응 기록은 건마다 최근 것만 읽는다.
_BRIEFING_OPEN_SUPPORT_LIMIT = 20
_BRIEFING_COMPLETED_SUPPORT_LIMIT = 3
_BRIEFING_SUPPORT_RESPONSE_LIMIT = 3
# 청크 하나가 최대 1,600자라 5건이면 문맥 블록 상한(12,000자) 안에 든다.
_BRIEFING_DOCUMENT_LIMIT = 5
# 다음 일정 추천 도구가 볼 최근 미팅 수. 주기·요일 패턴을 보기에 충분한 만큼만 읽는다.
_MEETING_HISTORY_LIMIT = 30
_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def _seoul_iso(value: datetime | None) -> str | None:
    """LLM 에 보낼 시각. 화면과 같은 서울 시간으로 맞춘다."""
    return None if value is None else value.astimezone(_SEOUL).isoformat()


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
    db: AsyncSession,
    member: Member,
    customer_company_id: UUID,
    *,
    limit: int | None = None,
) -> list[tuple[SalesDeal, SalesPipelineStage]]:
    """이 회사에서 아직 끝나지 않은 딜을 단계 정보와 함께 가져온다."""
    statement = (
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
        .order_by(SalesDeal.created_at.desc(), SalesDeal.id)
    )
    if limit is not None:
        statement = statement.limit(limit)
    result = await db.execute(statement)
    return list(result.all())


async def _company_deals(
    db: AsyncSession, member: Member, customer_company_id: UUID
) -> list[tuple[SalesDeal, SalesPipelineStage]]:
    """브리핑 배경에 쓸 고객사의 현재·종료 딜 전체. 삭제된 딜만 제외한다."""
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
        )
        .order_by(SalesDeal.created_at.desc(), SalesDeal.id)
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
    """이 회사에 걸린, 아직 끝나지 않은 C/S 요청."""
    result = await db.execute(
        select(SupportRequest).where(
            SupportRequest.deleted_at.is_(None),
            SupportRequest.team_id == member.team_id,
            SupportRequest.customer_company_id == customer_company_id,
            SupportRequest.status_code.in_(_OPEN_SUPPORT_STATUSES),
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
        "contract_amount": deal.contract_amount,
        "contract_ends_on": deal.contract_ends_on.isoformat() if deal.contract_ends_on else None,
        "contract_payment_terms": deal.contract_payment_terms,
        "quote_valid_until": (
            deal.quote_valid_until.isoformat() if deal.quote_valid_until else None
        ),
        "expected_delivery_at": (
            deal.expected_delivery_at.isoformat() if deal.expected_delivery_at else None
        ),
    }


async def _recent_finalized_reports(
    db: AsyncSession,
    member: Member,
    deal_ids: list[UUID],
    required_report_id: UUID | None = None,
    limit: int = 5,
    customer_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """작성자가 확정한(submitted) 보고서까지 근거로 쓴다.

    approved 는 팀장 검토까지 끝난 상태인데 그 검토 화면이 아직 없어, approved 만 보면
    방금 확정한 보고서가 영영 입력에 들어오지 못한다. 보고서 확정이 곧 이 파이프라인의
    트리거이기도 하므로(계약에이전트_설계.md 3장) 두 상태를 함께 본다. 확정 트리거가
    지정한 보고서는 5건 제한에 밀리지 않도록 맨 앞에 두며, 찾지 못하면 실행을 중단한다.
    """
    if not deal_ids and customer_company_id is None:
        return []
    priority = [] if required_report_id is None else [(Report.id == required_report_id).desc()]
    matching_deal = ReportDeal.sales_deal_id.in_(deal_ids)
    report_scope = [matching_deal]
    if customer_company_id is not None:
        report_scope.append(
            and_(
                Report.customer_company_id == customer_company_id,
                or_(Report.common_body.is_not(None), Report.unassigned_body.is_not(None)),
            )
        )
    recent_report_ids = (
        select(Report.id)
        .outerjoin(
            ReportDeal,
            and_(ReportDeal.report_id == Report.id, matching_deal),
        )
        .where(
            Report.team_id == member.team_id,
            Report.status_code.in_(("approved", "submitted")),
            or_(*report_scope),
        )
    )
    recent_report_ids = (
        recent_report_ids.group_by(Report.id)
        .order_by(*priority, Report.report_date.desc(), Report.id)
        .limit(limit)
        .subquery()
    )
    result = await db.execute(
        select(Report, ReportDeal)
        .join(recent_report_ids, recent_report_ids.c.id == Report.id)
        .outerjoin(
            ReportDeal,
            and_(ReportDeal.report_id == Report.id, matching_deal),
        )
        .order_by(*priority, Report.report_date.desc(), Report.id, ReportDeal.sales_deal_id)
    )
    rows = result.all()
    if required_report_id is not None and not any(
        report.id == required_report_id for report, _section in rows
    ):
        raise HTTPException(404, "report_source_not_found")
    output = []
    shared_by_activity = {}
    for report, section in rows:
        content = {"values": _body_values(getattr(section, "body", None))}
        title = getattr(section, "title", None)
        if isinstance(title, str):
            content["title"] = title
        common_body = getattr(report, "common_body", None)
        unassigned_body = getattr(report, "unassigned_body", None)
        if common_body is not None or unassigned_body is not None:
            if report.source_activity_id is None:
                raise HTTPException(422, "report_source_shared_invalid")
            content["meeting_shared"] = {
                "common_report": _shared_body(common_body),
                "unassigned_report": _shared_body(unassigned_body),
            }
            previous = shared_by_activity.get(report.source_activity_id)
            if previous is not None and previous != content["meeting_shared"]:
                raise HTTPException(409, "report_source_shared_conflict")
            shared_by_activity[report.source_activity_id] = content["meeting_shared"]
        output.append(
            {
                "id": str(report.id),
                "sales_deal_id": str(section.sales_deal_id) if section is not None else None,
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
    required_report_id: UUID | None = None,
    excluded_dates: list[date] | None = None,
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
        "recent_approved_reports": await _recent_finalized_reports(
            db,
            member,
            deal_ids,
            required_report_id,
            customer_company_id=customer_company_id if sales_deal_id is None else None,
        ),
        "current_datetime": datetime.now(_SEOUL).isoformat(),
        "excluded_dates": excluded_dates or [],
        # 아래 값은 LLM 입력 JSON이 아니라 계약관리 에이전트 도구가 읽는다.
        "_meeting_history": await _meeting_history(db, member, customer_company_id),
        "_report_scope": {
            "team_id": str(member.team_id),
            "customer_company_id": str(customer_company_id),
        },
        "_scope_sales_deal_id": str(sales_deal_id) if sales_deal_id is not None else None,
    }


async def _meeting_history(
    db: AsyncSession, member: Member, customer_company_id: UUID
) -> dict[str, Any]:
    """다음 일정 추천 도구가 볼 고객사 미팅 이력. 날짜 계산은 LLM 대신 여기서 끝낸다."""
    conditions = [
        Activity.team_id == member.team_id,
        Activity.customer_company_id == customer_company_id,
        Activity.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(Activity.owner_member_id == member.id)
    rows = (
        await db.execute(
            select(Activity.starts_at, Activity.all_day)
            .where(*conditions)
            .order_by(Activity.starts_at.desc())
            .limit(_MEETING_HISTORY_LIMIT)
        )
    ).all()
    now = datetime.now(_SEOUL)

    def item(starts_at: datetime, all_day: bool) -> dict[str, Any]:
        local = starts_at.astimezone(_SEOUL)
        return {
            "date": local.date().isoformat(),
            "weekday": _WEEKDAYS[local.weekday()],
            "time": None if all_day else local.strftime("%H:%M"),
        }

    ordered = list(reversed(rows))
    past = [item(starts_at, all_day) for starts_at, all_day in ordered if starts_at <= now]
    upcoming = [item(starts_at, all_day) for starts_at, all_day in ordered if starts_at > now]
    dates = sorted({date.fromisoformat(meeting["date"]) for meeting in past})
    intervals = [(later - earlier).days for earlier, later in zip(dates, dates[1:], strict=False)]
    return {
        "past_meetings": past[-10:],
        "upcoming_meetings": upcoming[:5],
        "meeting_count": len(dates),
        "interval_days": intervals[-9:],
        "median_interval_days": round(median(intervals)) if intervals else None,
        "weekday_counts": dict(Counter(meeting["weekday"] for meeting in past)),
        "is_first_meeting": len(dates) <= 1,
    }


def _briefing_search_query(
    company: CustomerCompany,
    activity: Activity,
    deals: list[tuple[SalesDeal, SalesPipelineStage]],
    recent_reports: list[dict[str, Any]],
) -> str:
    """자료실을 찾아볼 검색어. LLM 을 한 번 더 부르지 않고 결정적으로 만든다."""
    parts = [
        company.name,
        activity.title,
        activity.note,
        json.dumps(recent_reports, ensure_ascii=False),
        *(deal.title for deal, _stage in deals),
    ]
    # 기존 검색어 순서는 유지하고, 계약서 비교에 필요한 세 필드 검색어가 긴 보고서에
    # 밀려 잘리지 않도록 뒤쪽 자리를 따로 확보한다.
    contract_terms = "계약금액 총계약대금 계약종료일 계약만료일 지급조건 대금지급기일 결제조건"
    available = _BRIEFING_QUERY_MAX_CHARS - len(contract_terms) - 1
    base = " ".join(part for part in parts if part)[:available].rstrip()
    return f"{base} {contract_terms}".strip()


def _merge_briefing_sources(*groups: list[dict[str, object]]) -> list[dict[str, object]]:
    """현재 상태 근거를 앞에 두되, 같은 청크를 두 번 프롬프트에 넣지 않는다."""
    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for group in groups:
        for source in group:
            chunk_id = str(source.get("chunk_id") or "")
            key = chunk_id or f"{source.get('document_id')}:{source.get('chunk_no')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
    return merged


async def _briefing_document_context(
    db: AsyncSession,
    company: CustomerCompany,
    activity: Activity,
    deals: list[tuple[SalesDeal, SalesPipelineStage]],
    recent_reports: list[dict[str, Any]],
    member: Member,
) -> dict[str, Any]:
    """자료요약 Agent 가 저장한 요약·근거를 브리핑 입력 형태로 가져온다.

    조회가 실패해도 브리핑 자체는 만들어야 한다 — 계약에이전트_설계.md 의 "앞 단계
    데이터가 없어도 최소 동작한다" 원칙에 따라 빈 문맥으로 되돌린다.
    """
    query = _briefing_search_query(company, activity, deals, recent_reports)
    products = []
    current_state_sources: list[dict[str, object]] = []
    try:
        # 거래 문서의 최신 상태는 범용 RAG 상위 결과와 경쟁시키지 않는다. 그래야 이전
        # 견적의 "미확정" 문장만 남고 뒤늦은 계약·발주 조건이 빠지는 일을 막는다.
        current_state_sources = await sales_context.retrieve_current_state_sources(
            db,
            team_id=company.team_id,
            customer_company_id=company.id,
            member=member,
        )
        product_ids = await activity_documents.product_ids_for_deals(
            db,
            team_id=company.team_id,
            sales_deal_ids=[deal.id for deal, _stage in deals],
        )
        if recent_reports:
            product_ids.update(
                await activity_documents.mentioned_product_ids(
                    db, team_id=company.team_id, values=recent_reports
                )
            )
        products = await activity_documents.list_documents(
            db,
            team_id=company.team_id,
            scopes=[Document.product_id.in_(product_ids)] if product_ids else [],
            member=member,
        )
        if product_ids:
            names = (
                (
                    await db.execute(
                        select(Product.name).where(
                            Product.id.in_(product_ids), Product.team_id == company.team_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            query = " ".join([query[:350], *names])[:_BRIEFING_QUERY_MAX_CHARS]
        search_info = {}
        context = await sales_context.retrieve_briefing_context(
            db,
            team_id=company.team_id,
            query=query,
            limit=_BRIEFING_DOCUMENT_LIMIT,
            # 자료는 딜에만 붙기도 하고 고객사에만 붙기도 해서 둘 다 넘긴다(OR).
            # 일정은 회사에 연결된다. 딜 자료도 customer_company_id가 딜을 거쳐 찾는다.
            sales_deal_id=None,
            customer_company_id=company.id,
            product_ids=product_ids,
            search_info=search_info,
            member=member,
        )
        return {
            **context,
            # current_state_sources 는 프롬프트가 근거 성격을 구분하는 데 쓰고, sources에도
            # 합쳐 화면·출처 검증이 같은 청크 집합을 보게 한다.
            "current_state_sources": current_state_sources,
            "sources": _merge_briefing_sources(current_state_sources, context["sources"]),
            "product_documents": products,
            "search": search_info,
        }
    except (SQLAlchemyError, EmbeddingError, StorageError):
        # A failed SQL statement must not leave the worker session in an aborted transaction.
        await db.rollback()
        return {
            "query": query,
            "summaries": [],
            "current_state_sources": current_state_sources,
            "sources": current_state_sources,
            "product_documents": products,
            "search": {"method": "none", "status": "failed"},
        }


async def _briefing_support_requests(
    db: AsyncSession, member: Member, customer_company_id: UUID
) -> list[dict[str, Any]]:
    """브리핑이 read_support_requests 도구로 읽을 이 고객사의 C/S.

    미해결 건은 긴급한 것부터, 그다음 최근 처리완료 건 몇 개를 담는다. 팀원은 C/S 화면과
    같은 규칙으로 자기가 맡은 건만 본다(``app.api.support._scope``).
    """
    conditions = [
        SupportRequest.team_id == member.team_id,
        SupportRequest.customer_company_id == customer_company_id,
        SupportRequest.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(SupportRequest.assignee_member_id == member.id)
    requests = (
        (
            await db.execute(
                select(SupportRequest)
                .where(*conditions)
                .order_by(SupportRequest.occurred_at.desc(), SupportRequest.id)
            )
        )
        .scalars()
        .all()
    )
    open_requests = [item for item in requests if item.status_code in _OPEN_SUPPORT_STATUSES]
    # 정렬이 안정적이라 긴급 건 안에서도, 나머지 안에서도 최근 발생 순서가 유지된다.
    open_requests.sort(key=lambda item: not item.is_urgent)
    completed = [item for item in requests if item.status_code not in _OPEN_SUPPORT_STATUSES]
    selected = [
        *open_requests[:_BRIEFING_OPEN_SUPPORT_LIMIT],
        *completed[:_BRIEFING_COMPLETED_SUPPORT_LIMIT],
    ]
    if not selected:
        return []

    responses: dict[UUID, list[dict[str, Any]]] = {}
    rows = (
        (
            await db.execute(
                select(SupportResponse)
                .where(SupportResponse.support_request_id.in_([item.id for item in selected]))
                .order_by(SupportResponse.responded_at.desc(), SupportResponse.id)
            )
        )
        .scalars()
        .all()
    )
    for response in rows:
        items = responses.setdefault(response.support_request_id, [])
        if len(items) < _BRIEFING_SUPPORT_RESPONSE_LIMIT:
            items.append({"responded_at": _seoul_iso(response.responded_at), "body": response.body})

    return [
        {
            "id": str(item.id),
            "sales_deal_id": str(item.sales_deal_id),
            "title": item.title,
            "body": item.body,
            "is_urgent": item.is_urgent,
            "status_code": item.status_code,
            "occurred_at": _seoul_iso(item.occurred_at),
            # 오래된 대응부터 읽히게 되돌린다. 마지막 줄이 가장 최근 대응이다.
            "recent_responses": list(reversed(responses.get(item.id, []))),
        }
        for item in selected
    ]


async def build_briefing_snapshot(
    db: AsyncSession,
    member: Member,
    activity_id: UUID,
) -> dict[str, Any]:
    """확정 미팅에 표시할 브리핑 입력을 일정 ID로 다시 조회한다.

    document_context 는 자료요약 Agent(RAG)의 조회 결과다. 관련 자료가 없거나 조회가
    실패하면 비어 있는 채로 진행한다.
    """
    row = (
        await db.execute(
            select(Activity, CustomerCompany, CustomerContact)
            .join(CustomerCompany, Activity.customer_company_id == CustomerCompany.id)
            .join(CustomerContact, Activity.customer_contact_id == CustomerContact.id)
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
    activity, company, customer_contact = row
    if member.role_code == "member" and activity.owner_member_id != member.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="meeting_activity_not_found"
        )

    customer_company_id = company.id
    company = await _company_or_404(db, member, customer_company_id)
    deals = await _company_deals(db, member, customer_company_id)
    recent_candidates = await report_context.recent_reports(
        db,
        member=member,
        customer_company_id=customer_company_id,
        limit=4,
    )
    recent_reports = recent_candidates[:3]
    has_prior_meeting = (
        await db.execute(
            select(Activity.id)
            .where(
                Activity.team_id == member.team_id,
                Activity.customer_company_id == customer_company_id,
                Activity.deleted_at.is_(None),
                Activity.starts_at < activity.starts_at,
            )
            .limit(1)
        )
    ).scalar_one_or_none() is not None
    support_requests = await _briefing_support_requests(db, member, customer_company_id)

    deal_summaries = [_deal_summary(deal, stage) for deal, stage in deals]
    document_context = await _briefing_document_context(
        db, company, activity, deals, recent_reports, member
    )
    # 비교값은 AI 브리핑 출력이 아니라 관련 자료 표시 데이터에 둔다. 본문 출력 스키마는
    # 그대로 유지하고, RAG로 찾은 계약서 행 아래에서만 계약관리 값과 원문 값을 보여준다.
    document_context["contract_differences"] = contract_document_comparison.build_differences(
        document_context, deal_summaries
    )

    return {
        "customer_company": {"id": str(company.id), "name": company.name},
        "sales_deals": deal_summaries,
        "recent_reports": recent_reports,
        "has_older_reports": len(recent_candidates) > 3,
        # C/S 원문은 LLM 입력 JSON 에 넣지 않고 read_support_requests 도구로만 읽힌다.
        # 입력에는 미해결 건수만 실어 도구 호출이 필요한지 알린다.
        "support_requests": support_requests,
        "open_support_request_count": sum(
            item["status_code"] in _OPEN_SUPPORT_STATUSES for item in support_requests
        ),
        "briefing_mode": "relationship" if has_prior_meeting else "first_meeting",
        "report_search_query": _briefing_search_query(company, activity, deals, recent_reports),
        "_report_scope": {
            "team_id": str(member.team_id),
            "customer_company_id": str(customer_company_id),
        },
        "approved_next_meeting": {
            "activity_id": str(activity.id),
            "title": activity.title,
            # 화면이 서울 시간으로 보여 주는 미팅을 LLM 이 UTC 로 받아 브리핑에 그대로
            # 옮겨 적으면, 같은 미팅의 시각이 화면과 본문에서 아홉 시간 어긋나 보인다.
            "starts_at": _seoul_iso(activity.starts_at),
            "ends_at": _seoul_iso(activity.ends_at),
            "location": activity.location,
            "note": activity.note,
            "customer_contact": {
                "id": str(customer_contact.id),
                "name": customer_contact.name,
                "department": customer_contact.department,
                "job_title": customer_contact.job_title,
            },
        },
        # 구조화된 조회 결과를 그대로 둔다. 이 스냅샷은 agent_run.input_snapshot 으로
        # 저장되므로, 실행 시점에 어떤 근거를 봤는지가 그대로 남는다.
        "document_context": document_context,
    }


async def build_schedule_snapshot(
    db: AsyncSession,
    member: Member,
    sales_deal_id: UUID | None,
    parent_run: AgentRun | None,
    target_date: date | str | None,
    target_time: str | None,
    recommendation_status: str = "pending",
    excluded_dates: list[date] | None = None,
    customer_company_id: UUID | None = None,
) -> dict[str, Any]:
    """일정관리 실행 입력. 날짜를 넓히거나 기본 소요시간을 만들지 않는다."""
    deal = None
    deal_outcome_code = "in_progress"
    if sales_deal_id is not None:
        row = (
            await db.execute(
                select(SalesDeal, SalesPipelineStage.outcome_code)
                .join(
                    SalesPipelineStage,
                    SalesPipelineStage.id == SalesDeal.sales_pipeline_stage_id,
                )
                .where(
                    SalesDeal.id == sales_deal_id,
                    SalesDeal.team_id == member.team_id,
                    SalesDeal.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="sales_deal_not_found"
            )
        deal, deal_outcome_code = row
        customer_company_id = deal.customer_company_id
    elif customer_company_id is not None:
        await _company_or_404(db, member, customer_company_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="schedule_scope_required",
        )

    reason: str | None = None
    if parent_run is not None:
        suggestion = (parent_run.output_snapshot or {}).get("next_meeting_suggestion") or {}
        target_date = suggestion.get("target_date")
        target_time = suggestion.get("target_time")
        reason = suggestion.get("reason")

    if target_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="target_date_required",
        )
    try:
        parsed_target_date = (
            target_date if isinstance(target_date, date) else date.fromisoformat(target_date)
        )
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_target_date"
        ) from None

    return {
        "sales_deal_id": str(deal.id) if deal is not None else None,
        "customer_company_id": str(customer_company_id),
        "target_date": parsed_target_date.isoformat(),
        "target_time": target_time,
        "reason": reason,
        "recommendation_status": recommendation_status,
        "deal_outcome_code": deal_outcome_code,
        "excluded_dates": [value.isoformat() for value in (excluded_dates or [])],
        "current_datetime": datetime.now(_SEOUL).isoformat(),
        "timezone": "Asia/Seoul",
    }
