"""겹침 판정 규칙을 확인한다.

카드 조회(`contract_suggestions`)와 승인 뒤 안내(`activities._conflict_warning`)가 같은
함수를 쓴다. 두 시점이 다르게 판단하면 조회에서 비었다고 표시한 후보가 승인에서 겹친다고
나와, 사용자가 이유를 알 수 없다.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.crm import Activity
from app.services import schedule_conflicts


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 1, hour, minute, tzinfo=UTC)


def _activity(owner_member_id, starts_at: datetime, ends_at: datetime | None, title="기존 일정"):
    return Activity(
        id=uuid4(),
        team_id=uuid4(),
        owner_member_id=owner_member_id,
        customer_company_id=uuid4(),
        activity_category_id=uuid4(),
        title=title,
        starts_at=starts_at,
        ends_at=ends_at,
        deleted_at=None,
    )


@pytest.mark.parametrize(
    ("other_start", "other_end", "expected"),
    [
        (_at(10, 30), _at(11, 30), True),  # 뒤쪽이 걸침
        (_at(9, 30), _at(10, 30), True),  # 앞쪽이 걸침
        (_at(10, 15), _at(10, 45), True),  # 안에 들어옴
        (_at(9), _at(12), True),  # 통째로 감쌈
        (_at(11), _at(12), False),  # 끝과 시작이 맞닿음 — 겹침이 아니다
        (_at(9), _at(10), False),  # 시작과 끝이 맞닿음
        (_at(14), _at(15), False),  # 완전히 떨어짐
    ],
)
def test_overlaps_treats_touching_edges_as_free(other_start, other_end, expected):
    assert schedule_conflicts.overlaps(_at(10), _at(11), other_start, other_end) is expected


def test_all_day_activity_blocks_the_whole_day():
    """종료가 없는 일정은 그날 전체를 차지한 것으로 본다."""
    assert schedule_conflicts.overlaps(_at(10), _at(11), _at(3), None) is True


def test_first_conflict_ignores_other_owners_and_the_activity_itself():
    owner = uuid4()
    someone_else = _activity(uuid4(), _at(10), _at(11), title="남의 일정")
    myself = _activity(owner, _at(10), _at(11), title="이 일정 자신")
    real = _activity(owner, _at(10, 30), _at(11, 30), title="겹치는 일정")

    hit = schedule_conflicts.first_conflict(
        [someone_else, myself, real],
        owner_member_id=owner,
        starts_at=_at(10),
        ends_at=_at(11),
        exclude_activity_id=myself.id,
    )

    assert hit is not None
    assert hit.title == "겹치는 일정"


def test_first_conflict_returns_the_earliest_hit():
    owner = uuid4()
    late = _activity(owner, _at(10, 45), _at(11, 45), title="나중")
    early = _activity(owner, _at(9, 30), _at(10, 30), title="먼저")

    hit = schedule_conflicts.first_conflict(
        [late, early], owner_member_id=owner, starts_at=_at(10), ends_at=_at(11)
    )

    assert hit is not None
    assert hit.title == "먼저"


def test_first_conflict_returns_none_when_nothing_overlaps():
    owner = uuid4()
    assert (
        schedule_conflicts.first_conflict(
            [_activity(owner, _at(14), _at(15))],
            owner_member_id=owner,
            starts_at=_at(10),
            ends_at=_at(11),
        )
        is None
    )


def test_parse_candidate_window_reads_offsets_and_falls_back_on_a_bad_end():
    window = schedule_conflicts.parse_candidate_window(
        {"starts_at": "2026-09-01T10:00:00+09:00", "ends_at": "2026-09-01T11:00:00+09:00"}
    )
    assert window is not None
    starts_at, ends_at = window
    assert ends_at - starts_at == timedelta(hours=1)

    # 끝이 시작보다 이르면 기본 길이로 대신한다 — 그대로 두면 어떤 것과도 겹치지 않는다.
    window = schedule_conflicts.parse_candidate_window(
        {"starts_at": "2026-09-01T10:00:00+09:00", "ends_at": "2026-09-01T09:00:00+09:00"}
    )
    assert window is not None
    starts_at, ends_at = window
    assert ends_at - starts_at == timedelta(hours=1)


def test_parse_candidate_window_assumes_utc_when_the_offset_is_missing():
    """시간대 없는 문자열을 그대로 두면 aware 값과 비교하다 예외가 난다."""
    window = schedule_conflicts.parse_candidate_window(
        {"starts_at": "2026-09-01T10:00:00", "ends_at": "2026-09-01T11:00:00"}
    )
    assert window is not None
    assert window[0].tzinfo is not None


@pytest.mark.parametrize("candidate", [{}, {"starts_at": "not-a-date"}, {"starts_at": 1}])
def test_parse_candidate_window_gives_up_on_unreadable_values(candidate):
    assert schedule_conflicts.parse_candidate_window(candidate) is None
