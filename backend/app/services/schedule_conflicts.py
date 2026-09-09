"""담당자의 기존 일정과 시간이 겹치는지 판단한다.

추천은 트리거 시점에 미리 계산해 저장해 두므로(아키텍처 2.1), 계산할 때 비어 있던 자리가
사용자가 카드를 볼 때는 차 있을 수 있다. 일정관리 에이전트의 겹침 검사는 계산 시점 한
번뿐이라, 그 뒤에 잡힌 일정은 잡아내지 못한다.

그래서 겹침을 두 시점에 본다 — 카드를 **조회할 때**(찬 후보를 표시)와 일정을 **등록한
뒤**(뒤늦은 충돌을 안내). 두 시점이 서로 다른 규칙을 쓰면 조회에서 괜찮다고 한 후보가
승인에서 겹친다고 나오므로, 판단 규칙을 여기 한 곳에 둔다.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import Activity

# 종료가 없는(하루 종일) 일정은 그날 전체를 차지한 것으로 본다.
_ALL_DAY = timedelta(days=1)


def _end_or_all_day(starts_at: datetime, ends_at: datetime | None) -> datetime:
    return ends_at or starts_at + _ALL_DAY


def overlaps(
    starts_at: datetime,
    ends_at: datetime | None,
    other_starts_at: datetime,
    other_ends_at: datetime | None,
) -> bool:
    """두 구간이 실제로 겹치는지. 끝이 시작과 맞닿는 것은 겹침이 아니다."""
    return (
        other_starts_at < _end_or_all_day(starts_at, ends_at)
        and _end_or_all_day(other_starts_at, other_ends_at) > starts_at
    )


async def load_activities_in_range(
    db: AsyncSession,
    *,
    team_id: UUID,
    owner_member_ids: Iterable[UUID],
    range_starts_at: datetime,
    range_ends_at: datetime,
) -> list[Activity]:
    """담당자들의 일정 중 주어진 기간에 걸치는 것을 한 번에 가져온다.

    후보마다 따로 조회하면 카드 수 × 후보 수만큼 왕복이 생긴다. 전체 기간으로 한 번만
    가져와 파이썬에서 후보별로 비교한다.
    """
    owner_ids = list(owner_member_ids)
    if not owner_ids:
        return []
    return list(
        (
            await db.execute(
                select(Activity).where(
                    Activity.team_id == team_id,
                    Activity.owner_member_id.in_(owner_ids),
                    Activity.deleted_at.is_(None),
                    Activity.starts_at < range_ends_at,
                    func.coalesce(Activity.ends_at, Activity.starts_at + _ALL_DAY)
                    > range_starts_at,
                )
            )
        )
        .scalars()
        .all()
    )


def first_conflict(
    activities: Sequence[Activity],
    *,
    owner_member_id: UUID,
    starts_at: datetime,
    ends_at: datetime | None,
    exclude_activity_id: UUID | None = None,
) -> Activity | None:
    """이미 가져온 일정 중 이 구간과 겹치는 첫 건. 없으면 None."""
    hits = [
        activity
        for activity in activities
        if activity.owner_member_id == owner_member_id
        and activity.id != exclude_activity_id
        and overlaps(starts_at, ends_at, activity.starts_at, activity.ends_at)
    ]
    if not hits:
        return None
    return min(hits, key=lambda activity: activity.starts_at)


async def find_conflict(
    db: AsyncSession,
    *,
    team_id: UUID,
    owner_member_id: UUID,
    starts_at: datetime,
    ends_at: datetime | None,
    exclude_activity_id: UUID | None = None,
) -> Activity | None:
    """구간 하나만 볼 때 쓰는 단건 조회. 여러 구간은 load_activities_in_range 를 쓴다."""
    conditions = [
        Activity.team_id == team_id,
        Activity.owner_member_id == owner_member_id,
        Activity.deleted_at.is_(None),
        Activity.starts_at < _end_or_all_day(starts_at, ends_at),
        func.coalesce(Activity.ends_at, Activity.starts_at + _ALL_DAY) > starts_at,
    ]
    if exclude_activity_id is not None:
        conditions.append(Activity.id != exclude_activity_id)
    return (
        await db.execute(select(Activity).where(*conditions).order_by(Activity.starts_at).limit(1))
    ).scalar_one_or_none()


def parse_candidate_window(
    candidate: dict, duration_fallback: timedelta = timedelta(hours=1)
) -> tuple[datetime, datetime] | None:
    """일정 후보의 시작·종료를 aware datetime 으로 읽는다. 못 읽으면 None.

    후보는 LLM 출력을 서버가 검증해 저장한 값이지만, 저장된 뒤 스키마가 바뀌었거나 과거
    실행이 남아 있을 수 있어 여기서 한 번 더 방어한다. 시간대가 없는 문자열은 UTC 로 못
    박는다 — 그대로 두면 비교에서 예외가 난다.
    """
    starts_at = _parse_aware(candidate.get("starts_at"))
    if starts_at is None:
        return None
    ends_at = _parse_aware(candidate.get("ends_at"))
    if ends_at is None or ends_at <= starts_at:
        ends_at = starts_at + duration_fallback
    return starts_at, ends_at


def _parse_aware(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = [
    "find_conflict",
    "first_conflict",
    "load_activities_in_range",
    "overlaps",
    "parse_candidate_window",
]
