from datetime import date

from app.schemas.contract_briefing import (
    ApprovedMeetingInsight,
    ContractRiskAssessment,
    NextMeetingCandidate,
    RiskItem,
)
from app.services.contract_schedule_handoff import build_next_meeting_suggestion

TODAY = date(2026, 8, 17)

_EXPIRY_RISK = RiskItem(
    kind="expiry",
    severity="high",
    message="계약 만료까지 15일 남았습니다.",
    evidence={"days_left": 15},
)


def _assessment(*, risks=None, is_needed, candidate_date=None, triggered_by=None):
    return ContractRiskAssessment(
        risks=risks or [],
        next_meeting=NextMeetingCandidate(
            is_needed=is_needed,
            candidate_date=candidate_date,
            triggered_by=triggered_by or [],
        ),
    )


def test_no_suggestion_when_meeting_not_needed():
    assessment = _assessment(is_needed=False)
    assert build_next_meeting_suggestion(assessment, None) is None


def test_suggestion_carries_candidate_date():
    assessment = _assessment(is_needed=True, candidate_date=TODAY, triggered_by=["expiry"])
    suggestion = build_next_meeting_suggestion(assessment, None)
    assert suggestion.is_needed is True
    assert suggestion.suggested_date == TODAY


def test_reason_mentions_expiry_trigger():
    assessment = _assessment(
        risks=[_EXPIRY_RISK], is_needed=True, candidate_date=TODAY, triggered_by=["expiry"]
    )
    suggestion = build_next_meeting_suggestion(assessment, None)
    assert "만료" in suggestion.reason


def test_reason_combines_multiple_triggers_without_duplicates():
    assessment = _assessment(
        is_needed=True,
        candidate_date=TODAY,
        triggered_by=["expiry", "expiry", "contact_interval_elapsed"],
    )
    suggestion = build_next_meeting_suggestion(assessment, None)
    assert suggestion.reason.count("만료가 임박해 다음 미팅이 필요합니다") == 1
    assert "권장 접촉 주기가 지나" in suggestion.reason


def test_no_touch_history_reason():
    assessment = _assessment(
        is_needed=True, candidate_date=TODAY, triggered_by=["no_touch_history"]
    )
    suggestion = build_next_meeting_suggestion(assessment, None)
    assert "접촉 이력이 없어" in suggestion.reason


def test_agenda_from_approved_meeting_insight():
    insight = ApprovedMeetingInsight(next_meeting_agenda=["가격 재협상", "납기 확인"])
    assessment = _assessment(is_needed=True, candidate_date=TODAY, triggered_by=["expiry"])
    suggestion = build_next_meeting_suggestion(assessment, insight)
    assert suggestion.agenda == ["가격 재협상", "납기 확인"]


def test_agenda_is_none_without_insight():
    assessment = _assessment(is_needed=True, candidate_date=TODAY, triggered_by=["expiry"])
    suggestion = build_next_meeting_suggestion(assessment, None)
    assert suggestion.agenda is None
