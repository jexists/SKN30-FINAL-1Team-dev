"""선택한 하위 보고서의 저장 본문을 상위 보고서 작성 근거로 읽는다."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Report
from app.models.workspace import Member

SOURCE_REPORT_LIMIT = 100
_SOURCES = {"업무보고서": "meeting", "일일보고서": "daily", "주간보고서": "weekly"}
_CHILD_KIND = {"daily": "meeting", "weekly": "daily", "monthly": "weekly"}
_NON_BODY_KEYS = {
    "transcript",
    "raw_transcript",
    "ml",
    "ml_result",
    "meeting_analysis",
    "deal_assessment",
    "ai_values",
    "ai_evidence",
    "meeting_shared",
}


def _selected_ids(report: Report) -> list[UUID]:
    content = report.content if isinstance(report.content, dict) else {}
    activities = content.get("activities")
    if activities is None:
        return []
    if not isinstance(activities, list):
        raise HTTPException(422, "report_sources_invalid")
    selected = []
    for activity in activities:
        if not isinstance(activity, dict):
            raise HTTPException(422, "report_sources_invalid")
        source = activity.get("source")
        if not isinstance(source, str):
            raise HTTPException(422, "report_sources_invalid")
        if source not in _SOURCES:
            continue  # 캘린더/첨부 등은 이 보고서 조회 도구의 대상이 아니다.
        included = activity.get("included", False)
        if not isinstance(included, bool):
            raise HTTPException(422, "report_source_included_invalid")
        if not included:
            continue
        if _SOURCES[source] != _CHILD_KIND.get(report.report_kind):
            raise HTTPException(422, "report_source_kind_invalid")
        try:
            source_id = UUID(str(activity["refId"]))
        except (KeyError, ValueError, TypeError) as error:
            raise HTTPException(422, "report_source_id_invalid") from error
        if source_id == report.id:
            raise HTTPException(422, "report_source_self_reference")
        if source_id in selected:
            raise HTTPException(422, "report_source_duplicate")
        selected.append(source_id)
        if len(selected) > SOURCE_REPORT_LIMIT:
            raise HTTPException(422, "report_source_limit_exceeded")
    return selected


def _check_period(parent: Report, source: Report) -> None:
    if parent.report_kind == "daily":
        valid = source.report_date == parent.report_date
    else:
        start, end = parent.period_start, parent.period_end
        if start is None or end is None or end < start:
            raise HTTPException(422, "report_source_period_invalid")
        if parent.report_kind == "weekly":
            valid = start <= source.report_date <= end
        else:
            child_start, child_end = source.period_start, source.period_end
            if child_start is None or child_end is None or child_end < child_start:
                raise HTTPException(422, "report_source_period_invalid")
            # 프론트 월간 자료에는 월초가 걸친 전월 시작 주간보고서도 포함된다.
            valid = child_start <= end and child_end >= start
    if not valid:
        raise HTTPException(422, "report_source_outside_period")


def _values(content: dict) -> dict[str, str]:
    values = content.get("values", {})
    if not isinstance(values, dict):
        raise HTTPException(422, "report_source_values_invalid")
    # content 자체나 ai_values로 대체하면 원문/ML 또는 미검토 AI 초안이 섞인다.
    return {
        key: value
        for key, value in values.items()
        if isinstance(key, str) and key.lower() not in _NON_BODY_KEYS and isinstance(value, str)
    }


def _shared_body(value) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get("body"), str):
        raise HTTPException(422, "report_source_shared_invalid")
    # 본문을 임의로 줄이면 미지정 내용이 유실된다. 평가·근거장부 메타는 전달하지 않는다.
    return {"body": value["body"]}


async def build_report_sources(
    db: AsyncSession,
    member: Member,
    report: Report,
) -> dict[str, Any]:
    """포함된 하위 보고서 최대 100건. 누락·권한·상태·기간 문제는 조용히 빼지 않는다."""
    from app.api.reports import _report_row

    selected_ids = _selected_ids(report)
    if not selected_ids:
        return {"reports": [], "meetings": []}
    if not member.active or member.role_code not in {"member", "manager"}:
        raise HTTPException(403, "member_not_allowed")
    if report.team_id != member.team_id:
        raise HTTPException(404, "report_not_found")
    if report.author_member_id != member.id:
        raise HTTPException(403, "report_not_owned")

    output, meetings = [], {}
    for source_id in selected_ids:
        source = (await _report_row(db, member, source_id))[0]
        if source.report_kind != _CHILD_KIND[report.report_kind]:
            raise HTTPException(422, "report_source_kind_invalid")
        if source.status_code not in {"submitted", "approved"}:
            raise HTTPException(409, "report_source_not_finalized")
        _check_period(report, source)
        if not isinstance(source.content, dict):
            raise HTTPException(422, "report_source_content_invalid")
        content = source.content
        title = content.get("title")
        output.append(
            {
                "id": source.id,
                "sales_deal_id": source.sales_deal_id,
                "source_activity_id": source.source_activity_id,
                "report_date": source.report_date,
                "period_start": source.period_start,
                "period_end": source.period_end,
                "title": title if isinstance(title, str) else "",
                "values": _values(content),
            }
        )
        shared = content.get("meeting_shared")
        if shared is None:
            continue
        if not isinstance(shared, dict) or source.source_activity_id is None:
            raise HTTPException(422, "report_source_shared_invalid")
        meeting = {
            "activity_id": source.source_activity_id,
            "common_report": _shared_body(shared.get("common_report")),
            "unassigned_report": _shared_body(shared.get("unassigned_report")),
        }
        previous = meetings.get(source.source_activity_id)
        if previous is not None and previous != meeting:
            # 서로 다른 실행/수정 버전을 첫 행으로 덮으면 공통·미지정 본문이 사라진다.
            raise HTTPException(409, "report_source_shared_conflict")
        meetings[source.source_activity_id] = meeting
    return jsonable_encoder({"reports": output, "meetings": list(meetings.values())})
