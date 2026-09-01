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
    priority: int = 1,
):
    return schedule_management.ScheduleCandidate(
        candidate_id=candidate_id,
        title="계약 조건 협의",
        starts_at=starts_at,
        ends_at=ends_at,
        priority=priority,
    )


def _freeze(monkeypatch, when: datetime) -> None:
    monkeypatch.setattr(schedule_management, "_now", lambda: when)


# 2026-08-25 는 화요일이다 — 아래 후보들은 모두 평일 업무시간 안에 둔다.
_BEFORE_HOURS = datetime(2026, 8, 25, 8, 0, tzinfo=schedule_management._SEOUL)


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


_BUSY_11_TO_12 = {
    "id": "activity-busy",
    "owner_member_id": "member-1",
    "starts_at": "2026-08-25T11:00:00+09:00",
    "ends_at": "2026-08-25T12:00:00+09:00",
    "all_day": False,
}


def test_postprocess_extends_candidate_to_requested_duration(monkeypatch):
    """자리가 비어 있으면 짧은 후보를 버리지 않고 요청받은 길이로 늘려서 살린다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id="short",
                starts_at="2026-08-25T09:00:00+09:00",
                ends_at="2026-08-25T09:30:00+09:00",
            )
        ]
    )

    result = schedule_management._postprocess(
        output, {"duration_minutes": 60, "activities": [_BUSY_11_TO_12]}
    )

    assert len(result.schedule_candidates) == 1
    kept = result.schedule_candidates[0]
    assert schedule_management._parse(kept.ends_at) == schedule_management._parse(
        "2026-08-25T10:00:00+09:00"
    )


def test_postprocess_drops_short_candidate_whose_full_duration_is_occupied(monkeypatch):
    """길이를 맞추기 전에는 충돌 검사가 후보가 적어 놓은 구간만 본다 — 잘린 후보가 빠져나간다.

    10:30~11:00 은 비어 있어 30분 후보로는 통과하지만, 실제 회의 60분은 11:00 부터 잡혀 있는
    일정을 침범한다. 길이를 먼저 맞춰야 이 후보가 걸린다.
    """
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id="short-but-blocked",
                starts_at="2026-08-25T10:30:00+09:00",
                ends_at="2026-08-25T11:00:00+09:00",
            )
        ]
    )

    result = schedule_management._postprocess(
        output, {"duration_minutes": 60, "activities": [_BUSY_11_TO_12]}
    )

    assert result.schedule_candidates == []
    assert [conflict.activity_id for conflict in result.conflicts] == ["activity-busy"]


def test_postprocess_drops_short_candidate_that_would_run_past_business_hours(monkeypatch):
    """17:45 시작은 15분짜리로는 통과하지만 60분을 확보하면 18:00 을 넘는다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id="too-late",
                starts_at="2026-08-25T17:45:00+09:00",
                ends_at="2026-08-25T18:00:00+09:00",
            )
        ]
    )

    result = schedule_management._postprocess(output, {"duration_minutes": 60, "activities": []})

    assert result.schedule_candidates == []


def test_postprocess_shrinks_candidate_longer_than_requested_duration(monkeypatch):
    """저장되는 후보 길이는 항상 계약관리가 정한 소요 시간과 같다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id="long",
                starts_at="2026-08-25T09:00:00+09:00",
                ends_at="2026-08-25T10:30:00+09:00",
            )
        ]
    )

    result = schedule_management._postprocess(output, {"duration_minutes": 60, "activities": []})

    assert schedule_management._parse(
        result.schedule_candidates[0].ends_at
    ) == schedule_management._parse("2026-08-25T10:00:00+09:00")


@pytest.mark.parametrize("duration", [None, 0, 4, 481, "60", True])
def test_postprocess_keeps_candidate_length_without_a_usable_duration(monkeypatch, duration):
    """소요 시간을 못 믿을 때는 길이를 손대지 않는다 — 기준 없이 늘리면 없던 충돌을 만든다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id="as-is",
                starts_at="2026-08-25T09:00:00+09:00",
                ends_at="2026-08-25T09:30:00+09:00",
            )
        ]
    )

    result = schedule_management._postprocess(
        output, {"duration_minutes": duration, "activities": []}
    )

    assert schedule_management._parse(
        result.schedule_candidates[0].ends_at
    ) == schedule_management._parse("2026-08-25T09:30:00+09:00")


def test_postprocess_drops_duplicate_candidate_ids(monkeypatch):
    """candidate_id 는 화면에서 칩의 key 로 쓰인다 — 중복되면 선택이 엉킨다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(candidate_id="same", priority=1),
            _candidate(
                candidate_id="same",
                starts_at="2026-08-25T14:00:00+09:00",
                ends_at="2026-08-25T15:00:00+09:00",
                priority=2,
            ),
        ]
    )

    result = schedule_management._postprocess(output, {"activities": []})

    assert len(result.schedule_candidates) == 1


def test_postprocess_drops_candidates_overlapping_a_better_one(monkeypatch):
    """겹치는 후보는 같은 자리에 대한 같은 제안이라 선택지가 늘지 않는다.

    priority 가 앞선 것만 남긴다.
    """
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id="overlapping",
                starts_at="2026-08-25T09:30:00+09:00",
                ends_at="2026-08-25T10:30:00+09:00",
                priority=2,
            ),
            _candidate(candidate_id="best", priority=1),
            _candidate(
                candidate_id="separate",
                starts_at="2026-08-25T14:00:00+09:00",
                ends_at="2026-08-25T15:00:00+09:00",
                priority=3,
            ),
        ]
    )

    result = schedule_management._postprocess(output, {"activities": []})

    assert [item.candidate_id for item in result.schedule_candidates] == ["best", "separate"]


def test_postprocess_caps_candidates_and_renumbers_priority(monkeypatch):
    """상한을 넘으면 자르고, 걸러 내며 생긴 priority 의 구멍을 1부터 다시 메운다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    hours = [9, 10, 11, 13, 14, 15, 16]
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(
                candidate_id=f"c{hour}",
                starts_at=f"2026-08-25T{hour:02d}:00:00+09:00",
                ends_at=f"2026-08-25T{hour + 1:02d}:00:00+09:00",
                priority=index + 3,
            )
            for index, hour in enumerate(hours)
        ]
    )

    result = schedule_management._postprocess(output, {"duration_minutes": 60, "activities": []})

    assert len(result.schedule_candidates) == schedule_management._MAX_CANDIDATES
    assert [item.priority for item in result.schedule_candidates] == [1, 2, 3, 4, 5]
    assert [item.candidate_id for item in result.schedule_candidates] == [
        "c9",
        "c10",
        "c11",
        "c13",
        "c14",
    ]


@pytest.mark.parametrize(
    ("starts_at", "ends_at", "expected"),
    [
        # 선호 기간이 끝나는 날의 오후. 시각으로 자르면 빠지지만 같은 날짜라 남긴다.
        ("2026-08-26T15:00:00+09:00", "2026-08-26T16:00:00+09:00", ["in-window"]),
        # 선호 기간이 시작하는 날의 오전. build_schedule_snapshot 이 시작을 now 로 당겨 둔다.
        ("2026-08-25T09:00:00+09:00", "2026-08-25T10:00:00+09:00", ["in-window"]),
        ("2026-08-27T09:00:00+09:00", "2026-08-27T10:00:00+09:00", []),
    ],
)
def test_postprocess_bounds_candidates_by_preferred_dates(
    monkeypatch, starts_at, ends_at, expected
):
    """선호 기간은 날짜 범위로 본다 — 시각으로 자르면 경계가 하루 중간에 생긴다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[
            _candidate(candidate_id="in-window", starts_at=starts_at, ends_at=ends_at)
        ]
    )
    snapshot = {
        "preferred_starts_at": "2026-08-25T13:00:00+09:00",
        "preferred_ends_at": "2026-08-26T14:00:00+09:00",
        "activities": [],
    }

    result = schedule_management._postprocess(output, snapshot)

    assert [item.candidate_id for item in result.schedule_candidates] == expected


def test_postprocess_skips_window_check_when_preferred_dates_are_unusable(monkeypatch):
    """기간을 읽지 못하면 검사하지 않는다 — 읽기 실패로 후보를 전부 버리지는 않는다."""
    _freeze(monkeypatch, _BEFORE_HOURS)
    output = schedule_management.ScheduleManagementOutput(
        schedule_candidates=[_candidate(candidate_id="kept")]
    )
    snapshot = {
        "preferred_starts_at": "not-a-date",
        "preferred_ends_at": "2026-08-26T14:00:00+09:00",
        "activities": [],
    }

    result = schedule_management._postprocess(output, snapshot)

    assert [item.candidate_id for item in result.schedule_candidates] == ["kept"]


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
