import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import Text, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.activities import _activity_row
from app.api.deps import CurrentMember, DbSession, active_member, owner_scope
from app.api.sales_deals import _sales_deal_row
from app.models.agent import AgentRun
from app.models.content import Report, ReportActivity, ReportDeal, ReportSubmission
from app.models.crm import Activity
from app.models.workspace import Member
from app.schemas.reports import (
    REVIEW_DECISION_STATUS,
    ReportActivityRead,
    ReportDealRead,
    ReportDealWrite,
    ReportFilterOptionParams,
    ReportFilterOptions,
    ReportFinalize,
    ReportPage,
    ReportPageParams,
    ReportRead,
    ReportReview,
)
from app.services import agent_runs as agent_run_service
from app.services import contract_next_meeting_pipeline, report_sources, report_submissions

router = APIRouter(tags=["reports"])

_SEOUL = ZoneInfo("Asia/Seoul")
_author = aliased(Member)
_recipient = aliased(Member)

# 팀원이 고칠 수 있는 상태. 팀장이 수정 요청하면(유스케이스 RPT-004) 다시 편집·제출한다.
_EDITABLE_STATUSES = ("draft", "changes_requested")
_MEETING_UNIQUE_INDEX = "report_source_activity_meeting_key"
_REPORT_UNIQUE_CONSTRAINTS = {
    _MEETING_UNIQUE_INDEX: "meeting_report_exists",
    "report_daily_author_date_key": "report_exists",
    "report_period_author_range_key": "report_exists",
    "report_deal_position_key": "duplicate_deal_positions",
}
_SERVER_OWNED_CONTENT_KEYS = ("ai_values", "ai_evidence", "ai_generated_at", "meeting_shared")


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _seoul(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(_SEOUL)


def _report_version(report: Report) -> int:
    # Existing rows are backfilled to 1 by the migration.  The fallback keeps mocked rows and
    # a rolling deploy readable while the migration is applied.
    return int(getattr(report, "version", None) or 1)


def _require_version(report: Report, expected_version: int) -> None:
    if _report_version(report) != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="report_version_conflict",
        )


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(Report)
        .join(_author, Report.author_member_id == _author.id)
        .outerjoin(_recipient, Report.recipient_member_id == _recipient.id)
    )


def _scope(member: Member, author_ids: tuple[UUID, ...] | None = None):
    conditions = [
        Report.team_id == member.team_id,
        _author.team_id == member.team_id,
        _author.active.is_(True),
        _author.role_code.in_(("member", "manager")),
        or_(
            Report.recipient_member_id.is_(None),
            _recipient.team_id == member.team_id,
        ),
    ]
    if member.role_code == "member":
        conditions.append(Report.author_member_id == member.id)
    elif author_ids is not None:
        conditions.append(Report.author_member_id.in_(author_ids))
    return conditions


def _require_manager(member: Member) -> None:
    """보고서 검토는 팀장이 한다. notices._require_manager 와 같은 코드를 쓴다."""
    if member.role_code != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager_required")


def _read_entities():
    return (Report, _author.display_name, _recipient.display_name)


# 보고 대상은 결재선을 지정했으면 그 사람 이름, 아니면 작성 화면에 적어 둔 글자다.
# 화면이 둘을 이 순서로 골라 보여 주므로 거를 때도 같은 값을 봐야 한다.
def _approver_expr():
    return func.coalesce(_recipient.display_name, Report.content["approver"].astext)


def _hospital_expr():
    return Report.content["hospital"].astext


def _dict(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _text(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _legacy_values(content) -> dict:
    return _dict(_dict(content).get("values"))


def _legacy_shared_body(content, key: str) -> str | None:
    shared = _dict(_dict(content).get("meeting_shared"))
    return _text(_dict(shared.get(key)).get("body"))


def _normalized_report_values(
    content: dict,
    *,
    title=None,
    body=None,
    common_body=None,
    unassigned_body=None,
    structured_values=None,
) -> dict:
    """Derive normalized columns from explicit fields, then legacy JSON."""
    values = _legacy_values(content)
    structured = _dict(structured_values)
    if structured_values is None:
        structured = {key: value for key, value in values.items() if key != "body"}
    return {
        "title": _text(title) or _text(content.get("title")),
        "body": _text(body) or _text(values.get("body")) or _text(content.get("body")),
        "common_body": _text(common_body) or _legacy_shared_body(content, "common_report"),
        "unassigned_body": _text(unassigned_body)
        or _legacy_shared_body(content, "unassigned_report"),
        "structured_values": structured,
    }


def _sync_legacy_report_content(
    content: dict,
    normalized: dict,
    *,
    sync_title: bool,
    sync_body: bool,
    sync_common: bool,
    sync_unassigned: bool,
    sync_structured: bool,
) -> dict:
    """Keep old UI readers working while normalized columns become canonical."""
    output = dict(content)
    if sync_title:
        if normalized["title"] is None:
            output.pop("title", None)
        else:
            output["title"] = normalized["title"]
    if sync_body or sync_structured:
        values = (
            dict(normalized["structured_values"]) if sync_structured else _legacy_values(output)
        )
        if normalized["body"] is None:
            values.pop("body", None)
        else:
            values["body"] = normalized["body"]
        output["values"] = values
    if sync_common or sync_unassigned:
        shared = _dict(output.get("meeting_shared"))
        for should_sync, field, key in (
            (sync_common, "common_body", "common_report"),
            (sync_unassigned, "unassigned_body", "unassigned_report"),
        ):
            if not should_sync:
                continue
            body_value = normalized[field]
            if body_value is None:
                shared.pop(key, None)
            else:
                item = _dict(shared.get(key))
                item["body"] = body_value
                shared[key] = item
        if shared:
            output["meeting_shared"] = shared
        else:
            output.pop("meeting_shared", None)
    return output


def _report_read(
    report: Report,
    author_display_name: str,
    recipient_display_name: str | None,
    activities: list[ReportActivityRead],
    deal_sections: list[ReportDealRead],
) -> ReportRead:
    return ReportRead(
        id=report.id,
        team_id=report.team_id,
        author_member_id=report.author_member_id,
        author_display_name=author_display_name,
        recipient_member_id=report.recipient_member_id,
        recipient_display_name=recipient_display_name,
        source_activity_id=report.source_activity_id,
        sales_deal_id=report.sales_deal_id,
        deal_sections=deal_sections,
        report_kind=report.report_kind,
        report_date=report.report_date,
        period_start=report.period_start,
        period_end=report.period_end,
        status_code=report.status_code,
        version=_report_version(report),
        generation_input_version=int(
            getattr(report, "generation_input_version", None) or _report_version(report)
        ),
        current_submission_id=getattr(report, "current_submission_id", None),
        template_snapshot=report.template_snapshot,
        content=report.content,
        customer_company_id=getattr(report, "customer_company_id", None),
        title=getattr(report, "title", None),
        body=getattr(report, "body", None),
        common_body=getattr(report, "common_body", None),
        unassigned_body=getattr(report, "unassigned_body", None),
        structured_values=_dict(getattr(report, "structured_values", None)),
        transcript=report.transcript,
        source_snapshot=report.source_snapshot,
        ai_evidence=report.ai_evidence,
        note=report.note,
        review_note=report.review_note,
        reviewed_by_member_id=report.reviewed_by_member_id,
        reviewed_at=_seoul(report.reviewed_at),
        activities=activities,
        created_at=_seoul(report.created_at),
        updated_at=_seoul(report.updated_at),
    )


async def _visible_recipient(db: AsyncSession, member: Member, recipient_id: UUID) -> Member:
    result = await db.execute(
        select(Member).where(
            Member.id == recipient_id,
            Member.team_id == member.team_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    recipient = result.scalar_one_or_none()
    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="recipient_not_found",
        )
    return recipient


async def _validate_meeting_sales_deal_ids(
    db: AsyncSession,
    member: Member,
    source_activity_id: UUID,
    sales_deal_ids: list[UUID],
) -> UUID:
    """Validate one meeting once, then each selected deal, and return its company."""
    activity = await _activity_row(db, member, source_activity_id)
    meeting_company_id = activity[3]
    if meeting_company_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sales_deal_not_found",
        )
    for sales_deal_id in sales_deal_ids:
        deal = await _sales_deal_row(db, member, sales_deal_id)
        if meeting_company_id != deal[0].customer_company_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="sales_deal_not_found",
            )
    return meeting_company_id


async def _validate_meeting_deals(
    db: AsyncSession,
    member: Member,
    source_activity_id: UUID,
    deal_sections: list[ReportDealWrite],
) -> UUID:
    return await _validate_meeting_sales_deal_ids(
        db,
        member,
        source_activity_id,
        [section.sales_deal_id for section in deal_sections],
    )


def _integrity_constraint(error: IntegrityError) -> str | None:
    original = getattr(error, "orig", None)
    cause = getattr(original, "__cause__", None)
    candidates = (original, cause, getattr(original, "diag", None), getattr(cause, "diag", None))
    return next(
        (
            constraint
            for candidate in candidates
            if (constraint := getattr(candidate, "constraint_name", None)) is not None
        ),
        None,
    )


async def _deal_sections_by_report_ids(
    db: AsyncSession,
    report_ids: list[UUID],
) -> dict[UUID, list[ReportDealRead]]:
    grouped: dict[UUID, list[ReportDealRead]] = {report_id: [] for report_id in report_ids}
    if not report_ids:
        return grouped
    result = await db.execute(
        select(ReportDeal)
        .where(ReportDeal.report_id.in_(report_ids))
        .order_by(
            ReportDeal.position.asc().nullslast(),
            ReportDeal.created_at,
            ReportDeal.sales_deal_id,
        )
    )
    for section in result.scalars().all():
        grouped[section.report_id].append(
            ReportDealRead(
                sales_deal_id=section.sales_deal_id,
                deal_snapshot=section.deal_snapshot,
                content=section.content,
                position=section.position,
                deal_no_snapshot=section.deal_no_snapshot,
                deal_title_snapshot=section.deal_title_snapshot,
                title=section.title,
                body=section.body,
                structured_values=_dict(section.structured_values),
                ai_evidence=section.ai_evidence,
                created_at=_seoul(section.created_at),
                updated_at=_seoul(section.updated_at),
            )
        )
    return grouped


def _section_content(
    incoming: dict,
    current: dict | None = None,
) -> dict:
    content = dict(incoming)
    for key in _SERVER_OWNED_CONTENT_KEYS:
        content.pop(key, None)
        if current is not None and key in current:
            content[key] = current[key]
    return content


def _normalized_section_payload(payload: ReportDealWrite, position: int) -> dict:
    content = _section_content(payload.content)
    values = _legacy_values(content)
    explicit = payload.model_fields_set
    title = payload.title if "title" in explicit else _text(content.get("title"))
    body = payload.body if "body" in explicit else _text(values.get("body"))
    structured = (
        dict(payload.structured_values)
        if "structured_values" in explicit
        else {key: value for key, value in values.items() if key != "body"}
    )
    if "title" in explicit:
        if title is None:
            content.pop("title", None)
        else:
            content["title"] = title
    if "body" in explicit or "structured_values" in explicit:
        legacy_values = dict(structured) if "structured_values" in explicit else values
        if body is None:
            legacy_values.pop("body", None)
        else:
            legacy_values["body"] = body
        content["values"] = legacy_values
    snapshot = payload.deal_snapshot.model_dump(mode="json")
    return {
        "position": payload.position if payload.position is not None else position,
        "deal_snapshot": snapshot,
        "deal_no_snapshot": payload.deal_snapshot.label,
        "deal_title_snapshot": _text(payload.deal_snapshot.note),
        "title": title,
        "body": body,
        "structured_values": structured,
        "content": content,
    }


async def _replace_report_deals(
    db: AsyncSession,
    report_id: UUID,
    deal_sections: list[ReportDealWrite],
    *,
    ai_evidence_by_deal: dict[UUID, dict | None] | None = None,
) -> tuple[bool, bool]:
    existing = {
        section.sales_deal_id: section
        for section in (
            await db.execute(select(ReportDeal).where(ReportDeal.report_id == report_id))
        )
        .scalars()
        .all()
    }
    normalized_sections = [
        (payload, _normalized_section_payload(payload, position))
        for position, payload in enumerate(deal_sections)
    ]
    incoming_ids = {section.sales_deal_id for section in deal_sections}
    deal_ids_changed = set(existing) != incoming_ids
    changed = False
    if removed := set(existing) - incoming_ids:
        await db.execute(
            delete(ReportDeal).where(
                ReportDeal.report_id == report_id,
                ReportDeal.sales_deal_id.in_(removed),
            )
        )
        changed = True

    # PostgreSQL의 position UNIQUE 인덱스는 행마다 즉시 검사한다. 0↔1처럼 서로 자리를
    # 바꾸는 경우만 기존 자리를 비운 뒤 최종 위치를 한 번에 채운다.
    position_rewrite_needed = any(
        payload.sales_deal_id in existing
        and existing[payload.sales_deal_id].position != normalized["position"]
        for payload, normalized in normalized_sections
    )
    if position_rewrite_needed:
        for sales_deal_id in incoming_ids & set(existing):
            existing[sales_deal_id].position = None
        await db.flush()

    now = datetime.now(UTC)
    for payload, normalized in normalized_sections:
        current = existing.get(payload.sales_deal_id)
        if current is None:
            db.add(
                ReportDeal(
                    report_id=report_id,
                    sales_deal_id=payload.sales_deal_id,
                    **normalized,
                    ai_evidence=(
                        ai_evidence_by_deal.get(payload.sales_deal_id)
                        if ai_evidence_by_deal is not None
                        else None
                    ),
                )
            )
            changed = True
            continue
        normalized["content"] = _section_content(normalized["content"], current.content)
        if ai_evidence_by_deal is not None:
            normalized["ai_evidence"] = ai_evidence_by_deal.get(payload.sales_deal_id)
        section_changed = any(
            getattr(current, field_name) != value for field_name, value in normalized.items()
        )
        if not section_changed:
            continue
        for field_name, value in normalized.items():
            setattr(current, field_name, value)
        current.updated_at = now
        changed = True
    return changed, deal_ids_changed


def _add_report_deals(
    db: AsyncSession,
    report_id: UUID,
    deal_sections: list[ReportDealWrite],
    *,
    ai_evidence_by_deal: dict[UUID, dict | None] | None = None,
) -> None:
    for position, payload in enumerate(deal_sections):
        db.add(
            ReportDeal(
                report_id=report_id,
                sales_deal_id=payload.sales_deal_id,
                **_normalized_section_payload(payload, position),
                ai_evidence=(
                    ai_evidence_by_deal.get(payload.sales_deal_id)
                    if ai_evidence_by_deal is not None
                    else None
                ),
            )
        )


async def _activities_by_report_ids(
    db: AsyncSession,
    report_ids: list[UUID],
) -> dict[UUID, list[ReportActivityRead]]:
    grouped: dict[UUID, list[ReportActivityRead]] = {report_id: [] for report_id in report_ids}
    if not report_ids:
        return grouped
    result = await db.execute(
        select(
            ReportActivity.report_id,
            Activity.id,
            Activity.title,
            Activity.starts_at,
        )
        .join(Activity, ReportActivity.activity_id == Activity.id)
        .where(ReportActivity.report_id.in_(report_ids))
        .order_by(Activity.starts_at, Activity.id)
    )
    for report_id, activity_id, title, starts_at in result.all():
        grouped[report_id].append(
            ReportActivityRead(
                activity_id=activity_id,
                title=title,
                starts_at=_seoul(starts_at),
            )
        )
    return grouped


async def _report_row(db: AsyncSession, member: Member, report_id: UUID):
    result = await db.execute(
        _joined_select(*_read_entities()).where(Report.id == report_id, *_scope(member))
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_not_found",
        )
    return row


async def _locked_report(db: AsyncSession, member: Member, report_id: UUID) -> Report:
    conditions = [
        Report.id == report_id,
        Report.team_id == member.team_id,
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(Report.author_member_id == member.id)
    result = await db.execute(
        select(Report)
        .join(Member, Report.author_member_id == Member.id)
        .where(*conditions)
        .with_for_update(of=Report)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_not_found",
        )
    # 보고서는 쓴 사람이 고치고 제출하고 지운다. 팀장도 남의 보고서를 대신 손대지 않는다.
    #
    # 팀원에게는 위 조건이 이미 본인 것만 남기므로 여기까지 오지 않는다. 팀장은 팀원의
    # 보고서를 목록에서 보고 있어, 없는 척(404)하지 않고 403 으로 이유를 말한다.
    if report.author_member_id != member.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="report_not_owned",
        )
    return report


async def _locked_report_for_review(db: AsyncSession, member: Member, report_id: UUID) -> Report:
    """팀장이 검토할 한 건을 잠가서 읽는다.

    _locked_report 는 쓰기를 작성자에게만 열어 주므로 여기서 쓸 수 없다. 검토는 남의
    보고서에 하는 일이라 스코프가 반대다. 대신 볼 수 있는 범위는 목록과 같아야 하므로
    조회 조건은 _scope 를 그대로 쓴다.
    """
    _require_manager(member)
    result = await db.execute(
        _joined_select(Report)
        .where(Report.id == report_id, *_scope(member))
        .with_for_update(of=Report)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="report_not_found",
        )
    # 자기가 쓴 보고서를 자기가 확정하지 않는다. 팀장도 자기 보고서는 남에게 낸다.
    if report.author_member_id == member.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="self_review_not_allowed",
        )
    return report


async def _own_activity_ids(
    db: AsyncSession,
    member: Member,
    activity_ids: list[UUID],
) -> tuple[UUID, ...]:
    """보고서에 묶을 일정이 모두 "내가 한 일"인지 확인한다.

    보고는 남이 한 일을 대신 적는 문서가 아니다. 팀장이라도 팀원의 일정에 보고서를
    달 수 없다.

    이 저장소가 쓰기 권한에 404 를 쓰는 까닭은 볼 수 없는 줄의 존재를 알리지 않기
    위해서인데, 팀장은 팀원의 일정을 이미 자기 목록에서 본다. 숨길 것이 없는 자리라
    없는 척하지 않고 403 으로 이유를 말한다. 다른 팀이거나 지워진 일정은 그보다 먼저
    404 로 끊으므로 남의 팀을 더듬어 볼 수는 없다.
    """
    if not activity_ids:
        return ()
    unique = tuple(dict.fromkeys(activity_ids))
    result = await db.execute(
        select(Activity.id, Activity.owner_member_id).where(
            Activity.id.in_(unique),
            Activity.team_id == member.team_id,
            Activity.deleted_at.is_(None),
        )
    )
    owners = {row[0]: row[1] for row in result.all()}
    if set(owners) != set(unique):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="activity_not_found",
        )
    if any(owner_id != member.id for owner_id in owners.values()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="activity_not_owned",
        )
    return unique


async def _linked_activity_ids(db: AsyncSession, report_id: UUID) -> set[UUID]:
    """이미 이 보고서에 묶여 있는 일정."""
    result = await db.execute(
        select(ReportActivity.activity_id).where(ReportActivity.report_id == report_id)
    )
    return set(result.scalars().all())


async def _replace_report_activities(
    db: AsyncSession,
    report_id: UUID,
    activity_ids: tuple[UUID, ...],
    *,
    current_ids: set[UUID] | None = None,
) -> bool:
    if current_ids is None:
        current_ids = await _linked_activity_ids(db, report_id)
    if current_ids == set(activity_ids):
        return False
    await db.execute(delete(ReportActivity).where(ReportActivity.report_id == report_id))
    for activity_id in activity_ids:
        db.add(ReportActivity(report_id=report_id, activity_id=activity_id))
    return True


async def _detail(db: AsyncSession, member: Member, report_id: UUID) -> ReportRead:
    row = await _report_row(db, member, report_id)
    activities = await _activities_by_report_ids(db, [report_id])
    report = row[0]
    deal_sections = (
        await _deal_sections_by_report_ids(db, [report_id])
        if report.report_kind == "meeting"
        else {report_id: []}
    )
    return _report_read(*row, activities[report_id], deal_sections[report_id])


@router.get("/report-filter-options", response_model=ReportFilterOptions)
async def list_report_filter_options(
    page: Annotated[ReportFilterOptionParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> ReportFilterOptions:
    author_ids = await owner_scope(db, member, page.author_member_id)
    scope = _scope(member, author_ids)

    async def distinct(expression) -> list[str]:
        result = await db.execute(
            _joined_select(expression)
            .where(*scope, expression.is_not(None), expression != "")
            .distinct()
            .order_by(expression)
        )
        return list(result.scalars().all())

    return ReportFilterOptions(
        approvers=await distinct(_approver_expr()),
        hospitals=await distinct(_hospital_expr()),
    )


@router.get("/reports", response_model=ReportPage)
async def list_reports(
    page: Annotated[ReportPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> ReportPage:
    author_ids = await owner_scope(db, member, page.author_member_id)
    scope = _scope(member, author_ids)
    if page.report_kind is not None:
        scope.append(Report.report_kind.in_(tuple(dict.fromkeys(page.report_kind))))
    if page.status_code is not None:
        scope.append(Report.status_code.in_(tuple(dict.fromkeys(page.status_code))))
    if page.start_date is not None:
        scope.append(Report.report_date >= page.start_date)
    if page.end_date is not None:
        scope.append(Report.report_date <= page.end_date)
    if page.source_activity_id is not None:
        scope.append(Report.source_activity_id.in_(tuple(dict.fromkeys(page.source_activity_id))))
    if page.sales_deal_id is not None:
        section_report_ids = select(ReportDeal.report_id).where(
            ReportDeal.sales_deal_id == page.sales_deal_id
        )
        # migration 전 레거시 행도 조회가 끊기지 않게 둔다.
        scope.append(
            or_(
                Report.sales_deal_id == page.sales_deal_id,
                Report.id.in_(section_report_ids),
            )
        )
    if page.approver is not None:
        scope.append(_approver_expr().in_(tuple(dict.fromkeys(page.approver))))
    if page.hospital is not None:
        scope.append(_hospital_expr().in_(tuple(dict.fromkeys(page.hospital))))
    if page.q is not None:
        pattern = _contains(page.q)
        matching_deal_reports = select(ReportDeal.report_id).where(
            or_(
                ReportDeal.title.ilike(pattern, escape="\\"),
                ReportDeal.body.ilike(pattern, escape="\\"),
                ReportDeal.content.cast(Text).ilike(pattern, escape="\\"),
            )
        )
        scope.append(
            or_(
                Report.note.ilike(pattern, escape="\\"),
                Report.transcript.ilike(pattern, escape="\\"),
                _author.display_name.ilike(pattern, escape="\\"),
                Report.title.ilike(pattern, escape="\\"),
                Report.body.ilike(pattern, escape="\\"),
                Report.common_body.ilike(pattern, escape="\\"),
                Report.unassigned_body.ilike(pattern, escape="\\"),
                # 보고 본문은 content 안에 있다. 여기를 빼면 제목도 고객사도 못 찾아
                # 검색이 사실상 메모 검색이 된다.
                Report.content.cast(Text).ilike(pattern, escape="\\"),
                Report.id.in_(matching_deal_reports),
            )
        )

    total_result = await db.execute(_joined_select(func.count(Report.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(*_read_entities())
        .where(*scope)
        .order_by(Report.report_date.desc(), Report.created_at.desc(), Report.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    rows = rows_result.all()
    activity_map = await _activities_by_report_ids(db, [row[0].id for row in rows])
    meeting_ids = [row[0].id for row in rows if row[0].report_kind == "meeting"]
    deal_map = await _deal_sections_by_report_ids(db, meeting_ids)
    items = [
        _report_read(*row, activity_map[row[0].id], deal_map.get(row[0].id, [])) for row in rows
    ]
    has_more = page.skip + len(items) < total
    return ReportPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/reports/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> ReportRead:
    return await _detail(db, member, report_id)


def _finalize_request_hash(payload: ReportFinalize) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json", exclude_unset=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _finalize_scope_key(payload: ReportFinalize) -> str:
    if payload.report_kind == "meeting":
        return f"meeting:{payload.source_activity_id}"
    if payload.report_kind == "daily":
        return f"daily:{payload.report_date.isoformat()}"
    assert payload.period_start is not None and payload.period_end is not None
    return (
        f"{payload.report_kind}:{payload.period_start.isoformat()}:{payload.period_end.isoformat()}"
    )


async def _finalize_run(
    db: AsyncSession,
    member: Member,
    payload: ReportFinalize,
) -> AgentRun | None:
    if payload.agent_run_id is None:
        return None
    run = (
        await db.execute(
            select(AgentRun)
            .where(
                AgentRun.id == payload.agent_run_id,
                AgentRun.team_id == member.team_id,
                AgentRun.requested_by_member_id == member.id,
            )
            .with_for_update(of=AgentRun)
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "agent_run_not_found")
    expected_code = "meeting_processing" if payload.report_kind == "meeting" else "report_writing"
    if (
        run.agent_code != expected_code
        or run.status_code not in {"completed", "partial"}
        or run.report_id is not None
        or run.scope_key != _finalize_scope_key(payload)
        or run.output_snapshot is None
        or run.payload_redacted_at is not None
        or run.payload_expires_at is None
        or run.payload_expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(409, "report_generation_not_usable")
    if payload.report_kind == "meeting":
        source = run.input_snapshot.get("source", {})
        if source.get("transcript") != payload.transcript or set(
            source.get("selected_deal_ids", [])
        ) != {str(section.sales_deal_id) for section in payload.deal_sections}:
            raise HTTPException(409, "report_generation_source_changed")
    return run


def _finalize_values(payload: ReportFinalize) -> tuple[dict, dict]:
    content = _section_content(payload.content)
    explicit = payload.model_fields_set
    normalized = _normalized_report_values(content)
    for field_name in ("title", "body", "common_body", "unassigned_body", "structured_values"):
        if field_name in explicit:
            normalized[field_name] = getattr(payload, field_name)
    content = _sync_legacy_report_content(
        content,
        normalized,
        sync_title="title" in explicit,
        sync_body="body" in explicit,
        sync_common="common_body" in explicit,
        sync_unassigned="unassigned_body" in explicit,
        sync_structured="structured_values" in explicit,
    )
    return content, normalized


async def _existing_finalize(
    db: AsyncSession,
    member: Member,
    idempotency_key: UUID,
    request_hash: str,
) -> ReportRead | None:
    submission = (
        await db.execute(
            select(ReportSubmission).where(
                ReportSubmission.submitted_by_member_id == member.id,
                ReportSubmission.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if submission is None:
        return None
    if submission.request_hash != request_hash:
        raise HTTPException(409, "idempotency_key_reused")
    return await _detail(db, member, submission.report_id)


async def _existing_finalize_after_rollback(
    db: AsyncSession,
    member_id: UUID,
    idempotency_key: UUID,
    request_hash: str,
) -> ReportRead | None:
    """Rollback으로 만료된 ORM 객체 대신 현재 활성 구성원을 다시 읽는다."""
    member = await active_member(db, member_id)
    if member is None:
        return None
    return await _existing_finalize(db, member, idempotency_key, request_hash)


@router.post("/reports/finalize", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def finalize_report(
    payload: ReportFinalize,
    response: Response,
    background: BackgroundTasks,
    member: CurrentMember,
    db: DbSession,
) -> ReportRead:
    """사람이 승인한 최종값과 불변 제출본을 한 트랜잭션에서 저장한다."""
    member_id = member.id
    request_hash = _finalize_request_hash(payload)
    if existing := await _existing_finalize(db, member, payload.idempotency_key, request_hash):
        response.headers["Location"] = f"/api/reports/{existing.id}"
        return existing

    try:
        run = await _finalize_run(db, member, payload)
        recipient = (
            None
            if payload.recipient_member_id is None
            else await _visible_recipient(db, member, payload.recipient_member_id)
        )
        if payload.source_activity_id is not None:
            await _own_activity_ids(db, member, [payload.source_activity_id])
        customer_company_id = None
        if payload.report_kind == "meeting":
            assert payload.source_activity_id is not None
            customer_company_id = await _validate_meeting_deals(
                db, member, payload.source_activity_id, payload.deal_sections
            )
        ai_evidence_by_deal = (
            agent_run_service.meeting_deal_evidence(
                run,
                [section.sales_deal_id for section in payload.deal_sections],
            )
            if run is not None and payload.report_kind == "meeting"
            else None
        )
        activity_ids = await _own_activity_ids(db, member, payload.activity_ids)
        content, normalized = _finalize_values(payload)
        now = datetime.now(UTC)

        if payload.report_id is None:
            report = Report(
                id=uuid4(),
                team_id=member.team_id,
                author_member_id=member.id,
                recipient_member_id=None if recipient is None else recipient.id,
                template_snapshot=payload.template_snapshot,
                source_activity_id=payload.source_activity_id,
                sales_deal_id=None,
                customer_company_id=customer_company_id,
                report_kind=payload.report_kind,
                report_date=payload.report_date,
                period_start=payload.period_start,
                period_end=payload.period_end,
                status_code="submitted",
                content=content,
                **normalized,
                transcript=payload.transcript,
                source_snapshot={"agent_run_id": str(run.id)} if run is not None else None,
                ai_evidence=dict(run.evidence or {}) if run is not None else None,
                version=1,
                generation_input_version=1,
                current_submission_id=None,
                note=payload.note,
                review_note=None,
                reviewed_by_member_id=None,
                reviewed_at=None,
                created_at=now,
                updated_at=now,
            )
            db.add(report)
            _add_report_deals(
                db,
                report.id,
                payload.deal_sections,
                ai_evidence_by_deal=ai_evidence_by_deal,
            )
            for activity_id in activity_ids:
                db.add(ReportActivity(report_id=report.id, activity_id=activity_id))
            await db.flush()
        else:
            report = await _locked_report(db, member, payload.report_id)
            assert payload.expected_version is not None and payload.expected_status_code is not None
            _require_version(report, payload.expected_version)
            if report.status_code != payload.expected_status_code:
                raise HTTPException(409, "invalid_state_transition")
            if (
                report.report_kind != payload.report_kind
                or report.source_activity_id != payload.source_activity_id
                or report.report_date != payload.report_date
                or report.period_start != payload.period_start
                or report.period_end != payload.period_end
            ):
                raise HTTPException(409, "report_identity_changed")
            if payload.report_kind == "meeting":
                await _replace_report_deals(
                    db,
                    report.id,
                    payload.deal_sections,
                    ai_evidence_by_deal=ai_evidence_by_deal,
                )
            await _replace_report_activities(db, report.id, activity_ids)
            report.recipient_member_id = None if recipient is None else recipient.id
            report.template_snapshot = payload.template_snapshot
            report.customer_company_id = customer_company_id
            report.report_date = payload.report_date
            report.period_start = payload.period_start
            report.period_end = payload.period_end
            report.status_code = "submitted"
            report.content = content
            for field_name, value in normalized.items():
                setattr(report, field_name, value)
            report.transcript = payload.transcript
            report.source_snapshot = {"agent_run_id": str(run.id)} if run is not None else None
            report.ai_evidence = dict(run.evidence or {}) if run is not None else None
            report.note = payload.note
            report.review_note = None
            report.reviewed_by_member_id = None
            report.reviewed_at = None
            report.version = _report_version(report) + 1
            report.updated_at = now
            await db.flush()

        if report.report_kind != "meeting":
            await report_sources.sync_report_sources_from_legacy_content(db, member, report)
        sections = list(
            (
                await db.execute(
                    select(ReportDeal)
                    .where(ReportDeal.report_id == report.id)
                    .order_by(ReportDeal.position.asc().nullslast(), ReportDeal.sales_deal_id)
                )
            )
            .scalars()
            .all()
        )
        submission = await report_submissions.create_submission(
            db,
            report,
            member,
            sections,
            agent_run_id=run.id if run is not None else None,
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
        )
        report.current_submission_id = submission.id
        sales_deal_ids = [section.sales_deal_id for section in sections]
        if run is not None:
            run.report_id = report.id
            agent_run_service.redact_payload(run, now=now)
        await db.flush()
        read = await _detail(db, member, report.id)
        await db.commit()
    except HTTPException as error:
        await db.rollback()
        if error.status_code == status.HTTP_409_CONFLICT:
            existing = await _existing_finalize_after_rollback(
                db, member_id, payload.idempotency_key, request_hash
            )
            if existing is not None:
                response.headers["Location"] = f"/api/reports/{existing.id}"
                return existing
        raise
    except IntegrityError as error:
        await db.rollback()
        existing = await _existing_finalize_after_rollback(
            db, member_id, payload.idempotency_key, request_hash
        )
        if existing is not None:
            response.headers["Location"] = f"/api/reports/{existing.id}"
            return existing
        constraint = _integrity_constraint(error)
        if constraint in _REPORT_UNIQUE_CONSTRAINTS:
            raise HTTPException(409, _REPORT_UNIQUE_CONSTRAINTS[constraint]) from error
        raise
    except Exception:
        await db.rollback()
        raise

    response.headers["Location"] = f"/api/reports/{read.id}"
    for sales_deal_id in sales_deal_ids:
        contract_next_meeting_pipeline.queue(
            background,
            sales_deal_id,
            {"report_id": str(read.id), "sales_deal_id": str(sales_deal_id)},
        )
    return read


@router.post("/reports/{report_id}/review", response_model=ReportRead)
async def review_report(
    report_id: UUID,
    payload: ReportReview,
    member: CurrentMember,
    db: DbSession,
) -> ReportRead:
    """팀장이 제출된 보고서를 확정하거나 반려한다(유스케이스 RPT-004).

    반려는 changes_requested 로 가며 팀원이 고쳐서 다시 제출할 수 있다.
    """
    try:
        report = await _locked_report_for_review(db, member, report_id)
        if report.status_code != payload.expected_status_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )
        expected_submission_id = payload.expected_submission_id
        if report.current_submission_id is None:
            if expected_submission_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="report_submission_conflict",
                )
            submission = await report_sources.materialize_legacy_submission(db, report)
            expected_submission_id = submission.id
        elif expected_submission_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="report_submission_conflict",
            )
        assert expected_submission_id is not None
        submission = await report_submissions.review_current_submission(
            db,
            report,
            member,
            expected_submission_id=expected_submission_id,
            approved=payload.decision == "approve",
            note=payload.reason,
        )
        report.status_code = REVIEW_DECISION_STATUS[payload.decision]
        # 확정하면 지난 반려 사유를 남겨 두지 않는다. 고친 보고서에 옛 지적이 붙어 있으면
        # 무엇이 남은 문제인지 알 수 없다. 확정 요청에 reason 이 실려 와도 비운다.
        # 작성자의 note 는 건드리지 않는다.
        report.review_note = payload.reason if payload.decision == "reject" else None
        report.reviewed_by_member_id = member.id
        report.reviewed_at = submission.reviewed_at
        report.version = _report_version(report) + 1
        report.updated_at = datetime.now(UTC)
        await db.flush()
        read = await _detail(db, member, report_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    try:
        report = await _locked_report(db, member, report_id)
        if report.status_code not in _EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="report_not_editable",
            )
        if report.current_submission_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="report_has_submission_history",
            )
        # report 에는 deleted_at 이 없다. 묶인 일정은 report_activity 의 FK CASCADE 가 지운다.
        await db.delete(report)
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
