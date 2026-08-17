"""계약 위험 신호와 다음 미팅 필요 여부를 계산하는 결정적 로직.

DB 세션을 모르는 순수 함수다. 조회는 API 레이어가 맡고, 이미 팀·권한 스코프를
통과한 SalesDealRead와 같은 고객사 최근 활동 시각 목록만 받는다.

임계값(D-30/60/90, 납품 D-7, 미접촉 14일)은 학습된 값이 아니라 초기 추정치이며,
데모 피드백과 실사용 데이터를 근거로 조정한다.

계약(Contract) 도메인은 딜·파이프라인 통합(PR #32)으로 SalesDeal로 리네임됐다.
여기서 쓰는 `contract_ends_on`, `sales_pipeline_stage_outcome_code`,
`sales_pipeline_stage_position`은 그 이후 스키마의 필드명이다.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from app.schemas.contract_briefing import ContractRiskAssessment, NextMeetingCandidate, RiskItem
from app.schemas.sales_deals import SalesDealRead

_EXPIRY_WARNING_DAYS = 90
_DELIVERY_WARNING_DAYS = 7
_STALE_CONTACT_DAYS = 14
_STALE_CONTACT_HIGH_DAYS = 30
_DELIVERED_STAGE_POSITION = 6


def evaluate_contract_risks(
    deal: SalesDealRead,
    recent_company_activity_at: Sequence[datetime],
    today: date,
) -> ContractRiskAssessment:
    if deal.sales_pipeline_stage_outcome_code == "cancelled":
        return ContractRiskAssessment(
            risks=[],
            next_meeting=NextMeetingCandidate(
                is_needed=False, candidate_date=None, triggered_by=[]
            ),
        )

    risks: list[RiskItem] = []

    expiry_risk = _evaluate_expiry(deal, today)
    if expiry_risk is not None:
        risks.append(expiry_risk)

    delivery_risk = _evaluate_delivery(deal, today)
    if delivery_risk is not None:
        risks.append(delivery_risk)

    last_contact_at = max(recent_company_activity_at, default=None)
    stale_contact_risk, days_since_contact = _evaluate_stale_contact(last_contact_at, today)
    if stale_contact_risk is not None:
        risks.append(stale_contact_risk)

    next_meeting = _next_meeting_candidate(deal, risks, days_since_contact, today)
    return ContractRiskAssessment(risks=risks, next_meeting=next_meeting)


def _evaluate_expiry(deal: SalesDealRead, today: date) -> RiskItem | None:
    if deal.contract_ends_on is None:
        return None
    days_left = (deal.contract_ends_on - today).days
    if days_left < 0 or days_left > _EXPIRY_WARNING_DAYS:
        return None
    severity = "high" if days_left <= 30 else "medium" if days_left <= 60 else "low"
    return RiskItem(
        kind="expiry",
        severity=severity,
        message=f"계약 만료(갱신 판단 기준일)까지 {days_left}일 남았습니다.",
        evidence={"contract_ends_on": deal.contract_ends_on.isoformat(), "days_left": days_left},
    )


def _evaluate_delivery(deal: SalesDealRead, today: date) -> RiskItem | None:
    if deal.expected_delivery_at is None:
        return None
    if deal.sales_pipeline_stage_position >= _DELIVERED_STAGE_POSITION:
        return None
    days_left = (deal.expected_delivery_at.date() - today).days
    if days_left < 0:
        return RiskItem(
            kind="delivery",
            severity="high",
            message=f"납품 예정일이 {abs(days_left)}일 지났습니다.",
            evidence={
                "expected_delivery_at": deal.expected_delivery_at.isoformat(),
                "days_overdue": abs(days_left),
            },
        )
    if days_left <= _DELIVERY_WARNING_DAYS:
        return RiskItem(
            kind="delivery",
            severity="medium",
            message=f"납품 예정일이 {days_left}일 남았습니다.",
            evidence={
                "expected_delivery_at": deal.expected_delivery_at.isoformat(),
                "days_left": days_left,
            },
        )
    return None


def _evaluate_stale_contact(
    last_contact_at: datetime | None, today: date
) -> tuple[RiskItem | None, int | None]:
    if last_contact_at is None:
        return None, None
    days_since_contact = (today - last_contact_at.date()).days
    if days_since_contact < _STALE_CONTACT_DAYS:
        return None, days_since_contact
    severity = "high" if days_since_contact >= _STALE_CONTACT_HIGH_DAYS else "medium"
    risk = RiskItem(
        kind="stale_contact",
        severity=severity,
        message=(
            f"같은 고객사와 마지막 접촉 후 {days_since_contact}일이 지났습니다"
            "(같은 고객사 최근 일정 기준 근사치)."
        ),
        evidence={
            "last_contact_at": last_contact_at.isoformat(),
            "days_since_contact": days_since_contact,
        },
    )
    return risk, days_since_contact


def _recommended_interval_days(deal: SalesDealRead) -> int:
    if deal.sales_pipeline_stage_outcome_code == "confirmed":
        return 30
    if deal.sales_pipeline_stage_position <= 1:
        return 7
    return 5


def _next_meeting_candidate(
    deal: SalesDealRead,
    risks: list[RiskItem],
    days_since_contact: int | None,
    today: date,
) -> NextMeetingCandidate:
    interval = _recommended_interval_days(deal)
    triggered_by = [risk.kind for risk in risks]

    if days_since_contact is None:
        triggered_by.append("no_touch_history")
        return NextMeetingCandidate(is_needed=True, candidate_date=today, triggered_by=triggered_by)

    overdue = days_since_contact >= interval
    if overdue:
        triggered_by.append("contact_interval_elapsed")

    candidate_date = today + timedelta(days=max(interval - days_since_contact, 0))
    return NextMeetingCandidate(
        is_needed=bool(risks) or overdue,
        candidate_date=candidate_date,
        triggered_by=triggered_by,
    )
