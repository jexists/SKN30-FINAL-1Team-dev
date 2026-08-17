from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.crm import Activity, CustomerCompany, CustomerContact
from app.models.sales import Product
from app.models.workspace import Member
from app.schemas.activities import (
    ActivityCreate,
    ActivityPage,
    ActivityPageParams,
    ActivityPatch,
    ActivityRead,
)

router = APIRouter(tags=["activities"])

_SEOUL = ZoneInfo("Asia/Seoul")
_owner = aliased(Member)
_contact = aliased(CustomerContact)
_contact_owner = aliased(Member)
_company = aliased(CustomerCompany)
_product = aliased(Product)


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(Activity)
        .join(_owner, Activity.owner_member_id == _owner.id)
        .outerjoin(_contact, Activity.customer_contact_id == _contact.id)
        .outerjoin(_contact_owner, _contact.owner_member_id == _contact_owner.id)
        .outerjoin(_company, _contact.company_id == _company.id)
        .outerjoin(_product, Activity.product_id == _product.id)
    )


def _scope(member: Member, owner_ids: tuple[UUID, ...] | None = None):
    conditions = [
        Activity.team_id == member.team_id,
        Activity.deleted_at.is_(None),
        _owner.team_id == member.team_id,
        _owner.active.is_(True),
        _owner.role_code.in_(("member", "manager")),
        or_(
            Activity.customer_contact_id.is_(None),
            and_(
                _company.team_id == member.team_id,
                _contact_owner.team_id == member.team_id,
                _contact_owner.active.is_(True),
                _contact_owner.role_code.in_(("member", "manager")),
            ),
        ),
        or_(Activity.product_id.is_(None), _product.team_id == member.team_id),
    ]
    if member.role_code == "member":
        conditions.extend(
            (
                Activity.owner_member_id == member.id,
                or_(
                    Activity.customer_contact_id.is_(None),
                    _contact.owner_member_id == member.id,
                ),
            )
        )
    elif owner_ids is not None:
        conditions.append(Activity.owner_member_id.in_(owner_ids))
    return conditions


def _seoul(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(_SEOUL)


def _activity_read(
    activity: Activity,
    owner_display_name: str,
    contact: CustomerContact | None,
    company_id: UUID | None,
    company_name: str | None,
    product_name: str | None,
) -> ActivityRead:
    return ActivityRead(
        id=activity.id,
        owner_member_id=activity.owner_member_id,
        owner_display_name=owner_display_name,
        customer_contact_id=activity.customer_contact_id,
        customer_contact_name=None if contact is None else contact.name,
        customer_contact_department=None if contact is None else contact.department,
        customer_contact_job_title=None if contact is None else contact.job_title,
        customer_company_id=company_id,
        customer_company_name=company_name,
        product_id=activity.product_id,
        product_name=product_name,
        activity_type=activity.activity_type,
        category_code=activity.category_code,
        title=activity.title,
        starts_at=_seoul(activity.starts_at),
        ends_at=_seoul(activity.ends_at),
        all_day=activity.all_day,
        location=activity.location,
        action_tag=activity.action_tag,
        completed_at=_seoul(activity.completed_at),
        note=activity.note,
        created_at=_seoul(activity.created_at),
        updated_at=_seoul(activity.updated_at),
    )


async def _owner_filter(
    db: AsyncSession,
    member: Member,
    requested: list[UUID] | None,
) -> tuple[UUID, ...] | None:
    if requested is None:
        return None
    if member.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="scope_not_allowed",
        )
    owner_ids = tuple(dict.fromkeys(requested))
    result = await db.execute(
        select(Member.id).where(
            Member.id.in_(owner_ids),
            Member.team_id == member.team_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    if set(result.scalars().all()) != set(owner_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="scope_not_allowed",
        )
    return owner_ids


async def _activity_row(
    db: AsyncSession,
    member: Member,
    activity_id: UUID,
):
    result = await db.execute(
        _joined_select(
            Activity,
            _owner.display_name,
            _contact,
            _company.id,
            _company.name,
            _product.name,
        ).where(Activity.id == activity_id, *_scope(member))
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="activity_not_found",
        )
    return row


async def _locked_activity(
    db: AsyncSession,
    member: Member,
    activity_id: UUID,
) -> Activity:
    conditions = [
        Activity.id == activity_id,
        Activity.team_id == member.team_id,
        Activity.deleted_at.is_(None),
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(Activity.owner_member_id == member.id)
    result = await db.execute(
        select(Activity)
        .join(Member, Activity.owner_member_id == Member.id)
        .where(*conditions)
        .with_for_update(of=Activity)
    )
    activity = result.scalar_one_or_none()
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="activity_not_found",
        )
    return activity


async def _contact_info(
    db: AsyncSession,
    member: Member,
    contact_id: UUID,
) -> tuple[CustomerContact, UUID, str]:
    conditions = [
        CustomerContact.id == contact_id,
        CustomerCompany.team_id == member.team_id,
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(CustomerContact.owner_member_id == member.id)
    result = await db.execute(
        select(CustomerContact, CustomerCompany.id, CustomerCompany.name)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .where(*conditions)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_contact_not_found",
        )
    return row


async def _team_product(db: AsyncSession, member: Member, product_id: UUID) -> Product:
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.team_id == member.team_id,
            Product.active.is_(True),
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="product_not_found",
        )
    return product


def _validate_range(starts_at: datetime, ends_at: datetime | None) -> None:
    if ends_at is not None and ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_activity_range",
        )


@router.get("/activities", response_model=ActivityPage)
async def list_activities(
    page: Annotated[ActivityPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> ActivityPage:
    owner_ids = await _owner_filter(db, member, page.owner_member_id)
    start_at = datetime.combine(page.start_date, time.min, _SEOUL)
    end_at = datetime.combine(page.end_date or page.start_date, time.min, _SEOUL) + timedelta(
        days=1
    )
    scope = [
        *_scope(member, owner_ids),
        Activity.starts_at >= start_at,
        Activity.starts_at < end_at,
    ]
    total_result = await db.execute(_joined_select(func.count(Activity.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(
            Activity,
            _owner.display_name,
            _contact,
            _company.id,
            _company.name,
            _product.name,
        )
        .where(*scope)
        .order_by(Activity.starts_at, Activity.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    items = [_activity_read(*row) for row in rows_result.all()]
    has_more = page.skip + len(items) < total
    return ActivityPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/activities/{activity_id}", response_model=ActivityRead)
async def get_activity(
    activity_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> ActivityRead:
    return _activity_read(*await _activity_row(db, member, activity_id))


@router.post(
    "/activities",
    response_model=ActivityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity(
    payload: ActivityCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> ActivityRead:
    try:
        contact_info = (
            None
            if payload.customer_contact_id is None
            else await _contact_info(db, member, payload.customer_contact_id)
        )
        product = (
            None
            if payload.product_id is None
            else await _team_product(db, member, payload.product_id)
        )
        activity = Activity(
            id=uuid4(),
            team_id=member.team_id,
            owner_member_id=member.id,
            **payload.model_dump(),
        )
        db.add(activity)
        await db.flush()
        read = _activity_read(
            activity,
            member.display_name,
            None if contact_info is None else contact_info[0],
            None if contact_info is None else contact_info[1],
            None if contact_info is None else contact_info[2],
            None if product is None else product.name,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/activities/{activity.id}"
    return read


@router.patch("/activities/{activity_id}", response_model=ActivityRead)
async def update_activity(
    activity_id: UUID,
    payload: ActivityPatch,
    member: CurrentMember,
    db: DbSession,
) -> ActivityRead:
    try:
        activity = await _locked_activity(db, member, activity_id)
        values = payload.model_dump(exclude_unset=True)
        if values.get("customer_contact_id") is not None:
            await _contact_info(db, member, values["customer_contact_id"])
        if values.get("product_id") is not None:
            await _team_product(db, member, values["product_id"])
        _validate_range(
            values.get("starts_at", activity.starts_at),
            values.get("ends_at", activity.ends_at),
        )
        for field_name, value in values.items():
            setattr(activity, field_name, value)
        activity.updated_at = datetime.now(UTC)
        await db.flush()
        read = _activity_read(*await _activity_row(db, member, activity_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.delete("/activities/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(
    activity_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    try:
        activity = await _locked_activity(db, member, activity_id)
        now = datetime.now(UTC)
        activity.deleted_at = now
        activity.updated_at = now
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
