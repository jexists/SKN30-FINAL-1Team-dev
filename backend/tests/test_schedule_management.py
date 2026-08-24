from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents import schedule_management
from app.schemas.agent_runs import AgentRunCreate


@pytest.mark.anyio
async def test_run_uses_structured_llm_boundary(monkeypatch):
    captured = {}
    expected = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            schedule_management.ScheduleCandidate(
                candidate_id="candidate-1",
                title="계약 협의",
                activity_type="meeting",
                starts_at="2026-08-25T14:00:00+09:00",
                ends_at="2026-08-25T15:00:00+09:00",
                priority=1,
            )
        ]
    )

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(schedule_management, "generate_structured", fake_generate_structured)
    result = await schedule_management.run({"sales_deal": {"id": "deal-1"}})

    # run() 은 결과를 _postprocess 로 재검증하므로 같은 객체가 아니라 같은 내용을 확인한다.
    assert result.schedule_candidates == expected.schedule_candidates
    assert result.conflicts == expected.conflicts
    assert captured["schema"] is schedule_management.ScheduleManagementOutput
    assert captured["schema_name"] == "schedule_management"
    assert "deal-1" in captured["input_text"]


def test_schedule_request_requires_offset_and_valid_range():
    common = {
        "agent_code": "schedule_management",
        "idempotency_key": uuid4(),
        "sales_deal_id": uuid4(),
        "owner_member_id": uuid4(),
        "duration_minutes": 60,
        "activity_type": "meeting",
    }
    with pytest.raises(ValidationError, match="timezone_offset_required"):
        AgentRunCreate(
            **common,
            preferred_starts_at=datetime(2026, 8, 25, 14),
            preferred_ends_at=datetime(2026, 8, 25, 15),
        )


def test_contract_request_requires_company_and_rejects_report_input():
    with pytest.raises(ValidationError, match="customer_company_id_required"):
        AgentRunCreate(agent_code="contract_management", idempotency_key=uuid4())
    with pytest.raises(ValidationError, match="agent_input_not_supported"):
        AgentRunCreate(
            agent_code="contract_management",
            idempotency_key=uuid4(),
            customer_company_id=uuid4(),
            report_id=uuid4(),
        )


def _candidate(
    candidate_id: str, starts_at: str, ends_at: str
) -> schedule_management.ScheduleCandidate:
    return schedule_management.ScheduleCandidate(
        candidate_id=candidate_id,
        title="다음 계약 협의",
        activity_type="meeting",
        starts_at=starts_at,
        ends_at=ends_at,
        priority=1,
    )


def _activity_dict(*, starts_at: str, ends_at: str, all_day: bool = False) -> dict:
    return {
        "id": "activity-1",
        "owner_member_id": "member-1",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "all_day": all_day,
        "updated_at": starts_at,
    }


def test_within_business_hours_accepts_and_rejects():
    within = _candidate("c1", "2026-08-25T09:00:00+09:00", "2026-08-25T10:00:00+09:00")
    too_early = _candidate("c2", "2026-08-25T08:30:00+09:00", "2026-08-25T09:30:00+09:00")
    too_late = _candidate("c3", "2026-08-25T17:30:00+09:00", "2026-08-25T18:30:00+09:00")

    assert schedule_management._within_business_hours(within) is True
    assert schedule_management._within_business_hours(too_early) is False
    assert schedule_management._within_business_hours(too_late) is False


def test_conflicts_for_boundary_touch_is_not_a_conflict():
    candidate = _candidate("c1", "2026-08-25T10:00:00+09:00", "2026-08-25T11:00:00+09:00")
    activities = [
        _activity_dict(starts_at="2026-08-25T09:00:00+09:00", ends_at="2026-08-25T10:00:00+09:00")
    ]

    assert schedule_management._conflicts_for(candidate, activities) == []


def test_conflicts_for_detects_time_overlap():
    candidate = _candidate("c1", "2026-08-25T10:00:00+09:00", "2026-08-25T11:00:00+09:00")
    activities = [
        _activity_dict(starts_at="2026-08-25T10:30:00+09:00", ends_at="2026-08-25T11:30:00+09:00")
    ]

    conflicts = schedule_management._conflicts_for(candidate, activities)

    assert len(conflicts) == 1
    assert conflicts[0].reason == "time_overlap"
    assert conflicts[0].activity_id == "activity-1"


def test_conflicts_for_detects_all_day_overlap():
    candidate = _candidate("c1", "2026-08-25T09:00:00+09:00", "2026-08-25T10:00:00+09:00")
    activities = [
        _activity_dict(
            starts_at="2026-08-25T00:00:00+09:00",
            ends_at="2026-08-25T00:00:00+09:00",
            all_day=True,
        )
    ]

    conflicts = schedule_management._conflicts_for(candidate, activities)

    assert len(conflicts) == 1
    assert conflicts[0].reason == "all_day_overlap"


@pytest.mark.anyio
async def test_run_excludes_conflicting_and_out_of_hours_candidates(monkeypatch):
    kept = _candidate("kept", "2026-08-25T10:00:00+09:00", "2026-08-25T11:00:00+09:00")
    conflicting = _candidate("conflict", "2026-08-25T13:00:00+09:00", "2026-08-25T14:00:00+09:00")
    out_of_hours = _candidate("late", "2026-08-25T19:00:00+09:00", "2026-08-25T20:00:00+09:00")
    raw_output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[kept, conflicting, out_of_hours],
    )

    async def fake_generate_structured(**kwargs):
        return raw_output

    monkeypatch.setattr(schedule_management, "generate_structured", fake_generate_structured)

    snapshot = {
        "activities": [
            _activity_dict(
                starts_at="2026-08-25T13:30:00+09:00", ends_at="2026-08-25T14:30:00+09:00"
            ),
        ]
    }

    result = await schedule_management.run(snapshot)

    assert [candidate.candidate_id for candidate in result.schedule_candidates] == ["kept"]
    assert any(conflict.activity_id == "activity-1" for conflict in result.conflicts)
