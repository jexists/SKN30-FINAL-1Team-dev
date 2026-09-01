"""합성 선호 기간·기존 일정으로 실제 일정관리 에이전트를 확인한다."""

import asyncio
import json
import os
import sys
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

_SEOUL = ZoneInfo("Asia/Seoul")
_CONFLICTING_ACTIVITY_ID = "activity-existing-1"

_SNAPSHOT = {
    "sales_deal_id": "deal-demo-1",
    "preferred_starts_at": "2026-09-01T09:00:00+09:00",
    "preferred_ends_at": "2026-09-05T18:00:00+09:00",
    "duration_minutes": 30,
    "reason": "견적 만료 전에 의사결정권자 미팅이 필요합니다.",
    "activities": [
        {
            "id": _CONFLICTING_ACTIVITY_ID,
            "owner_member_id": "member-private-1",
            "starts_at": "2026-09-01T09:00:00+09:00",
            "ends_at": "2026-09-01T10:00:00+09:00",
            "all_day": False,
        }
    ],
}


async def check() -> None:
    os.environ["DEBUG"] = "false"

    from app.agents import schedule_management
    from app.core.config import settings

    if not settings.llm_configured:
        raise RuntimeError("LLM_API_URL, LLM_API_KEY, LLM_MODEL 설정이 필요합니다.")

    print("[일정 추천 요청]")
    print(json.dumps(_SNAPSHOT, ensure_ascii=False, indent=2))
    output = await schedule_management.run(_SNAPSHOT)
    print("[일정 추천 응답]")
    print(json.dumps(output.model_dump(), ensure_ascii=False, indent=2))

    if not output.schedule_candidates:
        raise ValueError("일정 후보를 하나도 만들지 않았습니다.")

    if len(output.schedule_candidates) > schedule_management._MAX_CANDIDATES:
        raise ValueError(
            f"후보가 상한({schedule_management._MAX_CANDIDATES}개)보다 많습니다: "
            f"{len(output.schedule_candidates)}개"
        )

    window_start = datetime.fromisoformat(_SNAPSHOT["preferred_starts_at"]).astimezone(_SEOUL)
    window_end = datetime.fromisoformat(_SNAPSHOT["preferred_ends_at"]).astimezone(_SEOUL)
    conflict_start = datetime.fromisoformat(_SNAPSHOT["activities"][0]["starts_at"])
    conflict_end = datetime.fromisoformat(_SNAPSHOT["activities"][0]["ends_at"])
    duration = timedelta(minutes=_SNAPSHOT["duration_minutes"])

    seen_ids: set[str] = set()
    kept: list[tuple[datetime, datetime]] = []
    for candidate in output.schedule_candidates:
        start = datetime.fromisoformat(candidate.starts_at).astimezone(_SEOUL)
        end = datetime.fromisoformat(candidate.ends_at).astimezone(_SEOUL)
        if not (time(9, 0) <= start.time() and end.time() <= time(18, 0)):
            raise ValueError(f"업무시간 밖 후보가 있습니다: {candidate.candidate_id}")
        if end - start != duration:
            raise ValueError(
                f"요청한 소요 시간({_SNAPSHOT['duration_minutes']}분)과 길이가 다른 후보가 "
                f"있습니다: {candidate.candidate_id}"
            )
        # 선호 기간은 날짜 범위로 본다 — 서버 검증(_within_preferred_dates)과 같은 기준이다.
        if not window_start.date() <= start.date() <= window_end.date():
            raise ValueError(f"선호 기간 밖 후보가 있습니다: {candidate.candidate_id}")
        if start < conflict_end and conflict_start < end:
            raise ValueError(f"기존 일정과 겹치는 후보가 있습니다: {candidate.candidate_id}")
        if candidate.candidate_id in seen_ids:
            raise ValueError(f"candidate_id 가 중복입니다: {candidate.candidate_id}")
        if any(start < kept_end and kept_start < end for kept_start, kept_end in kept):
            raise ValueError(f"다른 후보와 시간이 겹칩니다: {candidate.candidate_id}")
        seen_ids.add(candidate.candidate_id)
        kept.append((start, end))

    for conflict in output.conflicts:
        if conflict.activity_id != _CONFLICTING_ACTIVITY_ID:
            raise ValueError(f"모르는 활동을 충돌로 보고했습니다: {conflict.activity_id}")


def main() -> int:
    try:
        asyncio.run(check())
    except Exception as error:
        print(f"[실패] {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("\n[성공] 실제 일정관리 에이전트 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
