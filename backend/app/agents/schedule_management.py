"""선호 기간과 기존 일정을 바탕으로 겹치지 않는 일정 후보를 제안하는 에이전트."""

import json
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.llm import generate_structured

# 프롬프트는 라우터가 아니라 이 에이전트 파일에서만 관리한다.
# 내용을 바꾸면 실행 이력에서 구분할 수 있도록 버전도 함께 올린다.
PROMPT_VERSION = "schedule_management.v2"

SYSTEM_PROMPT = """너는 영업 일정관리를 보조하는 AI다.
입력된 선호 기간, 소요 시간과 기존 일정만 근거로 후보를 만든다.

입력의 current_date는 지금 시각(Asia/Seoul)이다. 모든 후보는 current_date 이후여야
한다 — 이미 지난 날짜를 제안하지 마라.

모든 후보의 시작·종료는 Asia/Seoul 기준 09:00~18:00 업무시간 안에서, 토·일요일을 뺀
평일(월~금)에만 제안하라.
기존 일정과 겹치는 후보는 만들지 말고, 발견한 충돌은 conflicts 에 근거 ID와 함께 남겨라.

각 후보의 길이는 duration_minutes 와 정확히 같아야 한다 — 자리가 부족하다고 짧게 줄이지
마라. 그 길이가 통째로 비어 있는 시간만 후보로 내라.

후보는 preferred_starts_at 부터 preferred_ends_at 까지의 날짜 안에서 고르라.

서로 겹치는 후보를 여러 개 내지 말고, 고를 만한 서로 다른 시간을 최대 5개까지만 내라.

priority 는 1이 가장 추천하는 후보라는 뜻이다. 숫자가 클수록 덜 추천한다. 가장 추천하는
후보부터 1, 2, 3 순으로 매겨라.

실제 일정을 만들었다고 표현하지 마라. 이 에이전트는 후보만 제안한다.
JSON 만 출력한다."""

_SEOUL = ZoneInfo("Asia/Seoul")
# ends_at 이 없는 활동은 하루 종일 점유한 것으로 본다.
_DEFAULT_DURATION = timedelta(days=1)
_BUSINESS_START = time(9, 0)
_BUSINESS_END = time(18, 0)
# 사용자에게 보여줄 후보의 상한. LLM 출력 상한(10)과 달리 서버 검사를 통과한 뒤에 건다.
# 실행 143건 실측에서 후보는 3개와 5개에 몰려 있었고, 6개 이상은 18건뿐이었다 — 5로 두면
# 그 꼬리만 정리하고 나머지 실행의 선택지는 그대로 남는다.
_MAX_CANDIDATES = 5
# duration_minutes 로 인정하는 범위. AgentRunCreate.duration_minutes 와 같게 맞춘다.
_MIN_DURATION_MINUTES = 5
_MAX_DURATION_MINUTES = 480


class ScheduleConflict(BaseModel):
    """일정 후보와 겹치는 기존 활동. 승인 시 서버가 같은 ID로 다시 검증한다."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str
    member_id: str | None = None
    reason: Literal["time_overlap", "all_day_overlap", "invalid_time"]


class ScheduleCandidate(BaseModel):
    """일정관리 Agent가 제안하는 후보 하나. 승인 전에는 실제 activity가 아니다."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    starts_at: str
    ends_at: str
    # 1이 가장 추천하는 후보다. 숫자가 클수록 덜 추천한다 — 프롬프트에도 같은 방향을 못박아 둔다.
    priority: int = Field(ge=1, le=100, description="1이 가장 추천하는 후보다. 클수록 덜 추천한다.")
    reason: str = Field(default="", max_length=1_000)


class _ActivityWindow(BaseModel):
    """LLM에는 시간 범위와 충돌 식별자만 전달한다. 담당자 등 개인정보는 보내지 않는다."""

    model_config = ConfigDict(extra="ignore")

    id: str
    starts_at: str
    ends_at: str | None = None
    all_day: bool = False


class _ScheduleLLMInput(BaseModel):
    """LLM에 보낼 값의 허용 목록. snapshot에 다른 키가 있어도 여기 없으면 보내지 않는다."""

    model_config = ConfigDict(extra="forbid")

    sales_deal_id: str | None = None
    preferred_starts_at: str | None = None
    preferred_ends_at: str | None = None
    duration_minutes: int | None = None
    reason: str | None = None
    activities: list[_ActivityWindow] = Field(default_factory=list)
    # LLM이 과거 날짜를 제안하지 않도록 기준점을 함께 보낸다.
    current_date: str


class ScheduleManagementOutput(BaseModel):
    """일정관리 Agent의 최종 출력. `agent_run.output_snapshot`에 그대로 저장된다."""

    model_config = ConfigDict(extra="forbid")

    schedule_candidates: list[ScheduleCandidate] = Field(default_factory=list, max_length=10)
    conflicts: list[ScheduleConflict] = Field(default_factory=list, max_length=100)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _now() -> datetime:
    return datetime.now(_SEOUL)


def _within_business_hours(candidate: ScheduleCandidate) -> bool:
    """후보 시작·종료가 같은 날짜의 평일 Asia/Seoul 09:00~18:00 안에 있는지 확인한다."""
    try:
        start = _parse(candidate.starts_at).astimezone(_SEOUL)
        end = _parse(candidate.ends_at).astimezone(_SEOUL)
    except ValueError:
        return False
    if end <= start or start.date() != end.date():
        return False
    if start.weekday() >= 5:  # 5=토요일, 6=일요일
        return False
    return _BUSINESS_START <= start.time() and end.time() <= _BUSINESS_END


def _required_duration(snapshot: dict[str, Any]) -> int | None:
    """확보해야 하는 회의 길이(분). 값이 없거나 범위 밖이면 None — 길이를 강제하지 않는다.

    선호 시간대를 사용자가 직접 넣는 실행에는 소요 시간이 비어 올 수 있다. 그때는 LLM 이
    정한 길이를 그대로 둔다 — 기준이 없는데 임의의 기본값으로 늘리면 없던 충돌을 만든다.
    """
    value = snapshot.get("duration_minutes")
    # bool 은 int 의 하위형이라 isinstance 를 그냥 통과한다. True 가 1분으로 읽히면 모든
    # 후보가 1분으로 줄어든다.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not _MIN_DURATION_MINUTES <= value <= _MAX_DURATION_MINUTES:
        return None
    return value


def _with_duration(candidate: ScheduleCandidate, duration: int | None) -> ScheduleCandidate:
    """후보 길이를 요청받은 소요 시간에 맞춘다. 시작 시각은 LLM 이 고른 값을 그대로 둔다.

    LLM 이 60분 요청에 30분 후보를 내면 뒤 30분은 아무도 검사하지 않는다 — 업무시간 검사도
    충돌 검사도 후보가 적어 놓은 구간만 보기 때문이다. 그대로 승인하면 실제 회의가 남의
    일정 위로 밀고 들어가는데 예외도 로그도 남지 않는다.

    그래서 검사 전에 길이부터 맞춘다. 짧으면 늘리고 길면 줄여, 저장되는 후보의 길이가 항상
    계약관리가 정한 소요 시간과 같도록 한다. 늘린 구간이 업무시간을 넘거나 다른 일정과
    겹치면 이어지는 검사가 그 후보를 걸러 낸다.
    """
    if duration is None:
        return candidate
    try:
        start = _parse(candidate.starts_at)
    except ValueError:
        # 시작 시각을 못 읽으면 손대지 않는다. _within_business_hours 가 같은 이유로 뺀다.
        return candidate
    return candidate.model_copy(
        update={"ends_at": (start + timedelta(minutes=duration)).isoformat()}
    )


def _preferred_dates(snapshot: dict[str, Any]) -> tuple[date, date] | None:
    """선호 기간을 Asia/Seoul 날짜 범위로 읽는다. 없거나 읽을 수 없으면 None.

    시각이 아니라 날짜로 비교한다. 선호 기간은 의미상 "9월 1일~9월 4일 사이"라는 날짜
    범위인데 저장은 타임스탬프라, 시각으로 자르면 경계가 하루 중간에 생긴다. 실측에서
    기간을 벗어난 후보 54개 중 36개가 "종료일 오후"였다 — 종료가 14:00 이라서 같은 날
    15:00 후보가 밖으로 밀린 경우다. 시작도 마찬가지로 build_schedule_snapshot 이
    max(제안 시각, now) 로 당겨 놓아 하루 중간에서 시작한다.
    """
    starts_at = snapshot.get("preferred_starts_at")
    ends_at = snapshot.get("preferred_ends_at")
    if not starts_at or not ends_at:
        return None
    try:
        start = _parse(starts_at).astimezone(_SEOUL)
        end = _parse(ends_at).astimezone(_SEOUL)
    except (TypeError, ValueError):
        return None
    if end < start:
        return None
    return start.date(), end.date()


def _within_preferred_dates(candidate: ScheduleCandidate, window: tuple[date, date] | None) -> bool:
    """후보 날짜가 선호 기간 안인지 본다. 기간을 읽지 못했으면 검사하지 않는다.

    시작 날짜만 본다 — 시작과 종료가 같은 날짜인 것은 _within_business_hours 가 이미 보장한다.
    """
    if window is None:
        return True
    try:
        start = _parse(candidate.starts_at).astimezone(_SEOUL)
    except ValueError:
        return False
    return window[0] <= start.date() <= window[1]


def _occupied_range(activity: dict[str, Any]) -> tuple[datetime, datetime]:
    """활동이 차지하는 시작~종료 시각. 종료 시각은 포함하지 않는다. all_day는 하루 전체로 본다."""
    start = _parse(activity["starts_at"]).astimezone(_SEOUL)
    if activity.get("all_day"):
        day_start = datetime.combine(start.date(), time.min, tzinfo=_SEOUL)
        return day_start, day_start + timedelta(days=1)
    ends_at = activity.get("ends_at")
    end = start + _DEFAULT_DURATION if ends_at is None else _parse(ends_at).astimezone(_SEOUL)
    return start, end


def _conflicts_for(
    candidate: ScheduleCandidate, activities: list[dict[str, Any]]
) -> list[ScheduleConflict]:
    """시간이 실제로 겹치는 활동만 다시 계산해 충돌 근거로 남긴다.

    개별 활동의 시각이 없거나 파싱할 수 없어도 전체 계산을 중단하지 않는다 — 그 활동만
    `invalid_time` 충돌로 표시하고 나머지 활동은 정상적으로 검사한다.
    """
    candidate_start = _parse(candidate.starts_at).astimezone(_SEOUL)
    candidate_end = _parse(candidate.ends_at).astimezone(_SEOUL)
    found: list[ScheduleConflict] = []
    for activity in activities:
        activity_id = str(activity.get("id", "unknown"))
        try:
            occupied_start, occupied_end = _occupied_range(activity)
        except (KeyError, ValueError, TypeError):
            found.append(
                ScheduleConflict(
                    activity_id=activity_id,
                    member_id=activity.get("owner_member_id"),
                    reason="invalid_time",
                )
            )
            continue
        # 한쪽 종료 시각과 다른 쪽 시작 시각이 같으면(맞닿기만 하면) 겹침이 아니다.
        if candidate_start < occupied_end and occupied_start < candidate_end:
            found.append(
                ScheduleConflict(
                    activity_id=activity_id,
                    member_id=activity.get("owner_member_id"),
                    reason="all_day_overlap" if activity.get("all_day") else "time_overlap",
                )
            )
    return found


def _dedupe_and_cap(candidates: list[ScheduleCandidate]) -> list[ScheduleCandidate]:
    """서로 겹치거나 중복인 후보를 걸러 내고 상한까지만 남긴 뒤 priority 를 다시 매긴다.

    개별 검사와 달리 후보 하나만 봐서는 판단할 수 없어(다른 후보와 비교해야 한다) 검사를
    모두 마친 목록에 한 번 적용한다. 순서를 뒤집어 먼저 자르면, 잘라 낸 자리에 있던 후보가
    유효했는지와 무관하게 목록이 비어 남은 후보를 잃는다.

    같은 candidate_id 는 화면에서 칩의 key 로 쓰여 중복되면 선택이 엉킨다. 시간이 겹치는
    후보는 같은 자리에 대한 사실상 같은 제안이라, 고를 수 있는 시간이 늘지 않고 칩만 는다.
    """
    kept: list[ScheduleCandidate] = []
    seen_ids: set[str] = set()
    ranges: list[tuple[datetime, datetime]] = []
    # priority 1이 가장 추천이므로 오름차순으로 본다. 같은 priority 는 이른 시각을 먼저 둔다.
    for candidate in sorted(candidates, key=lambda item: (item.priority, item.starts_at)):
        if candidate.candidate_id in seen_ids:
            continue
        start = _parse(candidate.starts_at).astimezone(_SEOUL)
        end = _parse(candidate.ends_at).astimezone(_SEOUL)
        if any(start < kept_end and kept_start < end for kept_start, kept_end in ranges):
            continue
        seen_ids.add(candidate.candidate_id)
        ranges.append((start, end))
        # 남은 자리에 맞춰 1부터 다시 매긴다. 걸러 내면서 생긴 번호의 구멍을 그대로 두면
        # "1이 가장 추천"이라는 계약이 화면에서 깨진다(3번부터 시작하는 목록이 된다).
        kept.append(candidate.model_copy(update={"priority": len(kept) + 1}))
        if len(kept) == _MAX_CANDIDATES:
            break
    return kept


def _postprocess(
    output: ScheduleManagementOutput, snapshot: dict[str, Any]
) -> ScheduleManagementOutput:
    """업무시간 밖·주말·과거·선호 기간 밖 후보는 버리고, 겹치는 후보는 conflicts로 옮긴다.

    프롬프트로 지침을 줘도 LLM이 어길 수 있어, 미래 여부는 여기서 다시 결정적으로 검증한다.

    길이를 먼저 맞추고 나머지를 검사한다 — 검사받는 구간과 승인 시 실제로 등록될 구간이
    같아야 검사가 뜻을 갖는다.
    """
    now = _now()
    activities = snapshot.get("activities") or []
    duration = _required_duration(snapshot)
    preferred_dates = _preferred_dates(snapshot)
    kept: list[ScheduleCandidate] = []
    conflicts_by_activity = {conflict.activity_id: conflict for conflict in output.conflicts}
    for candidate in output.schedule_candidates:
        candidate = _with_duration(candidate, duration)
        if not _within_business_hours(candidate):
            continue
        if _parse(candidate.starts_at).astimezone(_SEOUL) < now:
            continue
        if not _within_preferred_dates(candidate, preferred_dates):
            continue
        conflicts = _conflicts_for(candidate, activities)
        if conflicts:
            for conflict in conflicts:
                conflicts_by_activity[conflict.activity_id] = conflict
            continue
        kept.append(candidate)
    return ScheduleManagementOutput(
        schedule_candidates=_dedupe_and_cap(kept),
        conflicts=list(conflicts_by_activity.values()),
    )


def _llm_activities(activities: list[dict[str, Any]]) -> list[_ActivityWindow]:
    """형식이 안 맞는 활동은 조용히 건너뛴다 — 프롬프트 구성이 그 하나 때문에 실패하지 않는다."""
    windows = []
    for activity in activities:
        try:
            windows.append(_ActivityWindow.model_validate(activity))
        except ValidationError:
            continue
    return windows


async def run(snapshot: dict[str, Any]) -> ScheduleManagementOutput:
    """저장된 일정 스냅샷으로 LLM을 호출한다. 권한 검사와 실제 일정 생성은 호출 서비스가 맡는다."""
    llm_input = _ScheduleLLMInput(
        sales_deal_id=snapshot.get("sales_deal_id"),
        preferred_starts_at=snapshot.get("preferred_starts_at"),
        preferred_ends_at=snapshot.get("preferred_ends_at"),
        duration_minutes=snapshot.get("duration_minutes"),
        reason=snapshot.get("reason"),
        activities=_llm_activities(snapshot.get("activities") or []),
        current_date=_now().isoformat(),
    )
    output = await generate_structured(
        instructions=SYSTEM_PROMPT,
        input_text=json.dumps(llm_input.model_dump(), ensure_ascii=False, default=str),
        schema=ScheduleManagementOutput,
        schema_name="schedule_management",
    )
    # 담당자 등 개인정보가 포함된 원본 snapshot은 로컬 충돌 재계산에만 쓰고 LLM에는 보내지 않는다.
    return _postprocess(output, snapshot)
