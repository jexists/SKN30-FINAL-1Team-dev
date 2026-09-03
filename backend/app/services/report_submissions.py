"""Human-approved report revisions.

The mutable ``report`` aggregate remains the editing surface.  Every submit copies only
domain output into an immutable ``report_submission`` row so reviews and parent reports
never depend on a draft that may later change.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import Report, ReportDeal, ReportSource, ReportSubmission
from app.models.workspace import Member

SUBMISSION_SCHEMA_VERSION = "report_submission.v1"

# Template field IDs are user-controlled.  Raw generation inputs and machine-only values must
# not cross the human-approval boundary into immutable submissions, regardless of spelling.
_RESERVED_FIELD_IDS = {
    "activity",
    "activities",
    "attachment",
    "attachments",
    "ai_evidence",
    "ai_generated_at",
    "ai_values",
    "context_lookups",
    "crm_context",
    "deal_assessment",
    "input_snapshot",
    "meeting_analysis",
    "meeting_shared",
    "ml",
    "ml_result",
    "output_snapshot",
    "raw_payload",
    "raw_transcript",
    "request_snapshot",
    "source_snapshot",
    "transcript",
}
_RESERVED_FIELD_TOKENS = {
    "".join(character for character in key.casefold() if character.isalnum())
    for key in _RESERVED_FIELD_IDS
}


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def is_reserved_submission_field(value: Any) -> bool:
    """Use one normalized denylist at both submission-write and historical-read boundaries."""
    if not isinstance(value, str):
        return False
    token = "".join(character for character in value.casefold() if character.isalnum())
    return token in _RESERVED_FIELD_TOKENS


def _approved_structured_values(value: Any) -> dict[str, Any]:
    """Reject raw-payload keys anywhere inside a human-approved structured value."""

    def validate(item: Any) -> None:
        if isinstance(item, dict):
            if any(is_reserved_submission_field(key) for key in item):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="report_submission_reserved_field",
                )
            for nested in item.values():
                validate(nested)
        elif isinstance(item, list):
            for nested in item:
                validate(nested)

    output = _mapping(value)
    validate(output)
    return output


def _content_values(content: Any) -> dict[str, Any]:
    values = _mapping(content).get("values")
    return _mapping(values)


def effective_report_fields(report: Report) -> dict[str, Any]:
    """Return normalized human-approved fields while rejecting reserved legacy data."""
    content = _mapping(report.content)
    values = _content_values(content)
    _approved_structured_values(getattr(report, "structured_values", None))
    _approved_structured_values(values)
    return {
        "title": _text(getattr(report, "title", None)) or _text(content.get("title")),
        "body": _text(getattr(report, "body", None)),
        "common_body": _text(getattr(report, "common_body", None)),
        "unassigned_body": _text(getattr(report, "unassigned_body", None)),
        "structured_values": {},
    }


def effective_deal_fields(section: ReportDeal) -> dict[str, Any]:
    """Return the human-approved deal body while rejecting reserved legacy data."""
    content = _mapping(section.content)
    values = _content_values(content)
    _approved_structured_values(getattr(section, "structured_values", None))
    _approved_structured_values(values)
    return {
        "title": _text(getattr(section, "title", None)) or _text(content.get("title")),
        "body": _text(getattr(section, "body", None)),
        "structured_values": {},
    }


def build_submission_snapshot(
    report: Report,
    sections: list[ReportDeal],
    sources: list[ReportSource] | None = None,
) -> dict[str, Any]:
    """Build the canonical, transcript-free payload hashed and stored at submit time."""
    normalized = effective_report_fields(report)
    template_snapshot = _approved_structured_values(report.template_snapshot)
    ordered = sorted(
        sections,
        key=lambda item: (
            getattr(item, "position", None) is None,
            getattr(item, "position", None) or 0,
            str(item.sales_deal_id),
        ),
    )
    deals = []
    for index, section in enumerate(ordered):
        fields = effective_deal_fields(section)
        deals.append(
            {
                "sales_deal_id": section.sales_deal_id,
                "position": getattr(section, "position", None)
                if getattr(section, "position", None) is not None
                else index,
                "deal_snapshot": _mapping(section.deal_snapshot),
                "deal_no_snapshot": _text(getattr(section, "deal_no_snapshot", None)),
                "deal_title_snapshot": _text(getattr(section, "deal_title_snapshot", None)),
                **fields,
            }
        )
    transcript = _text(report.transcript)
    snapshot = {
        "schema_version": SUBMISSION_SCHEMA_VERSION,
        "report_id": report.id,
        "team_id": report.team_id,
        "author_member_id": report.author_member_id,
        "recipient_member_id": report.recipient_member_id,
        "source_activity_id": report.source_activity_id,
        "customer_company_id": getattr(report, "customer_company_id", None),
        "report_kind": report.report_kind,
        "report_date": report.report_date,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "template_snapshot": template_snapshot,
        **normalized,
        "deals": deals,
        "source_refs": [
            {
                "position": source.position,
                "source_activity_id": source.source_activity_id,
                "source_report_submission_id": source.source_report_submission_id,
            }
            for source in sorted(sources or [], key=lambda item: item.position)
        ],
        # Raw transcripts remain on the mutable report under the existing retention policy.
        "transcript_sha256": (
            hashlib.sha256(transcript.encode("utf-8")).hexdigest() if transcript else None
        ),
    }
    return jsonable_encoder(snapshot)


def snapshot_sha256(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_submission_content(report: Report, sections: list[ReportDeal]) -> None:
    """Reject a meeting section without a human-approved body."""
    if report.report_kind != "meeting":
        return
    if not sections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="deal_sections_required",
        )
    if any(effective_deal_fields(section)["body"] is None for section in sections):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="report_deal_body_required",
        )


async def create_submission(
    db: AsyncSession,
    report: Report,
    member: Member,
    sections: list[ReportDeal],
    *,
    submitted_by_member_id: UUID | None = None,
    agent_run_id: UUID | None = None,
    idempotency_key: UUID | None = None,
    request_hash: str | None = None,
) -> ReportSubmission:
    """Insert the next immutable revision.  The caller owns the surrounding transaction."""
    validate_submission_content(report, sections)
    result = await db.execute(
        select(func.coalesce(func.max(ReportSubmission.revision_no), 0)).where(
            ReportSubmission.report_id == report.id
        )
    )
    revision_no = int(result.scalar_one()) + 1
    source_rows = list(
        (
            await db.execute(
                select(ReportSource)
                .where(ReportSource.report_id == report.id)
                .order_by(ReportSource.position)
            )
        )
        .scalars()
        .all()
    )
    snapshot = build_submission_snapshot(report, sections, source_rows)
    submission = ReportSubmission(
        id=uuid4(),
        report_id=report.id,
        revision_no=revision_no,
        report_version=report.version,
        team_id=report.team_id,
        submitted_by_member_id=submitted_by_member_id or member.id,
        agent_run_id=agent_run_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        snapshot=snapshot,
        snapshot_sha256=snapshot_sha256(snapshot),
        review_status="pending",
        reviewed_by_member_id=None,
        reviewed_at=None,
        review_note=None,
    )
    db.add(submission)
    # The report's composite FK may only point at a row that has already been inserted.
    await db.flush()
    return submission


async def review_current_submission(
    db: AsyncSession,
    report: Report,
    member: Member,
    *,
    expected_submission_id: UUID,
    approved: bool,
    note: str | None,
) -> ReportSubmission:
    """Lock and review exactly the revision the manager saw."""
    if report.current_submission_id != expected_submission_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="report_submission_conflict",
        )
    result = await db.execute(
        select(ReportSubmission)
        .where(
            ReportSubmission.id == expected_submission_id,
            ReportSubmission.report_id == report.id,
            ReportSubmission.team_id == member.team_id,
        )
        .with_for_update(of=ReportSubmission)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="report_submission_conflict",
        )
    if submission.review_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="report_submission_already_reviewed",
        )
    now = datetime.now(UTC)
    submission.review_status = "approved" if approved else "changes_requested"
    submission.reviewed_by_member_id = member.id
    submission.reviewed_at = now
    submission.review_note = None if approved else note
    return submission
