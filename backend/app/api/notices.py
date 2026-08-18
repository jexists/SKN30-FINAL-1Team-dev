from datetime import datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.workspace import Member, Notice
from app.schemas.notices import NoticePage, NoticePageParams, NoticeRead

router = APIRouter(tags=["notices"])

_SEOUL = ZoneInfo("Asia/Seoul")
_author = aliased(Member)


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _seoul(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(_SEOUL)


def _joined_select(*entities):
    return (
        select(*entities).select_from(Notice).join(_author, Notice.author_member_id == _author.id)
    )


def _scope(member: Member, requested: str | None):
    """공지는 팀 전체가 보고 지시는 수신자 본인만 본다. 담당자 범위와 무관하다."""
    conditions = [
        Notice.team_id == member.team_id,
        _author.team_id == member.team_id,
        _author.role_code.in_(("member", "manager")),
    ]
    if requested == "team":
        conditions.append(Notice.recipient_member_id.is_(None))
    elif requested == "personal":
        conditions.append(Notice.recipient_member_id == member.id)
    else:
        conditions.append(
            or_(
                Notice.recipient_member_id.is_(None),
                Notice.recipient_member_id == member.id,
            )
        )
    return conditions


def _notice_read(notice: Notice, author_display_name: str) -> NoticeRead:
    return NoticeRead(
        id=notice.id,
        scope="team" if notice.recipient_member_id is None else "personal",
        author_member_id=notice.author_member_id,
        author_display_name=author_display_name,
        recipient_member_id=notice.recipient_member_id,
        tag=notice.tag,
        title=notice.title,
        body=notice.body,
        image_alt=notice.image_alt,
        published_at=_seoul(notice.published_at),
        due_at=_seoul(notice.due_at),
        due_text=notice.due_text,
    )


async def _notice_row(db: AsyncSession, member: Member, notice_id: UUID):
    result = await db.execute(
        _joined_select(Notice, _author.display_name).where(
            Notice.id == notice_id, *_scope(member, None)
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="notice_not_found",
        )
    return row


@router.get("/notices", response_model=NoticePage)
async def list_notices(
    page: Annotated[NoticePageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> NoticePage:
    scope = _scope(member, page.scope)
    if page.published_from is not None:
        scope.append(Notice.published_at >= page.published_from)
    if page.published_to is not None:
        scope.append(Notice.published_at <= page.published_to)
    if page.q is not None:
        pattern = _contains(page.q)
        scope.append(
            or_(
                Notice.title.ilike(pattern, escape="\\"),
                Notice.body.ilike(pattern, escape="\\"),
                Notice.tag.ilike(pattern, escape="\\"),
                _author.display_name.ilike(pattern, escape="\\"),
            )
        )

    total_result = await db.execute(_joined_select(func.count(Notice.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(Notice, _author.display_name)
        .where(*scope)
        .order_by(Notice.published_at.desc(), Notice.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    items = [_notice_read(*row) for row in rows_result.all()]
    has_more = page.skip + len(items) < total
    return NoticePage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/notices/{notice_id}", response_model=NoticeRead)
async def get_notice(
    notice_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> NoticeRead:
    return _notice_read(*await _notice_row(db, member, notice_id))
