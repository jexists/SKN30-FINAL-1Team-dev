"""선호 기간과 기존 일정을 바탕으로 겹치지 않는 일정 후보를 제안하는 에이전트."""

import json
from datetime import datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.services.llm import generate_structured

# 프롬프트는 라우터가 아니라 이 에이전트 파일에서만 관리한다.
# 내용을 바꾸면 실행 이력에서 구분할 수 있도록 버전도 함께 올린다.
PROMPT_VERSION = "schedule_management.v1"

SYSTEM_PROMPT = """너는 영업 일정관리를 보조하는 AI다.
입력된 선호 기간, 소요 시간과 기존 일정만 근거로 후보를 만든다.

모든 후보의 시작·종료는 Asia/Seoul 기준 09:00~18:00 업무시간 안에서만 제안하라.
기존 일정과 겹치는 후보는 만들지 말고, 발견한 충돌은 conflicts 에 근거 ID와 함께 남겨라.

priority 는 1이 가장 추천하는 후보라는 뜻이다. 숫자가 클수록 덜 추천한다. 가장 추천하는
후보부터 1, 2, 3 순으로 매겨라.

실제 일정을 만들었다고 표현하지 마라. 이 에이전트는 후보만 제안한다.
JSON 만 출력한다."""

_SEOUL = ZoneInfo("Asia/Seoul")
# ends_at 이 없는 활동은 하루 종일 점유한 것으로 본다.
_DEFAULT_DURATION = timedelta(days=1)
_BUSINESS_START = time(9, 0)
_BUSINESS_END = time(18, 0)


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


class ScheduleManagementOutput(BaseModel):
    """일정관리 Agent의 최종 출력. `agent_run.output_snapshot`에 그대로 저장된다."""

    model_config = ConfigDict(extra="forbid")

    schedule_candidates: list[ScheduleCandidate] = Field(default_factory=list, max_length=10)
    conflicts: list[ScheduleConflict] = Field(default_factory=list, max_length=100)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _within_business_hours(candidate: ScheduleCandidate) -> bool:
    """후보 시작·종료가 같은 날짜의 Asia/Seoul 09:00~18:00 안에 있는지 확인한다."""
    try:
        start = _parse(candidate.starts_at).astimezone(_SEOUL)
        end = _parse(candidate.ends_at).astimezone(_SEOUL)
    except ValueError:
        return False
    if end <= start or start.date() != end.date():
        return False
    return _BUSINESS_START <= start.time() and end.time() <= _BUSINESS_END


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


def _postprocess(
    output: ScheduleManagementOutput, snapshot: dict[str, Any]
) -> ScheduleManagementOutput:
    """09~18시 밖 후보는 버리고, 기존 일정과 겹치는 후보는 빼서 conflicts로 옮긴다."""
    activities = snapshot.get("activities") or []
    kept: list[ScheduleCandidate] = []
    conflicts_by_activity = {conflict.activity_id: conflict for conflict in output.conflicts}
    for candidate in output.schedule_candidates:
        if not _within_business_hours(candidate):
            continue
        conflicts = _conflicts_for(candidate, activities)
        if conflicts:
            for conflict in conflicts:
                conflicts_by_activity[conflict.activity_id] = conflict
            continue
        kept.append(candidate)
    return ScheduleManagementOutput(
        schedule_candidates=kept,
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
    )
    output = await generate_structured(
        instructions=SYSTEM_PROMPT,
        input_text=json.dumps(llm_input.model_dump(), ensure_ascii=False, default=str),
        schema=ScheduleManagementOutput,
        schema_name="schedule_management",
    )
    # 담당자 등 개인정보가 포함된 원본 snapshot은 로컬 충돌 재계산에만 쓰고 LLM에는 보내지 않는다.
    return _postprocess(output, snapshot)
