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
from app.api.deps import CurrentMember, DbSession, owner_scope
from app.api.sales_deals import _sales_deal_row
from app.models.content import Report, ReportActivity, ReportDeal
from app.models.crm import Activity
from app.models.workspace import Member
from app.schemas.reports import (
    ReportActivityRead,
    ReportCreate,
    ReportDealRead,
    ReportDealWrite,
    ReportFilterOptionParams,
    ReportFilterOptions,
    ReportPage,
    ReportPageParams,
    ReportPatch,
    ReportRead,
    ReportSubmit,
)
from app.services import contract_next_meeting_pipeline

router = APIRouter(tags=["reports"])

_SEOUL = ZoneInfo("Asia/Seoul")
_author = aliased(Member)
_recipient = aliased(Member)

# 팀원이 고칠 수 있는 상태. 팀장이 수정 요청하면(유스케이스 RPT-004) 다시 편집·제출한다.
_EDITABLE_STATUSES = ("draft", "changes_requested")
_INITIAL_STATUS = "draft"
_MEETING_UNIQUE_INDEX = "report_source_activity_meeting_key"
_SERVER_OWNED_CONTENT_KEYS = ("ai_values", "ai_evidence", "ai_generated_at", "meeting_shared")


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _seoul(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(_SEOUL)


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


def _read_entities():
    return (Report, _author.display_name, _recipient.display_name)


# 보고 대상은 결재선을 지정했으면 그 사람 이름, 아니면 작성 화면에 적어 둔 글자다.
# 화면이 둘을 이 순서로 골라 보여 주므로 거를 때도 같은 값을 봐야 한다.
def _approver_expr():
    return func.coalesce(_recipient.display_name, Report.content["approver"].astext)


def _hospital_expr():
    return Report.content["hospital"].astext


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
        template_snapshot=report.template_snapshot,
        content=report.content,
        transcript=report.transcript,
        source_snapshot=report.source_snapshot,
        ai_evidence=report.ai_evidence,
        note=report.note,
        reviewed_by_member_id=report.reviewed_by_member_id,
        reviewed_at=_seoul(report.reviewed_at),
        activities=activities,
        created_at=_seoul(report.created_at),
        updated_at=_seoul(report.updated_at),
    )


async def _visible_activity_ids(
    db: AsyncSession,
    member: Member,
    activity_ids: list[UUID],
) -> tuple[UUID, ...]:
    """보고서에 묶을 일정이 모두 같은 팀의 접근 가능한 일정인지 확인한다."""
    if not activity_ids:
        return ()
    unique = tuple(dict.fromkeys(activity_ids))
    conditions = [
        Activity.id.in_(unique),
        Activity.team_id == member.team_id,
        Activity.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(Activity.owner_member_id == member.id)
    result = await db.execute(select(Activity.id).where(*conditions))
    if set(result.scalars().all()) != set(unique):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="activity_not_found",
        )
    return unique


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


async def _validate_meeting_deal(
    db: AsyncSession,
    member: Member,
    source_activity_id: UUID,
    sales_deal_id: UUID,
) -> None:
    """선택한 딜이 접근 가능하고 미팅 고객사와 같은 고객사인지 확인한다."""
    # 두 조회는 각 원본 API와 같은 팀·담당자·활성 상태 스코프를 그대로 쓴다.
    activity = await _activity_row(db, member, source_activity_id)
    deal = await _sales_deal_row(db, member, sales_deal_id)
    meeting_company_id = activity[3]
    deal_company_id = deal[0].customer_company_id
    if meeting_company_id is None or meeting_company_id != deal_company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sales_deal_not_found",
        )


async def _validate_meeting_deals(
    db: AsyncSession,
    member: Member,
    source_activity_id: UUID,
    deal_sections: list[ReportDealWrite],
) -> None:
    for section in deal_sections:
        await _validate_meeting_deal(
            db,
            member,
            source_activity_id,
            section.sales_deal_id,
        )


def _duplicate_meeting(error: IntegrityError) -> bool:
    original = getattr(error, "orig", None)
    cause = getattr(original, "__cause__", None)
    candidates = (original, cause, getattr(original, "diag", None), getattr(cause, "diag", None))
    return any(
        getattr(candidate, "constraint_name", None) == _MEETING_UNIQUE_INDEX
        for candidate in candidates
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
        .order_by(ReportDeal.created_at, ReportDeal.sales_deal_id)
    )
    for section in result.scalars().all():
        grouped[section.report_id].append(
            ReportDealRead(
                sales_deal_id=section.sales_deal_id,
                deal_snapshot=section.deal_snapshot,
                content=section.content,
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


async def _replace_report_deals(
    db: AsyncSession,
    report_id: UUID,
    deal_sections: list[ReportDealWrite],
) -> None:
    existing = {
        section.sales_deal_id: section
        for section in (
            await db.execute(select(ReportDeal).where(ReportDeal.report_id == report_id))
        )
        .scalars()
        .all()
    }
    incoming_ids = {section.sales_deal_id for section in deal_sections}
    if removed := set(existing) - incoming_ids:
        await db.execute(
            delete(ReportDeal).where(
                ReportDeal.report_id == report_id,
                ReportDeal.sales_deal_id.in_(removed),
            )
        )
    now = datetime.now(UTC)
    for payload in deal_sections:
        current = existing.get(payload.sales_deal_id)
        if current is None:
            db.add(
                ReportDeal(
                    report_id=report_id,
                    sales_deal_id=payload.sales_deal_id,
                    deal_snapshot=payload.deal_snapshot.model_dump(mode="json"),
                    content=_section_content(payload.content),
                    ai_evidence=None,
                )
            )
            continue
        current.deal_snapshot = payload.deal_snapshot.model_dump(mode="json")
        current.content = _section_content(payload.content, current.content)
        current.updated_at = now


def _add_report_deals(
    db: AsyncSession,
    report_id: UUID,
    deal_sections: list[ReportDealWrite],
) -> None:
    for payload in deal_sections:
        db.add(
            ReportDeal(
                report_id=report_id,
                sales_deal_id=payload.sales_deal_id,
                deal_snapshot=payload.deal_snapshot.model_dump(mode="json"),
                content=_section_content(payload.content),
                ai_evidence=None,
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
) -> None:
    await db.execute(delete(ReportActivity).where(ReportActivity.report_id == report_id))
    for activity_id in activity_ids:
        db.add(ReportActivity(report_id=report_id, activity_id=activity_id))


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
        scope.append(Report.source_activity_id == page.source_activity_id)
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
        scope.append(
            or_(
                Report.note.ilike(pattern, escape="\\"),
                Report.transcript.ilike(pattern, escape="\\"),
                _author.display_name.ilike(pattern, escape="\\"),
                # 보고 본문은 content 안에 있다. 여기를 빼면 제목도 고객사도 못 찾아
                # 검색이 사실상 메모 검색이 된다.
                Report.content.cast(Text).ilike(pattern, escape="\\"),
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


@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> ReportRead:
    try:
        recipient = (
            None
            if payload.recipient_member_id is None
            else await _visible_recipient(db, member, payload.recipient_member_id)
        )
        if payload.source_activity_id is not None:
            await _own_activity_ids(db, member, [payload.source_activity_id])
        if payload.report_kind == "meeting":
            assert payload.source_activity_id is not None
            await _validate_meeting_deals(
                db,
                member,
                payload.source_activity_id,
                payload.deal_sections,
            )
        activity_ids = await _own_activity_ids(db, member, payload.activity_ids)

        report = Report(
            id=uuid4(),
            team_id=member.team_id,
            author_member_id=member.id,
            recipient_member_id=None if recipient is None else recipient.id,
            template_snapshot=payload.template_snapshot,
            source_activity_id=payload.source_activity_id,
            # 신규 미팅 보고서는 딜을 자식 섹션에만 보관한다.
            sales_deal_id=None,
            report_kind=payload.report_kind,
            report_date=payload.report_date,
            period_start=payload.period_start,
            period_end=payload.period_end,
            # 작성은 언제나 draft 로 시작한다. 제출은 별도 endpoint 를 거친다.
            status_code=_INITIAL_STATUS,
            content={
                key: value for key, value in payload.content.items() if key != "meeting_shared"
            },
            transcript=payload.transcript,
            source_snapshot=None,
            ai_evidence=None,
            note=payload.note,
            reviewed_by_member_id=None,
            reviewed_at=None,
        )
        db.add(report)
        _add_report_deals(db, report.id, payload.deal_sections)
        for activity_id in activity_ids:
            db.add(ReportActivity(report_id=report.id, activity_id=activity_id))
        await db.flush()
        read = await _detail(db, member, report.id)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if _duplicate_meeting(error):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="meeting_report_exists",
            ) from error
        raise
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/reports/{report.id}"
    return read


@router.patch("/reports/{report_id}", response_model=ReportRead)
async def update_report(
    report_id: UUID,
    payload: ReportPatch,
    member: CurrentMember,
    db: DbSession,
) -> ReportRead:
    try:
        report = await _locked_report(db, member, report_id)
        if report.status_code not in _EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="report_not_editable",
            )

        values = payload.model_dump(exclude_unset=True)
        activity_ids = values.pop("activity_ids", None)
        deal_sections = values.pop("deal_sections", None)
        if isinstance(values.get("content"), dict):
            # AI 원본은 서버 값을 유지한다. 공통 편집본은 전용 API에서만 갱신한다.
            for key in _SERVER_OWNED_CONTENT_KEYS:
                values["content"].pop(key, None)
                if isinstance(report.content, dict) and key in report.content:
                    values["content"][key] = report.content[key]

        if "recipient_member_id" in values and values["recipient_member_id"] is not None:
            await _visible_recipient(db, member, values["recipient_member_id"])

        if deal_sections is not None:
            if report.report_kind != "meeting":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="deal_sections_not_supported",
                )
            if report.source_activity_id is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="activity_not_found",
                )
            parsed_sections = [ReportDealWrite.model_validate(section) for section in deal_sections]
            await _validate_meeting_deals(
                db,
                member,
                report.source_activity_id,
                parsed_sections,
            )
            await _replace_report_deals(db, report.id, parsed_sections)

        period_start = values.get("period_start", report.period_start)
        period_end = values.get("period_end", report.period_end)
        if period_start is not None and period_end is not None and period_end < period_start:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid_report_period",
            )

        for field_name, value in values.items():
            setattr(report, field_name, value)
        report.updated_at = datetime.now(UTC)

        if activity_ids is not None:
            visible = await _visible_activity_ids(db, member, activity_ids)
            # 새로 묶는 일정에만 소유를 따진다. 규칙이 생기기 전에 팀장이 팀원의
            # 일정으로 만들어 둔 보고서가 있고, 그것을 통째로 막으면 손댈 수 없는
            # 문서가 된다. 이미 묶여 있던 일정은 그대로 둔다.
            linked = await _linked_activity_ids(db, report.id)
            await _own_activity_ids(db, member, [a for a in visible if a not in linked])
            await _replace_report_activities(db, report.id, visible)

        await db.flush()
        read = await _detail(db, member, report_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.post("/reports/{report_id}/submit", response_model=ReportRead)
async def submit_report(
    report_id: UUID,
    payload: ReportSubmit,
    background: BackgroundTasks,
    member: CurrentMember,
    db: DbSession,
) -> ReportRead:
    """작성자가 보고서를 확정하는 자리다. 계약관리·일정관리 에이전트 체인의 트리거이기도
    하다(계약에이전트_설계.md 3장).

    확정 자체는 이 트랜잭션에서 끝낸다. 체이닝은 이미 커밋된 뒤 백그라운드로 미루므로
    실패해도 확정 자체는 되돌리지 않는다.
    """
    try:
        report = await _locked_report(db, member, report_id)
        if report.status_code != payload.expected_status_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )
        if report.status_code not in _EDITABLE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )
        sales_deal_ids: list[UUID] = []
        if report.report_kind == "meeting":
            if report.source_activity_id is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="activity_not_found",
                )
            sections = (
                (await db.execute(select(ReportDeal).where(ReportDeal.report_id == report.id)))
                .scalars()
                .all()
            )
            sales_deal_ids = [section.sales_deal_id for section in sections]
            if not sales_deal_ids and report.sales_deal_id is not None:
                # migration 전 레거시 보고서 제출 호환.
                sales_deal_ids = [report.sales_deal_id]
            if not sales_deal_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="deal_sections_required",
                )
            # 저장 후 달라진 접근 권한·고객사 연결은 확정 전에 다시 확인한다.
            for sales_deal_id in sales_deal_ids:
                await _validate_meeting_deal(db, member, report.source_activity_id, sales_deal_id)
        report.status_code = "submitted"
        report.updated_at = datetime.now(UTC)
        await db.flush()
        read = await _detail(db, member, report_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    for sales_deal_id in sales_deal_ids:
        contract_next_meeting_pipeline.queue(
            background,
            sales_deal_id,
            {"report_id": str(report_id), "sales_deal_id": str(sales_deal_id)},
        )
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
        # report 에는 deleted_at 이 없다. 묶인 일정은 report_activity 의 FK CASCADE 가 지운다.
        await db.delete(report)
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
