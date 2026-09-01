"""선택한 하위 보고서의 저장 본문을 상위 보고서 작성 근거로 읽는다."""

from datetime import date
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Report, ReportDeal, ReportSource, ReportSubmission
from app.models.crm import Activity
from app.models.workspace import Member
from app.services.report_submissions import create_submission, snapshot_sha256

SOURCE_REPORT_LIMIT = 100
_SOURCES = {"업무보고서": "meeting", "일일보고서": "daily", "주간보고서": "weekly"}
_CHILD_KIND = {"daily": "meeting", "weekly": "daily", "monthly": "weekly"}
_SEOUL = ZoneInfo("Asia/Seoul")
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


async def _report_deals(db: AsyncSession, report_id: UUID) -> list[ReportDeal]:
    return list(
        (
            await db.execute(
                select(ReportDeal)
                .where(ReportDeal.report_id == report_id)
                .order_by(ReportDeal.sales_deal_id)
            )
        )
        .scalars()
        .all()
    )


async def _report_source_rows(db: AsyncSession, report_id: UUID) -> list[ReportSource]:
    return list(
        (
            await db.execute(
                select(ReportSource)
                .where(ReportSource.report_id == report_id)
                .order_by(ReportSource.position)
            )
        )
        .scalars()
        .all()
    )


async def materialize_legacy_submission(
    db: AsyncSession,
    report: Report,
) -> ReportSubmission:
    """Create the first immutable snapshot for a finalized pre-V2 report.

    Callers lock ``report`` first. Python builds the snapshot and hash so migrated rows use the
    same canonical representation as every new submission.
    """
    if report.current_submission_id is not None:
        raise HTTPException(409, "report_submission_conflict")
    if report.status_code not in {"submitted", "approved"}:
        raise HTTPException(409, "report_source_not_finalized")

    author = await db.get(Member, report.author_member_id)
    if author is None or author.team_id != report.team_id:
        raise HTTPException(409, "legacy_report_author_missing")
    if report.report_kind != "meeting":
        await sync_report_sources_from_legacy_content(db, author, report)
    sections = await _report_deals(db, report.id)
    submission = await create_submission(
        db,
        report,
        author,
        sections,
        submitted_by_member_id=report.author_member_id,
    )
    if report.status_code == "approved":
        if report.reviewed_by_member_id is None or report.reviewed_at is None:
            raise HTTPException(409, "legacy_report_review_metadata_missing")
        submission.review_status = "approved"
        submission.reviewed_by_member_id = report.reviewed_by_member_id
        submission.reviewed_at = report.reviewed_at
        submission.review_note = report.review_note
    report.current_submission_id = submission.id
    return submission


async def sync_report_sources_from_legacy_content(
    db: AsyncSession,
    member: Member,
    report: Report,
) -> bool:
    """Materialize the current UI selection into canonical source rows.

    Finalized pre-V2 child reports are snapshotted first so a new parent never records a mutable
    report as its provenance.
    """
    if report.report_kind == "meeting" or not isinstance(report.content, dict):
        return False
    raw = report.content.get("activities")
    if raw is None:
        return False
    if not isinstance(raw, list):
        raise HTTPException(422, "report_sources_invalid")

    selected: list[tuple[str, UUID]] = []
    report_ids: list[UUID] = []
    activity_ids: list[UUID] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("source"), str):
            raise HTTPException(422, "report_sources_invalid")
        included = item.get("included", False)
        if not isinstance(included, bool):
            raise HTTPException(422, "report_source_included_invalid")
        if not included:
            continue
        source = item["source"]
        if source not in _SOURCES and source != "캘린더":
            continue
        if source in _SOURCES and _SOURCES[source] != _CHILD_KIND.get(report.report_kind):
            raise HTTPException(422, "report_source_kind_invalid")
        try:
            source_id = UUID(str(item["refId"]))
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, "report_source_id_invalid") from error
        kind = "activity" if source == "캘린더" else "submission"
        selected.append((kind, source_id))
        (activity_ids if kind == "activity" else report_ids).append(source_id)
    if len(selected) > SOURCE_REPORT_LIMIT:
        raise HTTPException(422, "report_source_limit_exceeded")
    if len(set(selected)) != len(selected):
        raise HTTPException(422, "report_source_duplicate")

    if activity_ids:
        await _source_activities(db, member, report, activity_ids)

    source_submissions: dict[UUID, UUID] = {}
    if report_ids:
        expected_kind = _CHILD_KIND.get(report.report_kind)
        conditions = [
            Report.id.in_(report_ids),
            Report.team_id == member.team_id,
            Report.report_kind == expected_kind,
            Report.status_code.in_(("submitted", "approved")),
        ]
        if member.role_code == "member":
            conditions.append(Report.author_member_id == member.id)
        rows = list(
            (
                await db.execute(
                    select(Report).where(*conditions).order_by(Report.id).with_for_update(of=Report)
                )
            )
            .scalars()
            .all()
        )
        by_id = {source.id: source for source in rows}
        if set(by_id) != set(report_ids):
            raise HTTPException(404, "report_not_found")
        for source_id in report_ids:
            source = by_id[source_id]
            _check_period(report, source)
            if source.current_submission_id is None:
                await materialize_legacy_submission(db, source)
                assert source.current_submission_id is not None
            source_submissions[source_id] = source.current_submission_id

    desired = [
        (
            source_id if kind == "activity" else None,
            source_submissions[source_id] if kind == "submission" else None,
        )
        for kind, source_id in selected
    ]
    existing = await _report_source_rows(db, report.id)
    current = [(row.source_activity_id, row.source_report_submission_id) for row in existing]
    if current == desired:
        return False
    if existing:
        await db.execute(delete(ReportSource).where(ReportSource.report_id == report.id))
    for position, (activity_id, submission_id) in enumerate(desired):
        db.add(
            ReportSource(
                report_id=report.id,
                position=position,
                source_activity_id=activity_id,
                source_report_submission_id=submission_id,
            )
        )
    return True


async def _source_submissions(
    db: AsyncSession,
    submission_ids: list[UUID],
) -> dict[UUID, tuple[ReportSubmission, Report]]:
    if not submission_ids:
        return {}
    result = await db.execute(
        select(ReportSubmission, Report)
        .join(Report, Report.id == ReportSubmission.report_id)
        .where(ReportSubmission.id.in_(submission_ids))
    )
    return {submission.id: (submission, report) for submission, report in result.all()}


async def _source_activities(
    db: AsyncSession,
    member: Member,
    report: Report,
    activity_ids: list[UUID],
) -> list[dict[str, Any]]:
    if not activity_ids:
        return []
    if report.report_kind != "daily":
        raise HTTPException(422, "report_source_activity_kind_invalid")
    result = await db.execute(
        select(Activity).where(
            Activity.id.in_(activity_ids),
            Activity.team_id == member.team_id,
            Activity.owner_member_id == member.id,
            Activity.deleted_at.is_(None),
        )
    )
    by_id = {activity.id: activity for activity in result.scalars().all()}
    if set(by_id) != set(activity_ids):
        raise HTTPException(404, "activity_not_found")
    output = []
    for activity_id in activity_ids:
        activity = by_id[activity_id]
        if activity.starts_at.astimezone(_SEOUL).date() != report.report_date:
            raise HTTPException(422, "report_source_outside_period")
        output.append(
            {
                "id": activity.id,
                "source": "캘린더",
                "included": True,
                "title": activity.title,
                "starts_at": activity.starts_at,
                "ends_at": activity.ends_at,
                "location": activity.location,
                "note": activity.note,
            }
        )
    return output


def _snapshot_date(value: Any, detail: str) -> date:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else value
    except ValueError as error:
        raise HTTPException(422, detail) from error


def _check_snapshot_period(parent: Report, snapshot: dict[str, Any]) -> None:
    source_date = _snapshot_date(snapshot.get("report_date"), "report_source_period_invalid")
    if not isinstance(source_date, date):
        raise HTTPException(422, "report_source_period_invalid")
    if parent.report_kind == "daily":
        valid = source_date == parent.report_date
    else:
        start, end = parent.period_start, parent.period_end
        if start is None or end is None or end < start:
            raise HTTPException(422, "report_source_period_invalid")
        if parent.report_kind == "weekly":
            valid = start <= source_date <= end
        else:
            child_start = _snapshot_date(
                snapshot.get("period_start"), "report_source_period_invalid"
            )
            child_end = _snapshot_date(snapshot.get("period_end"), "report_source_period_invalid")
            if not isinstance(child_start, date) or not isinstance(child_end, date):
                raise HTTPException(422, "report_source_period_invalid")
            valid = child_start <= end and child_end >= start
    if not valid:
        raise HTTPException(422, "report_source_outside_period")


def _snapshot_values(snapshot: dict[str, Any]) -> dict[str, Any]:
    structured = snapshot.get("structured_values")
    if not isinstance(structured, dict):
        raise HTTPException(422, "report_source_values_invalid")
    values = dict(structured)
    body = snapshot.get("body")
    if body is not None:
        if not isinstance(body, str):
            raise HTTPException(422, "report_source_content_invalid")
        values["body"] = body
    return values


async def _build_normalized_sources(
    db: AsyncSession,
    member: Member,
    report: Report,
    rows: list[ReportSource],
) -> dict[str, Any]:
    submission_ids = [
        row.source_report_submission_id
        for row in rows
        if row.source_report_submission_id is not None
    ]
    activity_ids = [row.source_activity_id for row in rows if row.source_activity_id is not None]
    if len(rows) > SOURCE_REPORT_LIMIT:
        raise HTTPException(422, "report_source_limit_exceeded")
    if len(set(submission_ids)) != len(submission_ids):
        raise HTTPException(422, "report_source_duplicate")
    if len(set(activity_ids)) != len(activity_ids):
        raise HTTPException(422, "report_source_duplicate")
    loaded = await _source_submissions(db, submission_ids)
    if set(loaded) != set(submission_ids):
        raise HTTPException(404, "report_source_not_found")

    activities = await _source_activities(db, member, report, activity_ids)
    output: list[dict[str, Any]] = []
    meetings: dict[UUID, dict[str, Any]] = {}
    for submission_id in submission_ids:
        submission, source = loaded[submission_id]
        if submission.team_id != member.team_id or source.team_id != member.team_id:
            raise HTTPException(404, "report_not_found")
        if member.role_code == "member" and source.author_member_id != member.id:
            raise HTTPException(404, "report_not_found")
        if source.id == report.id:
            raise HTTPException(422, "report_source_self_reference")
        if submission.review_status not in {"pending", "approved"}:
            raise HTTPException(409, "report_source_not_finalized")
        snapshot = submission.snapshot
        if not isinstance(snapshot, dict):
            raise HTTPException(422, "report_source_content_invalid")
        if snapshot_sha256(snapshot) != submission.snapshot_sha256:
            raise HTTPException(409, "report_source_snapshot_hash_mismatch")
        if snapshot.get("report_kind") != _CHILD_KIND.get(report.report_kind):
            raise HTTPException(422, "report_source_kind_invalid")
        _check_snapshot_period(report, snapshot)

        source_activity_id = snapshot.get("source_activity_id")
        if snapshot["report_kind"] == "meeting":
            deals = snapshot.get("deals")
            if not isinstance(deals, list) or not deals:
                raise HTTPException(422, "report_source_deal_sections_required")
            for deal in deals:
                if not isinstance(deal, dict):
                    raise HTTPException(422, "report_source_content_invalid")
                output.append(
                    {
                        "id": source.id,
                        "submission_id": submission.id,
                        "sales_deal_id": deal.get("sales_deal_id"),
                        "source_activity_id": source_activity_id,
                        "report_date": snapshot.get("report_date"),
                        "period_start": snapshot.get("period_start"),
                        "period_end": snapshot.get("period_end"),
                        "title": deal.get("title") if isinstance(deal.get("title"), str) else "",
                        "values": _snapshot_values(deal),
                    }
                )
            if source_activity_id is not None:
                try:
                    activity_id = UUID(str(source_activity_id))
                except (TypeError, ValueError) as error:
                    raise HTTPException(422, "report_source_content_invalid") from error
                meeting = {
                    "activity_id": activity_id,
                    "common_report": (
                        {"body": snapshot["common_body"]}
                        if isinstance(snapshot.get("common_body"), str)
                        else None
                    ),
                    "unassigned_report": (
                        {"body": snapshot["unassigned_body"]}
                        if isinstance(snapshot.get("unassigned_body"), str)
                        else None
                    ),
                }
                previous = meetings.get(activity_id)
                if previous is not None and previous != meeting:
                    raise HTTPException(409, "report_source_shared_conflict")
                meetings[activity_id] = meeting
        else:
            output.append(
                {
                    "id": source.id,
                    "submission_id": submission.id,
                    "sales_deal_id": None,
                    "source_activity_id": source_activity_id,
                    "report_date": snapshot.get("report_date"),
                    "period_start": snapshot.get("period_start"),
                    "period_end": snapshot.get("period_end"),
                    "title": (
                        snapshot.get("title") if isinstance(snapshot.get("title"), str) else ""
                    ),
                    "values": _snapshot_values(snapshot),
                }
            )
    return jsonable_encoder(
        {
            "reports": output,
            "meetings": list(meetings.values()),
            "activities": activities,
        }
    )


async def build_report_sources(
    db: AsyncSession,
    member: Member,
    report: Report,
) -> dict[str, Any]:
    """포함된 하위 보고서 최대 100건. 누락·권한·상태·기간 문제는 조용히 빼지 않는다."""
    from app.api.reports import _report_row

    normalized_rows = await _report_source_rows(db, report.id)
    if normalized_rows:
        if not member.active or member.role_code not in {"member", "manager"}:
            raise HTTPException(403, "member_not_allowed")
        if report.team_id != member.team_id:
            raise HTTPException(404, "report_not_found")
        if report.author_member_id != member.id:
            raise HTTPException(403, "report_not_owned")
        return await _build_normalized_sources(db, member, report, normalized_rows)

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
        if source.report_kind == "meeting":
            sections = await _report_deals(db, source.id)
            if not sections:
                raise HTTPException(422, "report_source_deal_sections_required")
            source_contents = [(section.sales_deal_id, section.content) for section in sections]
        else:
            source_contents = [(source.sales_deal_id, content)]
        for sales_deal_id, source_content in source_contents:
            if not isinstance(source_content, dict):
                raise HTTPException(422, "report_source_content_invalid")
            title = source_content.get("title")
            output.append(
                {
                    "id": source.id,
                    "sales_deal_id": sales_deal_id,
                    "source_activity_id": source.source_activity_id,
                    "report_date": source.report_date,
                    "period_start": source.period_start,
                    "period_end": source.period_end,
                    "title": title if isinstance(title, str) else "",
                    "values": _values(source_content),
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
