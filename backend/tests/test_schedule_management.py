import json
from datetime import datetime

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
        starts_at=starts_at,
        ends_at=ends_at,
        priority=1,
    )


def test_candidate_contract_rejects_invalid_priority():
    with pytest.raises(ValidationError):
        schedule_management.ScheduleCandidate(
            candidate_id="candidate-1",
            title="계약 조건 협의",
            starts_at="2026-08-25T09:00:00+09:00",
            ends_at="2026-08-25T10:00:00+09:00",
            priority=0,
        )


@pytest.mark.parametrize(
    ("starts_at", "ends_at", "expected"),
    [
        ("2026-08-25T09:00:00+09:00", "2026-08-25T18:00:00+09:00", True),  # 화요일
        ("2026-08-25T08:59:00+09:00", "2026-08-25T10:00:00+09:00", False),
        ("2026-08-25T17:30:00+09:00", "2026-08-25T18:01:00+09:00", False),
        ("2026-08-25T10:00:00+09:00", "2026-08-25T10:00:00+09:00", False),
        ("not-a-date", "2026-08-25T10:00:00+09:00", False),
        ("2026-08-22T09:00:00+09:00", "2026-08-22T10:00:00+09:00", False),  # 토요일
        ("2026-08-23T09:00:00+09:00", "2026-08-23T10:00:00+09:00", False),  # 일요일
    ],
)
def test_candidate_must_be_valid_and_within_business_hours(starts_at, ends_at, expected):
    assert (
        schedule_management._within_business_hours(_candidate(starts_at=starts_at, ends_at=ends_at))
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


def test_conflicts_for_marks_invalid_time_without_raising():
    """활동 하나의 시각이 깨져 있어도 나머지 활동은 정상적으로 계산돼야 한다."""
    activities = [
        {"id": "missing-starts-at", "owner_member_id": "member-1"},
        {
            "id": "bad-format",
            "owner_member_id": "member-1",
            "starts_at": "not-a-date",
            "ends_at": "2026-08-25T10:00:00+09:00",
        },
        {
            "id": "valid-overlap",
            "owner_member_id": "member-2",
            "starts_at": "2026-08-25T09:30:00+09:00",
            "ends_at": "2026-08-25T10:00:00+09:00",
            "all_day": False,
        },
    ]

    conflicts = schedule_management._conflicts_for(_candidate(), activities)

    by_id = {conflict.activity_id: conflict for conflict in conflicts}
    assert by_id["missing-starts-at"].reason == "invalid_time"
    assert by_id["bad-format"].reason == "invalid_time"
    assert by_id["valid-overlap"].reason == "time_overlap"


def test_postprocess_removes_out_of_hours_and_conflicting_candidates(monkeypatch):
    monkeypatch.setattr(
        schedule_management,
        "_now",
        lambda: datetime(2026, 8, 25, 0, 0, tzinfo=schedule_management._SEOUL),
    )
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


def test_postprocess_drops_candidates_already_in_the_past(monkeypatch):
    """프롬프트로 지침을 줘도 LLM이 과거 날짜를 제안할 수 있다 — 여기서 결정적으로 막는다."""
    monkeypatch.setattr(
        schedule_management,
        "_now",
        lambda: datetime(2026, 8, 25, 12, 0, tzinfo=schedule_management._SEOUL),
    )
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id="past",
                starts_at="2026-08-25T09:00:00+09:00",
                ends_at="2026-08-25T10:00:00+09:00",
            ),
            _candidate(
                candidate_id="future",
                starts_at="2026-08-25T14:00:00+09:00",
                ends_at="2026-08-25T15:00:00+09:00",
            ),
        ]
    )

    result = schedule_management._postprocess(output, snapshot={"activities": []})

    assert [item.candidate_id for item in result.schedule_candidates] == ["future"]


@pytest.mark.anyio
async def test_run_uses_schedule_prompt_schema_and_postprocesses(monkeypatch):
    fixed_now = datetime(2026, 8, 25, 8, 0, tzinfo=schedule_management._SEOUL)
    monkeypatch.setattr(schedule_management, "_now", lambda: fixed_now)
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
    sent = json.loads(captured["input_text"])
    assert sent == {
        "sales_deal_id": "deal-1",
        "preferred_starts_at": None,
        "preferred_ends_at": None,
        "duration_minutes": None,
        "reason": None,
        "activities": [
            {
                "id": "activity-1",
                "starts_at": "2026-08-25T14:30:00+09:00",
                "ends_at": "2026-08-25T15:30:00+09:00",
                "all_day": False,
            }
        ],
        "current_date": fixed_now.isoformat(),
    }
    # 담당자(개인정보)는 로컬 충돌 계산에만 쓰고 LLM 프롬프트에는 보내지 않는다.
    assert "owner_member_id" not in captured["input_text"]
    assert "member-1" not in captured["input_text"]


@pytest.mark.anyio
async def test_run_skips_malformed_activity_when_building_llm_input(monkeypatch):
    captured = {}
    generated = schedule_management.ScheduleManagementOutput(schedule_candidates=[])

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return generated

    monkeypatch.setattr(schedule_management, "generate_structured", fake_generate_structured)
    snapshot = {
        "sales_deal_id": "deal-1",
        "activities": [
            {"id": "broken"},  # starts_at 없음
            {
                "id": "ok",
                "owner_member_id": "member-1",
                "starts_at": "2026-08-25T09:00:00+09:00",
                "ends_at": "2026-08-25T10:00:00+09:00",
                "all_day": False,
            },
        ],
    }

    result = await schedule_management.run(snapshot)

    sent_activities = json.loads(captured["input_text"])["activities"]
    assert [activity["id"] for activity in sent_activities] == ["ok"]
    # LLM 호출 자체가 깨진 활동 때문에 실패하지 않는다.
    assert result.schedule_candidates == []
