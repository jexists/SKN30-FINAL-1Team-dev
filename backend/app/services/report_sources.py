"""선택한 바로 아래 보고서의 확정 제출본을 검증하고 고정한다."""

from datetime import date
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.content import Report, ReportDeal, ReportSource, ReportSubmission
from app.models.crm import Activity
from app.models.workspace import Member
from app.services.report_submissions import (
    create_submission,
    submission_ref,
)

SOURCE_REPORT_LIMIT = 100
SOURCE_CONTRACT = "hierarchy.v2"
_SOURCES = {"업무보고서": "meeting", "일일보고서": "daily", "주간보고서": "weekly"}
_CHILD_KIND = {"daily": "meeting", "weekly": "daily", "monthly": "weekly"}
_SEOUL = ZoneInfo("Asia/Seoul")


def _body_values(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, str):
        raise HTTPException(422, "report_source_content_invalid")
    return {"body": value}


def _shared_body(value) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(422, "report_source_shared_invalid")
    return {"body": value}


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
    """Restore pre-V2 provenance only when materializing its first historical submission.

    Generation/finalize validates the same selection with the current contract.
    """
    if report.report_kind == "meeting" or not isinstance(report.content, dict):
        return False
    desired, activities = await _resolve_report_source_refs(db, member, report)
    rows = _source_rows(report.id, desired)
    # Validate the exact immutable snapshots before recording their IDs as provenance.
    await _build_normalized_sources(
        db,
        member,
        report,
        rows,
        resolved_activities=activities,
        legacy=True,
    )

    existing = await _report_source_rows(db, report.id)
    current = [(row.source_activity_id, row.source_report_submission_id) for row in existing]
    if current == desired:
        return False
    if existing:
        await db.execute(delete(ReportSource).where(ReportSource.report_id == report.id))
    for row in rows:
        db.add(row)
    await db.flush()
    return True


async def sync_report_sources(db: AsyncSession, member: Member, report: Report) -> None:
    """Validate the selection before replacing canonical provenance."""
    desired, activities = await _resolve_report_source_refs(db, member, report)
    rows = _source_rows(report.id, desired)
    await _build_normalized_sources(db, member, report, rows, resolved_activities=activities)
    await db.execute(delete(ReportSource).where(ReportSource.report_id == report.id))
    for row in rows:
        db.add(row)
    await db.flush()


def selected_sources(content: dict[str, Any]) -> list[tuple[str, UUID, UUID | None]]:
    """Read selection identities only; display text is never evidence."""
    raw = content.get("activities", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise HTTPException(422, "report_sources_invalid")
    selected = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("source"), str):
            raise HTTPException(422, "report_sources_invalid")
        included = item.get("included", False)
        if not isinstance(included, bool):
            raise HTTPException(422, "report_source_included_invalid")
        if not included:
            continue
        kind = "activity" if item["source"] == "캘린더" else _SOURCES.get(item["source"])
        if kind is None:
            continue
        try:
            source_id = UUID(str(item["refId"]))
            submission_id = (
                UUID(str(item["sourceSubmissionId"]))
                if item.get("sourceSubmissionId") is not None
                else None
            )
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, "report_source_id_invalid") from error
        if kind == "activity" and submission_id is not None:
            raise HTTPException(422, "report_source_kind_invalid")
        selected.append((kind, source_id, submission_id))
    if len(selected) > SOURCE_REPORT_LIMIT:
        raise HTTPException(422, "report_source_limit_exceeded")
    if len({(kind, source_id) for kind, source_id, _ in selected}) != len(selected):
        raise HTTPException(422, "report_source_duplicate")
    return selected


async def selection_changed(db: AsyncSession, report: Report, content: dict[str, Any]) -> bool:
    """Omitted selections and body-only edits keep their historical submission IDs."""
    if "activities" not in content:
        return False
    selected = selected_sources(content)
    current = await current_source_ref_snapshot(db, report.id)
    existing = {}
    for ref in current:
        if ref["source_activity_id"]:
            existing[("activity", UUID(ref["source_activity_id"]))] = None
        else:
            existing[(_CHILD_KIND[report.report_kind], UUID(ref["source_report_id"]))] = UUID(
                ref["source_report_submission_id"]
            )
    return {(kind, source_id) for kind, source_id, _ in selected} != set(existing) or any(
        submission_id is not None and submission_id != existing.get((kind, source_id))
        for kind, source_id, submission_id in selected
    )


async def _resolve_report_source_refs(
    db: AsyncSession,
    member: Member,
    report: Report,
) -> tuple[list[tuple[UUID | None, UUID | None]], list[dict[str, Any]]]:
    """Resolve the selected current child submissions through the server's access boundary."""
    if not member.active or member.role_code not in {"member", "manager"}:
        raise HTTPException(403, "member_not_allowed")
    if report.team_id != member.team_id:
        raise HTTPException(404, "report_not_found")
    if report.author_member_id != member.id:
        raise HTTPException(403, "report_not_owned")
    if report.report_kind not in _CHILD_KIND:
        raise HTTPException(422, "report_source_kind_invalid")
    if report.report_kind != "daily" and (
        report.period_start is None
        or report.period_end is None
        or report.period_end < report.period_start
    ):
        raise HTTPException(422, "report_source_period_invalid")
    selected = selected_sources(report.content)
    report_ids, activity_ids = [], []
    for kind, source_id, _ in selected:
        if kind != "activity" and kind != _CHILD_KIND[report.report_kind]:
            raise HTTPException(422, "report_source_kind_invalid")
        if kind != "activity" and source_id == report.id:
            raise HTTPException(422, "report_source_self_reference")
        (activity_ids if kind == "activity" else report_ids).append(source_id)
    expected_submissions = {source_id: submission_id for _, source_id, submission_id in selected}

    activities = await _source_activities(db, member, report, activity_ids)

    source_submissions: dict[UUID, UUID] = {}
    if report_ids:
        expected_kind = _CHILD_KIND.get(report.report_kind)
        author, recipient = aliased(Member), aliased(Member)
        conditions = [
            Report.id.in_(report_ids),
            Report.team_id == member.team_id,
            Report.report_kind == expected_kind,
            author.team_id == member.team_id,
            author.active.is_(True),
            author.role_code.in_(("member", "manager")),
            or_(Report.recipient_member_id.is_(None), recipient.team_id == member.team_id),
        ]
        if member.role_code == "member":
            conditions.append(Report.author_member_id == member.id)
        rows = list(
            (
                await db.execute(
                    select(Report)
                    .join(author, author.id == Report.author_member_id)
                    .outerjoin(recipient, recipient.id == Report.recipient_member_id)
                    .where(*conditions)
                    .order_by(Report.id)
                    .with_for_update(of=Report)
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
            if source.status_code not in {"submitted", "approved"}:
                raise HTTPException(409, "report_source_not_finalized")
            if source.current_submission_id is None:
                await materialize_legacy_submission(db, source)
                assert source.current_submission_id is not None
            expected = expected_submissions[source_id]
            if expected is not None and expected != source.current_submission_id:
                raise HTTPException(409, "report_source_submission_changed")
            source_submissions[source_id] = source.current_submission_id

    desired: list[tuple[UUID | None, UUID | None]] = [
        (
            source_id if kind == "activity" else None,
            source_submissions[source_id] if kind != "activity" else None,
        )
        for kind, source_id, _ in selected
    ]
    return desired, activities


def _source_rows(
    report_id: UUID,
    refs: list[tuple[UUID | None, UUID | None]],
) -> list[ReportSource]:
    return [
        ReportSource(
            report_id=report_id,
            position=position,
            source_activity_id=activity_id,
            source_report_submission_id=submission_id,
        )
        for position, (activity_id, submission_id) in enumerate(refs)
    ]


def source_ref_snapshot(
    rows: list[ReportSource], submissions: dict[UUID, tuple[ReportSubmission, Report]] | None = None
) -> list[dict[str, Any]]:
    """Return the ordered, JSON-safe provenance identity retained after run redaction."""
    return jsonable_encoder(
        [
            {
                "position": row.position,
                "source_activity_id": row.source_activity_id,
                "source_report_submission_id": row.source_report_submission_id,
                **(
                    submission_ref(submissions[row.source_report_submission_id][0])
                    if submissions is not None and row.source_report_submission_id is not None
                    else {}
                ),
            }
            for row in sorted(rows, key=lambda item: item.position)
        ]
    )


async def current_source_ref_snapshot(
    db: AsyncSession,
    report_id: UUID,
) -> list[dict[str, Any]]:
    rows = await _report_source_rows(db, report_id)
    ids = [row.source_report_submission_id for row in rows if row.source_report_submission_id]
    submissions = await _source_submissions(db, ids)
    if set(ids) != set(submissions):
        raise HTTPException(404, "report_source_not_found")
    return source_ref_snapshot(rows, submissions)


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
        .with_for_update(of=(Report, ReportSubmission))
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
                "starts_at": activity.starts_at.astimezone(_SEOUL),
                "ends_at": activity.ends_at.astimezone(_SEOUL) if activity.ends_at else None,
                "completed_at": (
                    activity.completed_at.astimezone(_SEOUL) if activity.completed_at else None
                ),
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


def _check_snapshot_period(
    parent: Report, snapshot: dict[str, Any], *, legacy: bool = False
) -> None:
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
            if (
                not isinstance(child_start, date)
                or not isinstance(child_end, date)
                or child_end < child_start
            ):
                raise HTTPException(422, "report_source_period_invalid")
            valid = child_start <= end and child_end >= start
    if not valid:
        raise HTTPException(422, "report_source_outside_period")


def _snapshot_values(snapshot: dict[str, Any]) -> dict[str, Any]:
    structured = snapshot.get("structured_values")
    if not isinstance(structured, dict):
        raise HTTPException(422, "report_source_values_invalid")
    body = snapshot.get("body")
    if body is None:
        return {}
    if not isinstance(body, str):
        raise HTTPException(422, "report_source_content_invalid")
    return {"body": body}


async def _build_normalized_sources(
    db: AsyncSession,
    member: Member,
    report: Report,
    rows: list[ReportSource],
    *,
    resolved_activities: list[dict[str, Any]] | None = None,
    legacy: bool = False,
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

    activities = (
        resolved_activities
        if resolved_activities is not None
        else await _source_activities(db, member, report, activity_ids)
    )
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
        provenance = submission_ref(submission)
        if snapshot.get("report_kind") != _CHILD_KIND.get(report.report_kind):
            raise HTTPException(422, "report_source_kind_invalid")
        _check_snapshot_period(report, snapshot, legacy=legacy)
        if not legacy:
            if source.report_kind != snapshot["report_kind"]:
                raise HTTPException(422, "report_source_kind_invalid")
            if source.status_code not in {"submitted", "approved"}:
                raise HTTPException(409, "report_source_not_finalized")
            if source.current_submission_id != submission.id:
                raise HTTPException(409, "report_source_submission_changed")
            author = await db.get(Member, source.author_member_id)
            recipient = (
                await db.get(Member, source.recipient_member_id)
                if source.recipient_member_id
                else None
            )
            if (
                author is None
                or author.team_id != member.team_id
                or not author.active
                or author.role_code not in {"member", "manager"}
                or (
                    source.recipient_member_id is not None
                    and (recipient is None or recipient.team_id != member.team_id)
                )
            ):
                raise HTTPException(404, "report_not_found")

        if not legacy and any(
            snapshot.get(key) != (str(value) if value is not None else None)
            for key, value in (
                ("report_id", source.id),
                ("team_id", source.team_id),
                ("author_member_id", source.author_member_id),
                ("recipient_member_id", source.recipient_member_id),
                ("source_activity_id", source.source_activity_id),
            )
        ):
            raise HTTPException(422, "report_source_identity_invalid")

        source_activity_id = snapshot.get("source_activity_id")
        if snapshot["report_kind"] == "meeting":
            deals = snapshot.get("deals")
            if not isinstance(deals, list):
                raise HTTPException(422, "report_source_deal_sections_required")
            if not deals and not any(
                isinstance(body, str) and body.strip()
                for body in (snapshot.get("common_body"), snapshot.get("unassigned_body"))
            ):
                raise HTTPException(422, "report_source_content_invalid")
            deal_ids = set()
            for deal in deals:
                if not isinstance(deal, dict):
                    raise HTTPException(422, "report_source_content_invalid")
                if not legacy:
                    try:
                        deal_id = UUID(str(deal["sales_deal_id"]))
                    except (KeyError, TypeError, ValueError) as error:
                        raise HTTPException(422, "report_source_content_invalid") from error
                    if deal_id in deal_ids:
                        raise HTTPException(422, "report_source_duplicate")
                    deal_ids.add(deal_id)
                    if not isinstance(deal.get("body"), str) or not deal["body"].strip():
                        raise HTTPException(422, "report_source_content_invalid")
                output.append(
                    {
                        "id": source.id,
                        "submission_id": submission.id,
                        **({"report_kind": "meeting", **provenance} if not legacy else {}),
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
                    **({"submission_id": submission.id, **provenance} if not legacy else {}),
                    "common_report": _shared_body(snapshot.get("common_body")),
                    "unassigned_report": _shared_body(snapshot.get("unassigned_body")),
                }
                previous = meetings.get(activity_id)
                if previous is not None and not legacy:
                    raise HTTPException(422, "report_source_duplicate")
                if previous is not None and previous != meeting:
                    raise HTTPException(409, "report_source_shared_conflict")
                meetings[activity_id] = meeting
        else:
            values = _snapshot_values(snapshot)
            if not isinstance(values.get("body"), str) or not values["body"].strip():
                raise HTTPException(422, "report_source_content_invalid")
            output.append(
                {
                    "id": source.id,
                    "submission_id": submission.id,
                    "report_kind": snapshot["report_kind"],
                    **provenance,
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


async def freeze_report_sources(
    db: AsyncSession,
    member: Member,
    report: Report,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Freeze selected child submissions; never read navigation bodies or grandchildren."""
    desired, activities = await _resolve_report_source_refs(db, member, report)
    rows = _source_rows(report.id, desired)
    sources = await _build_normalized_sources(
        db,
        member,
        report,
        rows,
        resolved_activities=activities,
    )
    submissions = await _source_submissions(
        db, [submission_id for _, submission_id in desired if submission_id is not None]
    )
    return sources, source_ref_snapshot(rows, submissions)


async def build_report_sources(
    db: AsyncSession,
    member: Member,
    report: Report,
) -> dict[str, Any]:
    """기존 보고서 재생성에도 선택된 하위 제출본 검증을 재사용한다."""
    return (await freeze_report_sources(db, member, report))[0]
