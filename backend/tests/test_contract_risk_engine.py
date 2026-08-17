from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest

from app.schemas.contracts import ContractRead
from app.services.contract_risk_engine import evaluate_contract_risks

TODAY = date(2026, 8, 17)


def _make_contract(**overrides) -> ContractRead:
    defaults = dict(
        id=uuid4(),
        contract_no="FM-CT-TEST-0001",
        customer_company_id=uuid4(),
        customer_company_name="테스트 병원",
        customer_company_region_code=None,
        contact_id=None,
        contact_name=None,
        owner_member_id=uuid4(),
        owner_display_name="김지훈",
        product_id=None,
        product_name=None,
        stage_id=uuid4(),
        stage_name="계약서 발송",
        stage_tone="orange",
        stage_outcome_code="in_progress",
        stage_position=3,
        title="테스트 계약",
        description=None,
        contract_type="new_installation",
        amount=10_000_000,
        contract_date=date(2026, 1, 1),
        ends_on=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        position=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    defaults.update(overrides)
    return ContractRead(**defaults)


def _delivery_at(days_offset: int) -> datetime:
    return datetime.combine(TODAY + timedelta(days=days_offset), time(9, 0), tzinfo=UTC)


# ---- 만료 임박 (Task 0 픽스처의 6개 구간과 그대로 대응) ----


@pytest.mark.parametrize(
    ("days_offset", "expected_severity"),
    [(15, "high"), (25, "high"), (40, "medium"), (55, "medium"), (65, "low"), (88, "low")],
)
def test_expiry_severity_matches_task0_fixture_tiers(days_offset, expected_severity):
    contract = _make_contract(
        ends_on=TODAY + timedelta(days=days_offset),
        stage_outcome_code="confirmed",
        stage_position=5,
    )
    assessment = evaluate_contract_risks(contract, recent_company_activity_at=[], today=TODAY)
    risk = next(r for r in assessment.risks if r.kind == "expiry")
    assert risk.severity == expected_severity


def test_expiry_beyond_90_days_is_not_flagged():
    contract = _make_contract(
        ends_on=TODAY + timedelta(days=120), stage_outcome_code="confirmed", stage_position=5
    )
    assessment = evaluate_contract_risks(contract, [], TODAY)
    assert assessment.risks == []


def test_no_ends_on_means_no_expiry_risk():
    contract = _make_contract(stage_outcome_code="confirmed", stage_position=5)
    today_contact = datetime.combine(TODAY, time(9), tzinfo=UTC)
    assessment = evaluate_contract_risks(
        contract, recent_company_activity_at=[today_contact], today=TODAY
    )
    assert not any(r.kind == "expiry" for r in assessment.risks)


# ---- 납품 지연·임박 (Task 0 픽스처의 4개 구간과 그대로 대응) ----


@pytest.mark.parametrize(
    ("days_offset", "expected_severity"),
    [(-5, "high"), (-2, "high"), (3, "medium"), (6, "medium")],
)
def test_delivery_severity_matches_task0_fixture_tiers(days_offset, expected_severity):
    contract = _make_contract(
        expected_delivery_at=_delivery_at(days_offset),
        stage_outcome_code="in_progress",
        stage_position=3,
    )
    assessment = evaluate_contract_risks(contract, recent_company_activity_at=[], today=TODAY)
    risk = next(r for r in assessment.risks if r.kind == "delivery")
    assert risk.severity == expected_severity


def test_delivery_risk_skipped_once_delivered():
    contract = _make_contract(
        expected_delivery_at=_delivery_at(-10),
        stage_outcome_code="confirmed",
        stage_position=6,
    )
    assessment = evaluate_contract_risks(contract, [], TODAY)
    assert not any(r.kind == "delivery" for r in assessment.risks)


# ---- 장기 미접촉 ----


def test_stale_contact_medium_between_14_and_29_days():
    last_contact = datetime.combine(TODAY - timedelta(days=20), time(9), tzinfo=UTC)
    contract = _make_contract(stage_outcome_code="confirmed", stage_position=5)
    assessment = evaluate_contract_risks(contract, [last_contact], TODAY)
    risk = next(r for r in assessment.risks if r.kind == "stale_contact")
    assert risk.severity == "medium"


def test_stale_contact_high_at_30_days_or_more():
    last_contact = datetime.combine(TODAY - timedelta(days=40), time(9), tzinfo=UTC)
    contract = _make_contract(stage_outcome_code="confirmed", stage_position=5)
    assessment = evaluate_contract_risks(contract, [last_contact], TODAY)
    risk = next(r for r in assessment.risks if r.kind == "stale_contact")
    assert risk.severity == "high"


def test_recent_contact_has_no_stale_risk():
    last_contact = datetime.combine(TODAY - timedelta(days=3), time(9), tzinfo=UTC)
    contract = _make_contract(stage_outcome_code="confirmed", stage_position=5)
    assessment = evaluate_contract_risks(contract, [last_contact], TODAY)
    assert not any(r.kind == "stale_contact" for r in assessment.risks)


def test_uses_most_recent_of_several_activities():
    older = datetime.combine(TODAY - timedelta(days=40), time(9), tzinfo=UTC)
    newer = datetime.combine(TODAY - timedelta(days=3), time(9), tzinfo=UTC)
    contract = _make_contract(stage_outcome_code="confirmed", stage_position=5)
    assessment = evaluate_contract_risks(contract, [older, newer], TODAY)
    assert not any(r.kind == "stale_contact" for r in assessment.risks)


# ---- 취소 계약은 전부 위험 없음 ----


def test_cancelled_contract_has_no_risks_and_no_next_meeting():
    contract = _make_contract(
        ends_on=TODAY + timedelta(days=10),
        expected_delivery_at=_delivery_at(-5),
        stage_outcome_code="cancelled",
        stage_position=7,
    )
    assessment = evaluate_contract_risks(contract, [], TODAY)
    assert assessment.risks == []
    assert assessment.next_meeting.is_needed is False
    assert assessment.next_meeting.candidate_date is None


# ---- 위험 없는 계약(Task 0에서 값을 채우지 않은 49건과 동일한 케이스) ----


def test_no_risk_data_and_no_recent_contact_still_needs_meeting_for_history():
    contract = _make_contract(stage_outcome_code="in_progress", stage_position=3)
    assessment = evaluate_contract_risks(contract, [], TODAY)
    assert assessment.risks == []
    assert assessment.next_meeting.is_needed is True
    assert assessment.next_meeting.triggered_by == ["no_touch_history"]
    assert assessment.next_meeting.candidate_date == TODAY


def test_no_risk_with_recent_contact_means_no_meeting_needed_yet():
    last_contact = datetime.combine(TODAY - timedelta(days=1), time(9), tzinfo=UTC)
    contract = _make_contract(stage_outcome_code="in_progress", stage_position=3)
    assessment = evaluate_contract_risks(contract, [last_contact], TODAY)
    assert assessment.risks == []
    assert assessment.next_meeting.is_needed is False
    assert assessment.next_meeting.triggered_by == []
    assert assessment.next_meeting.candidate_date == TODAY + timedelta(days=4)


# ---- 다음 미팅 권장 간격이 stage/outcome에 따라 달라지는지 ----


@pytest.mark.parametrize(
    ("stage_outcome_code", "stage_position", "expected_interval"),
    [("in_progress", 0, 7), ("in_progress", 1, 7), ("in_progress", 3, 5), ("confirmed", 5, 30)],
)
def test_recommended_interval_by_stage(stage_outcome_code, stage_position, expected_interval):
    last_contact = datetime.combine(TODAY - timedelta(days=1), time(9), tzinfo=UTC)
    contract = _make_contract(
        stage_outcome_code=stage_outcome_code, stage_position=stage_position
    )
    assessment = evaluate_contract_risks(contract, [last_contact], TODAY)
    assert assessment.next_meeting.candidate_date == TODAY + timedelta(days=expected_interval - 1)


def test_risk_present_forces_next_meeting_even_with_recent_contact():
    last_contact = datetime.combine(TODAY - timedelta(days=1), time(9), tzinfo=UTC)
    contract = _make_contract(
        ends_on=TODAY + timedelta(days=15),
        stage_outcome_code="confirmed",
        stage_position=5,
    )
    assessment = evaluate_contract_risks(contract, [last_contact], TODAY)
    assert assessment.next_meeting.is_needed is True
    assert "expiry" in assessment.next_meeting.triggered_by
