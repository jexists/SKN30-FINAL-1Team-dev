"""선호 기간과 기존 일정을 바탕으로 일정 후보를 제안하는 Agent."""

import json
from datetime import datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from app.services.llm import generate_structured

_SEOUL = ZoneInfo("Asia/Seoul")
_FAR_FUTURE = datetime(9999, 12, 31, tzinfo=_SEOUL)
_BUSINESS_START = time(9, 0)
_BUSINESS_END = time(18, 0)

PROMPT_VERSION = "schedule_management.v2"
SYSTEM_PROMPT = (
    "너는 영업 일정관리 보조 AI다. "
    "입력의 선호 기간, 소요 시간과 기존 일정만 사용해 후보를 제안하라. "
    "시간은 반드시 ISO 8601 offset 포함 형식으로 출력하라. 기존 일정과 겹치는 후보는 만들지 말고 "
    "발견한 충돌은 conflicts에 근거 ID와 함께 남겨라. 실제 일정을 생성했다고 표현하지 말라. "
    "모든 후보의 시작·종료 시각은 Asia/Seoul 기준 09:00~18:00 업무시간 안에서만 제안하라."
)


class ScheduleConflict(BaseModel):
    """일정 후보를 만들 때 확인한 기존 일정 충돌 한 건을 표현한다.

    충돌 근거가 된 활동 ID와 관련 회원 ID, 충돌 유형을 남겨 사용자가 후보 제외
    사유를 확인하고 승인 시 서버가 다시 검증할 수 있게 한다.
    """

    model_config = ConfigDict(extra="forbid")
    activity_id: str
    member_id: str | None = None
    reason: Literal["time_overlap", "all_day_overlap", "invalid_time"]


class ScheduleCandidate(BaseModel):
    """일정관리 Agent가 제안하는 하나의 일정 후보를 정의한다.

    후보 식별자, 제목, 활동 종류, 시작·종료 시각, 우선순위와 추천 이유만 담는다.
    이 모델은 실제 `activity` 행을 생성하지 않으며 사용자 승인 전 제안으로만 사용된다.
    """

    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    activity_type: Literal["meeting", "task"]
    starts_at: str
    ends_at: str
    priority: int = Field(ge=1, le=100)
    reason: str = Field(default="", max_length=1_000)


class ScheduleManagementOutput(BaseModel):
    """LLM이 반환해야 하는 일정관리 Agent의 최종 구조화 출력이다.

    충돌하지 않는 일정 후보와 후보 계산 중 발견한 충돌 근거를 하나의 검증 가능한
    결과로 묶어 `agent_run.output_snapshot`에 저장할 수 있게 한다.
    """

    model_config = ConfigDict(extra="forbid")
    schedule_candidates: list[ScheduleCandidate] = Field(default_factory=list, max_length=20)
    conflicts: list[ScheduleConflict] = Field(default_factory=list, max_length=100)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _within_business_hours(candidate: ScheduleCandidate) -> bool:
    """후보 시작·종료가 Asia/Seoul 09:00~18:00 안, 같은 날짜에 있는지 확인한다."""
    try:
        start = _parse(candidate.starts_at).astimezone(_SEOUL)
        end = _parse(candidate.ends_at).astimezone(_SEOUL)
    except ValueError:
        return False
    if end <= start or start.date() != end.date():
        return False
    return _BUSINESS_START <= start.time() and end.time() <= _BUSINESS_END


def _occupied_range(activity: dict[str, Any]) -> tuple[datetime, datetime]:
    """활동 하나가 실제로 점유하는 [start, end) 구간. all_day 는 로컬 날짜 전체로 치환한다."""
    start = _parse(activity["starts_at"]).astimezone(_SEOUL)
    if activity.get("all_day"):
        day_start = datetime.combine(start.date(), time.min, tzinfo=_SEOUL)
        return day_start, day_start + timedelta(days=1)
    ends_at = activity.get("ends_at")
    end = _FAR_FUTURE if ends_at is None else _parse(ends_at).astimezone(_SEOUL)
    return start, end


def _conflicts_for(
    candidate: ScheduleCandidate, activities: list[dict[str, Any]]
) -> list[ScheduleConflict]:
    """반열린 구간 겹침을 계산해, 후보와 실제로 충돌하는 활동만 근거로 남긴다."""
    candidate_start = _parse(candidate.starts_at).astimezone(_SEOUL)
    candidate_end = _parse(candidate.ends_at).astimezone(_SEOUL)
    found: list[ScheduleConflict] = []
    for activity in activities:
        occupied_start, occupied_end = _occupied_range(activity)
        if candidate_start < occupied_end and occupied_start < candidate_end:
            found.append(
                ScheduleConflict(
                    activity_id=str(activity["id"]),
                    member_id=activity.get("owner_member_id"),
                    reason="all_day_overlap" if activity.get("all_day") else "time_overlap",
                )
            )
    return found


def _postprocess(
    output: ScheduleManagementOutput, snapshot: dict[str, Any]
) -> ScheduleManagementOutput:
    """LLM이 반환한 후보를 결정론적 규칙으로 재검증한다.

    LLM 프롬프트만으로는 겹침·업무시간 규칙 준수를 보장할 수 없어, 여기서 같은 스냅샷의
    activities 로 다시 계산하고, 어긋난 후보는 제외하거나 conflicts 로 옮긴다.
    """
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


async def run(snapshot: dict[str, Any]) -> ScheduleManagementOutput:
    """실행 시점의 일정 스냅샷으로 LLM을 호출하고 검증된 후보 결과를 반환한다.

    DB 일정 조회, 팀 권한 검사와 실제 일정 생성은 이 함수의 책임이 아니다. 호출 서비스가
    준비한 스냅샷을 전달하며, 공통 LLM 경계가 출력 JSON을 이 파일의 schema로 검증한다.
    이후 겹침·업무시간 규칙은 `_postprocess`가 결정론적으로 다시 검증한다.
    """

    output = await generate_structured(
        instructions=SYSTEM_PROMPT,
        input_text=json.dumps(snapshot, ensure_ascii=False, default=str),
        schema=ScheduleManagementOutput,
        schema_name="schedule_management",
    )
    return _postprocess(output, snapshot)
