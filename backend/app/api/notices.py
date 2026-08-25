"""공지와 팀장 지시사항.

읽기는 팀원 모두가 하고 쓰기는 팀장만 한다. 팀원이 보는 목록은 지운 것·숨긴 것·노출 기간
밖을 모두 걷어내지만, 팀장 관리 목록은 기간을 보지 않는다. 아직 시작하지 않은 글과 이미 끝난
글을 봐야 고칠 수 있기 때문이다.

본문은 편집기가 만든 HTML 이다. 저장 직전에 services.html_sanitize 가 허용한 태그만 남기고,
본문 안의 사진은 `/notice-images/{id}` 라는 내부 참조로만 남는다. 실제로 볼 수 있는 주소는
응답을 만들 때마다 서명 URL 로 새로 발급한다. 저장소 주소는 응답에 나가지 않는다.
"""

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.core.config import settings
from app.models.workspace import Member, Notice, NoticeImage, NoticeTarget
from app.schemas.notices import (
    NoticeCreate,
    NoticeImageRead,
    NoticeManageListItem,
    NoticeManagePage,
    NoticeManagePageParams,
    NoticeManageRead,
    NoticePage,
    NoticePageParams,
    NoticePatch,
    NoticeRead,
    NoticeTargetRead,
)
from app.services import storage
from app.services.html_sanitize import (
    NOTICE_IMAGE_PREFIX,
    BodyEmpty,
    image_ids,
    sanitize_body,
)
from app.services.storage import StorageError
from app.services.upload_guard import UploadRejected, check_image_upload, check_size

router = APIRouter(tags=["notices"])

_SEOUL = ZoneInfo("Asia/Seoul")
_author = aliased(Member)

# 본문 사진은 상품 사진과 같은 규칙으로 받는다.
NOTICE_IMAGE_MAX_BYTES = 5 * 1024 * 1024
# 본문을 한 번 그리는 동안 살아 있으면 된다.
NOTICE_IMAGE_EXPIRES_IN = 300

# 옛 어휘(team/personal)와 새 어휘(NOTICE/DIRECTIVE)를 함께 받는다. 대시보드가 옛 어휘로
# _scope 를 부르고 있어 둘 다 통해야 한다.
_SCOPE_TO_TYPE = {
    "team": "NOTICE",
    "personal": "DIRECTIVE",
    "NOTICE": "NOTICE",
    "DIRECTIVE": "DIRECTIVE",
}


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _seoul(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(_SEOUL)


def _today() -> date:
    """업무상 오늘은 Asia/Seoul 기준이다. dashboard._day_bounds 와 같은 규약이다."""
    return datetime.now(_SEOUL).date()


def _joined_select(*entities):
    return (
        select(*entities).select_from(Notice).join(_author, Notice.author_member_id == _author.id)
    )


def _targeted_to(member_id: UUID):
    """이 지시가 그 사람에게 왔는지 묻는다.

    조인하지 않고 EXISTS 로 묻는다. 조인하면 지시 한 건이 수신자 수만큼 늘어나 목록의 total 이
    부풀고 같은 글이 여러 줄로 보인다.
    """
    return (
        select(NoticeTarget.member_id)
        .where(NoticeTarget.notice_id == Notice.id, NoticeTarget.member_id == member_id)
        .exists()
    )


def _visible(member: Member, requested_type: str | None):
    """팀원이 볼 수 있는 것. 지운 것, 숨긴 것, 노출 기간 밖은 여기서 모두 빠진다."""
    today = _today()
    conditions = [
        Notice.team_id == member.team_id,
        _author.team_id == member.team_id,
        _author.role_code.in_(("member", "manager")),
        Notice.deleted_at.is_(None),
        Notice.is_hidden.is_(False),
        Notice.display_start_date <= today,
        or_(Notice.display_end_date.is_(None), Notice.display_end_date >= today),
    ]
    if requested_type == "NOTICE":
        conditions.append(Notice.type == "NOTICE")
    elif requested_type == "DIRECTIVE":
        conditions.append(Notice.type == "DIRECTIVE")
        conditions.append(_targeted_to(member.id))
    else:
        conditions.append(
            or_(
                Notice.type == "NOTICE",
                and_(Notice.type == "DIRECTIVE", _targeted_to(member.id)),
            )
        )
    return conditions


def _scope(member: Member, requested: str | None):
    """공지는 팀 전체가 보고 지시는 수신자 본인만 본다. 담당자 범위와 무관하다.

    이름과 인자 모양을 그대로 둔다. dashboard 가 이 함수를 직접 가져다 쓰므로, 여기 조건이
    곧 대시보드 카드의 조건이다.
    """
    return _visible(member, _SCOPE_TO_TYPE.get(requested or ""))


def _require_manager(member: Member) -> None:
    """공지와 지시는 팀장이 관리한다. 읽기는 팀원 그대로다."""
    if member.role_code != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager_required")


def _require_storage() -> None:
    if not settings.storage_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage_not_configured",
        )


async def _flush_and_commit(db: AsyncSession) -> None:
    try:
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def _render_body(db: AsyncSession, member: Member, body: str) -> str:
    """본문의 사진 참조를 그 자리에서 발급한 서명 URL 로 바꾼다.

    본문에는 저장소 주소가 없고 우리 id 만 있다. 서명 URL 은 짧게 살기 때문에 본문에 박아
    둘 수 없고, 읽을 때마다 새로 만든다. 발급에 실패한 사진은 참조를 그대로 두어 본문의
    나머지가 함께 무너지지 않게 한다.
    """
    wanted = image_ids(body)
    if not wanted:
        return body

    rows = (
        await db.execute(
            select(NoticeImage.id, NoticeImage.storage_key).where(
                NoticeImage.id.in_([UUID(value) for value in wanted]),
                NoticeImage.team_id == member.team_id,
            )
        )
    ).all()

    rendered = body
    for image_id, storage_key in rows:
        try:
            url = await storage.signed_url(
                storage_key=storage_key,
                expires_in=NOTICE_IMAGE_EXPIRES_IN,
            )
        except StorageError:
            continue
        rendered = rendered.replace(f"{NOTICE_IMAGE_PREFIX}{image_id}", url)
    return rendered


async def _load_targets(
    db: AsyncSession,
    notices: list[Notice],
) -> dict[UUID, list[NoticeTargetRead]]:
    """지시들의 수신자를 한 번에 읽는다. 행마다 따로 묻지 않는다."""
    grouped: dict[UUID, list[NoticeTargetRead]] = {notice.id: [] for notice in notices}
    directive_ids = [notice.id for notice in notices if notice.type == "DIRECTIVE"]
    if not directive_ids:
        return grouped

    result = await db.execute(
        select(NoticeTarget.notice_id, Member.id, Member.display_name)
        .join(Member, NoticeTarget.member_id == Member.id)
        .where(NoticeTarget.notice_id.in_(directive_ids))
        .order_by(NoticeTarget.created_at, Member.display_name, Member.id)
    )
    for notice_id, member_id, display_name in result.all():
        grouped[notice_id].append(NoticeTargetRead(id=member_id, display_name=display_name))
    return grouped


async def _resolve_targets(
    db: AsyncSession,
    member: Member,
    target_member_ids: list[UUID],
) -> list[Member]:
    """수신자를 정한다. 고른 순서가 곧 표시 순서다."""
    ordered = list(dict.fromkeys(target_member_ids))
    if not ordered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="directive_target_required",
        )

    result = await db.execute(
        select(Member).where(
            Member.id.in_(ordered),
            Member.team_id == member.team_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    found = {row.id: row for row in result.scalars().all()}
    if len(found) != len(ordered):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="notice_target_member_not_found",
        )
    return [found[target_id] for target_id in ordered]


def _sanitize(body: str) -> str:
    try:
        return sanitize_body(body)
    except BodyEmpty as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="notice_body_empty",
        ) from error


def _check_display_range(start: date, end: date | None) -> None:
    """스키마는 시작일을 생략한 요청의 범위를 보지 못한다. 값이 정해진 뒤 다시 본다."""
    if end is not None and end < start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_notice_display_range",
        )


def _notice_read(
    notice: Notice,
    author_display_name: str,
    targets: list[NoticeTargetRead],
    body: str,
) -> NoticeRead:
    return NoticeRead(
        id=notice.id,
        scope="team" if notice.type == "NOTICE" else "personal",
        type=notice.type,
        author_member_id=notice.author_member_id,
        author_display_name=author_display_name,
        recipient_member_id=targets[0].id if len(targets) == 1 else None,
        tag=notice.tag,
        title=notice.title,
        body=body,
        image_alt=notice.image_alt,
        published_at=_seoul(notice.published_at),
        due_at=_seoul(notice.due_at),
        due_text=notice.due_text,
    )


def _manage_fields(
    notice: Notice,
    author_display_name: str,
    targets: list[NoticeTargetRead],
) -> dict:
    return {
        "id": notice.id,
        "type": notice.type,
        "author_member_id": notice.author_member_id,
        "author_display_name": author_display_name,
        "tag": notice.tag,
        "title": notice.title,
        "image_alt": notice.image_alt,
        "published_at": _seoul(notice.published_at),
        "due_at": _seoul(notice.due_at),
        "due_text": notice.due_text,
        "display_start_date": notice.display_start_date,
        "display_end_date": notice.display_end_date,
        "is_hidden": notice.is_hidden,
        "sort_order": notice.sort_order,
        "targets": targets,
        "target_member_ids": [target.id for target in targets],
        "updated_at": _seoul(notice.updated_at),
    }


def _manage_list_item(
    notice: Notice,
    author_display_name: str,
    targets: list[NoticeTargetRead],
) -> NoticeManageListItem:
    return NoticeManageListItem(**_manage_fields(notice, author_display_name, targets))


def _manage_read(
    notice: Notice,
    author_display_name: str,
    targets: list[NoticeTargetRead],
    body: str,
) -> NoticeManageRead:
    return NoticeManageRead(**_manage_fields(notice, author_display_name, targets), body=body)


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


async def _manage_row(db: AsyncSession, member: Member, notice_id: UUID):
    """팀장이 관리하는 한 건. 숨겼거나 기간이 지난 것도 잡힌다."""
    result = await db.execute(
        _joined_select(Notice, _author.display_name).where(
            Notice.id == notice_id,
            Notice.team_id == member.team_id,
            Notice.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="notice_not_found",
        )
    return row


async def _notice_for_update(db: AsyncSession, member: Member, notice_id: UUID) -> Notice:
    notice = (
        await db.execute(
            select(Notice)
            .where(
                Notice.id == notice_id,
                Notice.team_id == member.team_id,
                Notice.deleted_at.is_(None),
            )
            .with_for_update(of=Notice)
        )
    ).scalar_one_or_none()
    if notice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notice_not_found")
    return notice


@router.get("/notices", response_model=NoticePage)
async def list_notices(
    page: Annotated[NoticePageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> NoticePage:
    scope = _visible(member, page.type or _SCOPE_TO_TYPE.get(page.scope or ""))
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
        .order_by(Notice.sort_order, Notice.published_at.desc(), Notice.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    rows = rows_result.all()
    targets = await _load_targets(db, [notice for notice, _ in rows])
    items = [
        _notice_read(
            notice,
            author_display_name,
            targets[notice.id],
            await _render_body(db, member, notice.body),
        )
        for notice, author_display_name in rows
    ]
    has_more = page.skip + len(items) < total
    return NoticePage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


# 아래 /notices/{notice_id} 보다 먼저 선언한다. 순서가 바뀌면 "manage" 와 "images" 가
# UUID 로 읽혀 422 가 난다.
@router.get("/notices/manage", response_model=NoticeManagePage)
async def list_notices_for_manage(
    page: Annotated[NoticeManagePageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> NoticeManagePage:
    _require_manager(member)
    # 노출 기간은 보지 않는다. 아직 시작하지 않은 글과 끝난 글도 팀장은 봐야 고칠 수 있다.
    conditions = [
        Notice.team_id == member.team_id,
        _author.team_id == member.team_id,
        Notice.deleted_at.is_(None),
    ]
    if not page.include_hidden:
        conditions.append(Notice.is_hidden.is_(False))
    if page.type is not None:
        conditions.append(Notice.type == page.type)
    if page.q is not None:
        pattern = _contains(page.q)
        conditions.append(
            or_(
                Notice.title.ilike(pattern, escape="\\"),
                Notice.body.ilike(pattern, escape="\\"),
                Notice.tag.ilike(pattern, escape="\\"),
                _author.display_name.ilike(pattern, escape="\\"),
            )
        )

    total_result = await db.execute(_joined_select(func.count(Notice.id)).where(*conditions))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(Notice, _author.display_name)
        .where(*conditions)
        .order_by(Notice.sort_order, Notice.published_at.desc(), Notice.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    rows = rows_result.all()
    targets = await _load_targets(db, [notice for notice, _ in rows])
    items = [
        _manage_list_item(notice, author_display_name, targets[notice.id])
        for notice, author_display_name in rows
    ]
    has_more = page.skip + len(items) < total
    return NoticeManagePage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/notices/manage/{notice_id}", response_model=NoticeManageRead)
async def get_notice_for_manage(
    notice_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> NoticeManageRead:
    _require_manager(member)
    notice, author_display_name = await _manage_row(db, member, notice_id)
    targets = (await _load_targets(db, [notice]))[notice.id]
    body = await _render_body(db, member, notice.body)
    return _manage_read(notice, author_display_name, targets, body)


@router.post(
    "/notices/images",
    response_model=NoticeImageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_notice_image(
    member: CurrentMember,
    db: DbSession,
    upload: Annotated[UploadFile, File()],
) -> NoticeImageRead:
    """본문에 넣을 사진을 받는다.

    돌려주는 url 은 저장소 주소가 아니라 우리 내부 참조다. 본문에는 이것만 박히고, 볼 수 있는
    주소는 읽을 때마다 새로 발급한다.

    ponytail: 본문에서 빠진 사진의 저장소 객체는 아직 회수하지 않는다. notice_image 에
    team_id 를 두었으므로 나중에 팀 단위로 훑어 정리할 수 있다.
    """
    _require_manager(member)
    _require_storage()
    content = await upload.read()

    try:
        check_size(len(content), NOTICE_IMAGE_MAX_BYTES)
        allowed = check_image_upload(
            file_name=upload.filename or "",
            declared_media_type=upload.content_type,
            content=content,
        )
    except UploadRejected as rejected:
        raise HTTPException(status_code=rejected.status_code, detail=rejected.detail) from rejected

    storage_key = storage.build_storage_key(member.team_id, allowed.extension)
    try:
        await storage.upload(
            storage_key=storage_key,
            content=content,
            media_type=allowed.media_type,
        )
    except StorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    image = NoticeImage(
        id=uuid4(),
        team_id=member.team_id,
        uploaded_by_member_id=member.id,
        storage_key=storage_key,
        media_type=allowed.media_type,
    )
    try:
        db.add(image)
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        # DB 기록이 실패하면 올린 객체를 지워 고아를 남기지 않는다.
        await storage.remove(storage_key=storage_key)
        raise
    return NoticeImageRead(id=image.id, url=f"{NOTICE_IMAGE_PREFIX}{image.id}")


@router.get("/notices/{notice_id}", response_model=NoticeRead)
async def get_notice(
    notice_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> NoticeRead:
    notice, author_display_name = await _notice_row(db, member, notice_id)
    targets = (await _load_targets(db, [notice]))[notice.id]
    body = await _render_body(db, member, notice.body)
    return _notice_read(notice, author_display_name, targets, body)


@router.post("/notices", response_model=NoticeManageRead, status_code=status.HTTP_201_CREATED)
async def create_notice(
    payload: NoticeCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> NoticeManageRead:
    _require_manager(member)
    body = _sanitize(payload.body)

    targets: list[Member] = []
    if payload.type == "DIRECTIVE":
        targets = await _resolve_targets(db, member, payload.target_member_ids or [])

    display_start_date = payload.display_start_date or _today()
    _check_display_range(display_start_date, payload.display_end_date)

    now = datetime.now(UTC)
    notice = Notice(
        id=uuid4(),
        team_id=member.team_id,
        author_member_id=member.id,
        type=payload.type,
        tag=payload.tag,
        title=payload.title,
        body=body,
        # DB 기본값에 기대지 않고 넣는다. 넣은 객체를 그대로 응답으로 쓰기 때문이다.
        image_storage_key=None,
        image_alt=payload.image_alt,
        published_at=now,
        due_at=payload.due_at,
        due_text=payload.due_text,
        display_start_date=display_start_date,
        display_end_date=payload.display_end_date,
        is_hidden=payload.is_hidden,
        sort_order=payload.sort_order,
        updated_at=now,
        deleted_at=None,
    )
    db.add(notice)
    for target in targets:
        db.add(NoticeTarget(notice_id=notice.id, member_id=target.id))
    await _flush_and_commit(db)

    response.headers["Location"] = f"/api/notices/{notice.id}"
    return _manage_read(
        notice,
        member.display_name,
        [NoticeTargetRead(id=target.id, display_name=target.display_name) for target in targets],
        await _render_body(db, member, notice.body),
    )


@router.patch("/notices/{notice_id}", response_model=NoticeManageRead)
async def update_notice(
    notice_id: UUID,
    payload: NoticePatch,
    member: CurrentMember,
    db: DbSession,
) -> NoticeManageRead:
    _require_manager(member)
    values = payload.model_dump(exclude_unset=True)

    try:
        notice = await _notice_for_update(db, member, notice_id)

        final_type = values.get("type", notice.type)
        # 수신자를 어떻게 할지 먼저 정한다. None 은 "그대로 둔다" 는 뜻이다.
        if "target_member_ids" in values:
            requested_targets = values.pop("target_member_ids")
        elif final_type != notice.type:
            # 종류가 바뀌는데 수신자를 주지 않았다. 공지로 가면 비우고, 지시로 가면 받아야 한다.
            if final_type == "DIRECTIVE":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="directive_target_required",
                )
            requested_targets = []
        else:
            requested_targets = None

        if final_type == "NOTICE" and requested_targets:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="notice_cannot_have_targets",
            )
        if final_type == "DIRECTIVE" and requested_targets is not None and not requested_targets:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="directive_target_required",
            )

        resolved: list[Member] = []
        if requested_targets and final_type == "DIRECTIVE":
            resolved = await _resolve_targets(db, member, requested_targets)

        if "body" in values:
            values["body"] = _sanitize(values["body"])

        for field_name, value in values.items():
            setattr(notice, field_name, value)
        _check_display_range(notice.display_start_date, notice.display_end_date)
        notice.updated_at = datetime.now(UTC)

        if requested_targets is not None:
            # 수신자는 통째로 갈아 끼운다. 지운 뒤 고른 순서대로 다시 넣는다.
            await db.execute(delete(NoticeTarget).where(NoticeTarget.notice_id == notice.id))
            for target in resolved:
                db.add(NoticeTarget(notice_id=notice.id, member_id=target.id))

        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    notice, author_display_name = await _manage_row(db, member, notice_id)
    targets = (await _load_targets(db, [notice]))[notice.id]
    body = await _render_body(db, member, notice.body)
    return _manage_read(notice, author_display_name, targets, body)


@router.delete("/notices/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notice(
    notice_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    """지우지 않고 가린다. 수신자 행은 남겨 되살릴 여지를 없애지 않는다."""
    _require_manager(member)
    try:
        notice = await _notice_for_update(db, member, notice_id)
        now = datetime.now(UTC)
        notice.deleted_at = now
        notice.updated_at = now
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
