from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.configuration import ActivityActionTag, ActivityCategory
from app.models.crm import Activity, CustomerCompany, CustomerContact
from app.models.sales import Product, SalesDeal
from app.models.workspace import Member
from app.schemas.activities import (
    ActivityCreate,
    ActivityOptionRead,
    ActivityPage,
    ActivityPageParams,
    ActivityPatch,
    ActivityRead,
    ActivityType,
)

router = APIRouter(tags=["activities"])

_SEOUL = ZoneInfo("Asia/Seoul")
_owner = aliased(Member)
_contact = aliased(CustomerContact)
_contact_owner = aliased(Member)
_company = aliased(CustomerCompany)
_product = aliased(Product)
_sales_deal = aliased(SalesDeal)
_activity_category = aliased(ActivityCategory)
_activity_action_tag = aliased(ActivityActionTag)


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(Activity)
        .join(_owner, Activity.owner_member_id == _owner.id)
        .outerjoin(_contact, Activity.customer_contact_id == _contact.id)
        .outerjoin(_contact_owner, _contact.owner_member_id == _contact_owner.id)
        .outerjoin(_company, _contact.company_id == _company.id)
        .outerjoin(_product, Activity.product_id == _product.id)
        .outerjoin(_sales_deal, Activity.sales_deal_id == _sales_deal.id)
        .join(_activity_category, Activity.activity_category_id == _activity_category.id)
        .outerjoin(
            _activity_action_tag,
            Activity.activity_action_tag_id == _activity_action_tag.id,
        )
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
        _activity_category.team_id == member.team_id,
        or_(
            Activity.activity_action_tag_id.is_(None),
            _activity_action_tag.team_id == member.team_id,
        ),
        or_(
            Activity.sales_deal_id.is_(None),
            and_(
                _sales_deal.team_id == member.team_id,
                _sales_deal.deleted_at.is_(None),
            ),
        ),
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
    category: ActivityCategory,
    action_tag: ActivityActionTag | None,
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
        sales_deal_id=activity.sales_deal_id,
        activity_type=activity.activity_type,
        activity_category_id=category.id,
        activity_category_name=category.name,
        activity_category_tone=category.tone,
        category_code=category.code,
        title=activity.title,
        starts_at=_seoul(activity.starts_at),
        ends_at=_seoul(activity.ends_at),
        all_day=activity.all_day,
        location=activity.location,
        activity_action_tag_id=None if action_tag is None else action_tag.id,
        activity_action_tag_name=None if action_tag is None else action_tag.name,
        activity_action_tag_tone=None if action_tag is None else action_tag.tone,
        action_tag=None if action_tag is None else action_tag.code,
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
            _activity_category,
            _activity_action_tag,
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


async def _team_sales_deal(
    db: AsyncSession,
    member: Member,
    sales_deal_id: UUID,
) -> SalesDeal:
    conditions = [
        SalesDeal.id == sales_deal_id,
        SalesDeal.team_id == member.team_id,
        SalesDeal.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)
    result = await db.execute(select(SalesDeal).where(*conditions))
    sales_deal = result.scalar_one_or_none()
    if sales_deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sales_deal_not_found",
        )
    return sales_deal


async def _active_activity_category(
    db: AsyncSession,
    member: Member,
    code: str,
    activity_type: str,
) -> ActivityCategory:
    result = await db.execute(
        select(ActivityCategory).where(
            ActivityCategory.team_id == member.team_id,
            ActivityCategory.code == code,
            ActivityCategory.activity_type == activity_type,
            ActivityCategory.deleted_at.is_(None),
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="activity_category_code_not_found",
        )
    return category


async def _active_activity_action_tag(
    db: AsyncSession,
    member: Member,
    code: str,
    activity_type: str,
) -> ActivityActionTag:
    result = await db.execute(
        select(ActivityActionTag).where(
            ActivityActionTag.team_id == member.team_id,
            ActivityActionTag.code == code,
            ActivityActionTag.activity_type == activity_type,
            ActivityActionTag.deleted_at.is_(None),
        )
    )
    action_tag = result.scalar_one_or_none()
    if action_tag is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="activity_action_tag_code_not_found",
        )
    return action_tag


def _validate_range(starts_at: datetime, ends_at: datetime | None) -> None:
    if ends_at is not None and ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_activity_range",
        )


@router.get("/activity-categories", response_model=list[ActivityOptionRead])
async def list_activity_categories(
    activity_type: Annotated[ActivityType, Query()],
    member: CurrentMember,
    db: DbSession,
) -> list[ActivityCategory]:
    result = await db.execute(
        select(ActivityCategory)
        .where(
            ActivityCategory.team_id == member.team_id,
            ActivityCategory.activity_type == activity_type,
            ActivityCategory.deleted_at.is_(None),
        )
        .order_by(ActivityCategory.position, ActivityCategory.id)
    )
    return list(result.scalars().all())


@router.get("/activity-action-tags", response_model=list[ActivityOptionRead])
async def list_activity_action_tags(
    activity_type: Annotated[ActivityType, Query()],
    member: CurrentMember,
    db: DbSession,
) -> list[ActivityActionTag]:
    result = await db.execute(
        select(ActivityActionTag)
        .where(
            ActivityActionTag.team_id == member.team_id,
            ActivityActionTag.activity_type == activity_type,
            ActivityActionTag.deleted_at.is_(None),
        )
        .order_by(ActivityActionTag.position, ActivityActionTag.id)
    )
    return list(result.scalars().all())


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
            _activity_category,
            _activity_action_tag,
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
        if payload.sales_deal_id is not None:
            await _team_sales_deal(db, member, payload.sales_deal_id)
        category = await _active_activity_category(
            db,
            member,
            payload.category_code,
            payload.activity_type,
        )
        action_tag = (
            None
            if payload.action_tag is None
            else await _active_activity_action_tag(
                db,
                member,
                payload.action_tag,
                payload.activity_type,
            )
        )
        values = payload.model_dump()
        values.pop("category_code")
        values.pop("action_tag")
        activity = Activity(
            id=uuid4(),
            team_id=member.team_id,
            owner_member_id=member.id,
            activity_category_id=category.id,
            activity_action_tag_id=None if action_tag is None else action_tag.id,
            **values,
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
            category,
            action_tag,
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
        activity_type = values.get("activity_type", activity.activity_type)
        if "activity_type" in values and "category_code" not in values:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="category_code_required_with_activity_type",
            )
        if (
            "activity_type" in values
            and activity.activity_action_tag_id is not None
            and "action_tag" not in values
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="action_tag_required_with_activity_type",
            )
        if values.get("customer_contact_id") is not None:
            await _contact_info(db, member, values["customer_contact_id"])
        if values.get("product_id") is not None:
            await _team_product(db, member, values["product_id"])
        if values.get("sales_deal_id") is not None:
            await _team_sales_deal(db, member, values["sales_deal_id"])
        if "category_code" in values:
            category_code = values.pop("category_code")
            category = await _active_activity_category(
                db,
                member,
                category_code,
                activity_type,
            )
            activity.activity_category_id = category.id
        if "action_tag" in values:
            action_tag = values.pop("action_tag")
            activity.activity_action_tag_id = (
                None
                if action_tag is None
                else (
                    await _active_activity_action_tag(
                        db,
                        member,
                        action_tag,
                        activity_type,
                    )
                ).id
            )
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


@router.post("/activities/{activity_id}/complete", response_model=ActivityRead)
async def complete_activity(
    activity_id: UUID,
    member: CurrentMember,
    db: DbSession,
):
    try:
        activity = await _locked_activity(db, member, activity_id)
        if activity.completed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="already_completed",
            )
        now = datetime.now(UTC)
        activity.completed_at = now
        activity.updated_at = now
        await db.flush()
        read = _activity_read(*await _activity_row(db, member, activity_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read
