"""계약관리 Agent가 일정관리 Agent로 넘길 "다음 미팅 제안"을 만드는 자리.

일정관리 Agent와의 실제 연결 방식(텍스트 제안 vs activity 초안)은 아직
합의되지 않았다(ADR 6절). 그래서 이 함수는 결정적 위험 판정 결과만 갖고
형식 중립적인 제안을 만들며, 어떤 통신 수단으로도 아직 내보내지 않는다.
"""

from app.schemas.contract_briefing import (
    ApprovedMeetingInsight,
    ContractRiskAssessment,
    NextMeetingSuggestion,
)

_REASON_BY_TRIGGER = {
    "expiry": "계약 만료가 임박해 다음 미팅이 필요합니다.",
    "delivery": "납품 일정 확인이 필요해 다음 미팅을 권장합니다.",
    "stale_contact": "장기간 접촉이 없어 다음 미팅이 필요합니다.",
    "contact_interval_elapsed": "권장 접촉 주기가 지나 다음 미팅을 제안합니다.",
    "no_touch_history": "접촉 이력이 없어 첫 미팅이 필요합니다.",
}


def build_next_meeting_suggestion(
    risk_assessment: ContractRiskAssessment,
    approved_meeting_insight: ApprovedMeetingInsight | None,
) -> NextMeetingSuggestion | None:
    next_meeting = risk_assessment.next_meeting
    if not next_meeting.is_needed:
        return None

    return NextMeetingSuggestion(
        is_needed=True,
        suggested_date=next_meeting.candidate_date,
        reason=_build_reason(next_meeting.triggered_by),
        agenda=approved_meeting_insight.next_meeting_agenda if approved_meeting_insight else None,
    )


def _build_reason(triggered_by: list[str]) -> str:
    reasons = dict.fromkeys(
        _REASON_BY_TRIGGER[trigger] for trigger in triggered_by if trigger in _REASON_BY_TRIGGER
    )
    return " ".join(reasons) if reasons else "다음 미팅을 권장합니다."
