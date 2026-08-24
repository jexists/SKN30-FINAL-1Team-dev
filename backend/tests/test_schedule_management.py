import json

import pytest
from pydantic import ValidationError

from app.agents import schedule_management


def _candidate(
    *,
    candidate_id: str = "candidate-1",
    starts_at: str = "2026-08-25T09:00:00+09:00",
    ends_at: str = "2026-08-25T10:00:00+09:00",
):
    return schedule_management.ScheduleCandidate(
        candidate_id=candidate_id,
        title="계약 조건 협의",
        activity_type="meeting",
        starts_at=starts_at,
        ends_at=ends_at,
        priority=1,
    )


def test_candidate_contract_rejects_invalid_activity_type_and_priority():
    with pytest.raises(ValidationError):
        schedule_management.ScheduleCandidate(
            candidate_id="candidate-1",
            title="계약 조건 협의",
            activity_type="call",
            starts_at="2026-08-25T09:00:00+09:00",
            ends_at="2026-08-25T10:00:00+09:00",
            priority=1,
        )

    with pytest.raises(ValidationError):
        schedule_management.ScheduleCandidate(
            candidate_id="candidate-1",
            title="계약 조건 협의",
            activity_type="meeting",
            starts_at="2026-08-25T09:00:00+09:00",
            ends_at="2026-08-25T10:00:00+09:00",
            priority=0,
        )


@pytest.mark.parametrize(
    ("starts_at", "ends_at", "expected"),
    [
        ("2026-08-25T09:00:00+09:00", "2026-08-25T18:00:00+09:00", True),
        ("2026-08-25T08:59:00+09:00", "2026-08-25T10:00:00+09:00", False),
        ("2026-08-25T17:30:00+09:00", "2026-08-25T18:01:00+09:00", False),
        ("2026-08-25T10:00:00+09:00", "2026-08-25T10:00:00+09:00", False),
        ("not-a-date", "2026-08-25T10:00:00+09:00", False),
    ],
)
def test_candidate_must_be_valid_and_within_business_hours(starts_at, ends_at, expected):
    assert (
        schedule_management._within_business_hours(
            _candidate(starts_at=starts_at, ends_at=ends_at)
        )
        is expected
    )


def test_conflict_uses_half_open_ranges_and_all_day_activities():
    activities = [
        {
            "id": "touching",
            "owner_member_id": "member-1",
            "starts_at": "2026-08-25T10:00:00+09:00",
            "ends_at": "2026-08-25T11:00:00+09:00",
            "all_day": False,
        },
        {
            "id": "all-day",
            "owner_member_id": "member-2",
            "starts_at": "2026-08-26T00:00:00+09:00",
            "ends_at": None,
            "all_day": True,
        },
    ]

    touching = schedule_management._conflicts_for(_candidate(), activities)
    all_day = schedule_management._conflicts_for(
        _candidate(
            starts_at="2026-08-26T15:00:00+09:00",
            ends_at="2026-08-26T16:00:00+09:00",
        ),
        activities,
    )

    assert touching == []
    assert len(all_day) == 1
    assert all_day[0].activity_id == "all-day"
    assert all_day[0].member_id == "member-2"
    assert all_day[0].reason == "all_day_overlap"


def test_postprocess_removes_out_of_hours_and_conflicting_candidates():
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(candidate_id="kept"),
            _candidate(
                candidate_id="conflicting",
                starts_at="2026-08-25T11:00:00+09:00",
                ends_at="2026-08-25T12:00:00+09:00",
            ),
            _candidate(
                candidate_id="too-late",
                starts_at="2026-08-25T18:00:00+09:00",
                ends_at="2026-08-25T19:00:00+09:00",
            ),
        ]
    )
    snapshot = {
        "activities": [
            {
                "id": "activity-1",
                "owner_member_id": "member-1",
                "starts_at": "2026-08-25T11:30:00+09:00",
                "ends_at": "2026-08-25T12:30:00+09:00",
                "all_day": False,
            }
        ]
    }

    result = schedule_management._postprocess(output, snapshot)

    assert [item.candidate_id for item in result.schedule_candidates] == ["kept"]
    assert [item.activity_id for item in result.conflicts] == ["activity-1"]


@pytest.mark.anyio
async def test_run_uses_schedule_prompt_schema_and_postprocesses(monkeypatch):
    captured = {}
    generated = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                starts_at="2026-08-25T14:00:00+09:00",
                ends_at="2026-08-25T15:00:00+09:00",
            )
        ]
    )

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return generated

    monkeypatch.setattr(schedule_management, "generate_structured", fake_generate_structured)
    snapshot = {
        "sales_deal_id": "deal-1",
        "activities": [
            {
                "id": "activity-1",
                "owner_member_id": "member-1",
                "starts_at": "2026-08-25T14:30:00+09:00",
                "ends_at": "2026-08-25T15:30:00+09:00",
                "all_day": False,
            }
        ],
    }

    result = await schedule_management.run(snapshot)

    assert result.schedule_candidates == []
    assert result.conflicts[0].activity_id == "activity-1"
    assert captured["instructions"] == schedule_management.SYSTEM_PROMPT
    assert captured["schema"] is schedule_management.ScheduleManagementOutput
    assert captured["schema_name"] == "schedule_management"
    assert json.loads(captured["input_text"]) == snapshot
