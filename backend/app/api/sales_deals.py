from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.configuration import SalesDealType
from app.models.crm import CustomerCompany, CustomerContact
from app.models.sales import Product, SalesDeal, SalesPipeline, SalesPipelineStage
from app.models.workspace import Member, Team
from app.schemas.sales_deals import (
    ProductPage,
    ProductPageParams,
    SalesDealCreate,
    SalesDealMove,
    SalesDealPage,
    SalesDealPageParams,
    SalesDealPatch,
    SalesDealRead,
    SalesDealTypeRead,
    SalesPipelineRead,
    SalesPipelineStageRead,
)

router = APIRouter(tags=["sales-deals"])

_SEOUL = ZoneInfo("Asia/Seoul")
_owner = aliased(Member)
_company = aliased(CustomerCompany)
_contact = aliased(CustomerContact)
_contact_owner = aliased(Member)
_product = aliased(Product)
_pipeline = aliased(SalesPipeline)
_stage = aliased(SalesPipelineStage)
_deal_type = aliased(SalesDealType)


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _seoul(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(_SEOUL)


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(SalesDeal)
        .join(_owner, SalesDeal.owner_member_id == _owner.id)
        .join(_company, SalesDeal.customer_company_id == _company.id)
        .outerjoin(_contact, SalesDeal.customer_contact_id == _contact.id)
        .outerjoin(_contact_owner, _contact.owner_member_id == _contact_owner.id)
        .outerjoin(_product, SalesDeal.product_id == _product.id)
        .join(_pipeline, SalesDeal.sales_pipeline_id == _pipeline.id)
        .join(
            _stage,
            and_(
                SalesDeal.sales_pipeline_id == _stage.sales_pipeline_id,
                SalesDeal.sales_pipeline_stage_id == _stage.id,
            ),
        )
        .join(_deal_type, SalesDeal.sales_deal_type_id == _deal_type.id)
    )


def _scope(member: Member, owner_ids: tuple[UUID, ...] | None = None):
    conditions = [
        SalesDeal.team_id == member.team_id,
        SalesDeal.deleted_at.is_(None),
        _owner.team_id == member.team_id,
        _owner.active.is_(True),
        _owner.role_code.in_(("member", "manager")),
        _company.team_id == member.team_id,
        _pipeline.team_id == member.team_id,
        _pipeline.status_code.in_(("published", "archived")),
        _deal_type.team_id == member.team_id,
        or_(SalesDeal.product_id.is_(None), _product.team_id == member.team_id),
        or_(
            SalesDeal.customer_contact_id.is_(None),
            and_(
                _contact.company_id == SalesDeal.customer_company_id,
                _contact_owner.team_id == member.team_id,
                _contact_owner.active.is_(True),
                _contact_owner.role_code.in_(("member", "manager")),
            ),
        ),
    ]
    if member.role_code == "member":
        conditions.extend(
            (
                SalesDeal.owner_member_id == member.id,
                or_(SalesDeal.customer_contact_id.is_(None), _contact.owner_member_id == member.id),
            )
        )
    elif owner_ids is not None:
        conditions.append(SalesDeal.owner_member_id.in_(owner_ids))
    return conditions


def _read_entities():
    return (
        SalesDeal,
        _owner.display_name,
        _company.name,
        _company.region_code,
        _contact.name,
        _product.name,
        _pipeline.name,
        _pipeline.status_code,
        _pipeline.is_default,
        _stage.stage_code,
        _stage.name,
        _stage.tone,
        _stage.phase_code,
        _stage.outcome_code,
        _stage.position,
        _deal_type.code,
        _deal_type.name,
    )


def _sales_deal_read(
    sales_deal: SalesDeal,
    owner_display_name: str,
    company_name: str,
    company_region_code: str | None,
    contact_name: str | None,
    product_name: str | None,
    pipeline_name: str,
    pipeline_status_code: str,
    pipeline_is_default: bool,
    stage_code: str,
    stage_name: str,
    stage_tone: str,
    stage_phase_code: str,
    stage_outcome_code: str,
    stage_position: int,
    deal_type_code: str,
    deal_type_name: str,
) -> SalesDealRead:
    return SalesDealRead(
        id=sales_deal.id,
        deal_no=sales_deal.deal_no,
        customer_company_id=sales_deal.customer_company_id,
        customer_company_name=company_name,
        customer_company_region_code=company_region_code,
        customer_contact_id=sales_deal.customer_contact_id,
        customer_contact_name=contact_name,
        owner_member_id=sales_deal.owner_member_id,
        owner_display_name=owner_display_name,
        product_id=sales_deal.product_id,
        product_name=product_name,
        sales_pipeline_id=sales_deal.sales_pipeline_id,
        sales_pipeline_name=pipeline_name,
        sales_pipeline_status_code=pipeline_status_code,
        sales_pipeline_is_default=pipeline_is_default,
        sales_pipeline_stage_id=sales_deal.sales_pipeline_stage_id,
        sales_pipeline_stage_code=stage_code,
        sales_pipeline_stage_name=stage_name,
        sales_pipeline_stage_tone=stage_tone,
        sales_pipeline_stage_phase_code=stage_phase_code,
        sales_pipeline_stage_outcome_code=stage_outcome_code,
        sales_pipeline_stage_position=stage_position,
        sales_deal_type_id=sales_deal.sales_deal_type_id,
        deal_type_code=deal_type_code,
        deal_type_name=deal_type_name,
        title=sales_deal.title,
        description=sales_deal.description,
        deal_amount=sales_deal.deal_amount,
        opened_on=sales_deal.opened_on,
        closed_on=sales_deal.closed_on,
        quote_no=sales_deal.quote_no,
        quote_issued_on=sales_deal.quote_issued_on,
        quote_valid_until=sales_deal.quote_valid_until,
        contract_no=sales_deal.contract_no,
        contract_signed_on=sales_deal.contract_signed_on,
        contract_ends_on=sales_deal.contract_ends_on,
        warranty_terms=sales_deal.warranty_terms,
        expected_delivery_at=_seoul(sales_deal.expected_delivery_at),
        memo=sales_deal.memo,
        stage_position=sales_deal.stage_position,
        created_at=_seoul(sales_deal.created_at),
        updated_at=_seoul(sales_deal.updated_at),
    )


def _pipeline_read(pipeline: SalesPipeline) -> SalesPipelineRead:
    return SalesPipelineRead(
        id=pipeline.id,
        name=pipeline.name,
        description=pipeline.description,
        status_code=pipeline.status_code,
        is_default=pipeline.is_default,
        published_at=_seoul(pipeline.published_at),
        archived_at=_seoul(pipeline.archived_at),
        created_at=_seoul(pipeline.created_at),
        updated_at=_seoul(pipeline.updated_at),
    )


def _validate_sales_deal_dates(sales_deal: SalesDeal) -> None:
    invalid = (
        (sales_deal.closed_on is not None and sales_deal.closed_on < sales_deal.opened_on)
        or (
            sales_deal.quote_issued_on is not None
            and sales_deal.quote_issued_on < sales_deal.opened_on
        )
        or (
            sales_deal.quote_valid_until is not None
            and (
                sales_deal.quote_issued_on is None
                or sales_deal.quote_valid_until < sales_deal.quote_issued_on
            )
        )
        or (
            sales_deal.contract_signed_on is not None
            and sales_deal.contract_signed_on < sales_deal.opened_on
        )
        or (
            sales_deal.contract_ends_on is not None
            and (
                sales_deal.contract_signed_on is None
                or sales_deal.contract_ends_on < sales_deal.contract_signed_on
            )
        )
    )
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_sales_deal_dates",
        )


async def _owner_filter(
    db: AsyncSession,
    member: Member,
    requested: list[UUID] | None,
) -> tuple[UUID, ...] | None:
    if requested is None:
        return None
    if member.role_code != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="scope_not_allowed")
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="scope_not_allowed")
    return owner_ids


async def _team_pipeline(
    db: AsyncSession,
    member: Member,
    sales_pipeline_id: UUID,
    *,
    published_only: bool = False,
) -> SalesPipeline:
    statuses = ("published",) if published_only else ("published", "archived")
    result = await db.execute(
        select(SalesPipeline).where(
            SalesPipeline.id == sales_pipeline_id,
            SalesPipeline.team_id == member.team_id,
            SalesPipeline.status_code.in_(statuses),
        )
    )
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sales_pipeline_not_found",
        )
    return pipeline


async def _team_stage(
    db: AsyncSession,
    member: Member,
    sales_pipeline_stage_id: UUID,
) -> SalesPipelineStage:
    result = await db.execute(
        select(SalesPipelineStage)
        .join(SalesPipeline, SalesPipelineStage.sales_pipeline_id == SalesPipeline.id)
        .where(
            SalesPipelineStage.id == sales_pipeline_stage_id,
            SalesPipeline.team_id == member.team_id,
            SalesPipeline.status_code == "published",
        )
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sales_pipeline_stage_not_found",
        )
    return stage


async def _stage_filter(
    db: AsyncSession,
    member: Member,
    requested: list[UUID] | None,
) -> tuple[UUID, ...] | None:
    if requested is None:
        return None
    stage_ids = tuple(dict.fromkeys(requested))
    result = await db.execute(
        select(SalesPipelineStage.id)
        .join(SalesPipeline, SalesPipelineStage.sales_pipeline_id == SalesPipeline.id)
        .where(
            SalesPipelineStage.id.in_(stage_ids),
            SalesPipeline.team_id == member.team_id,
            SalesPipeline.status_code.in_(("published", "archived")),
        )
    )
    if set(result.scalars().all()) != set(stage_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sales_pipeline_stage_not_found",
        )
    return stage_ids


async def _sales_deal_row(db: AsyncSession, member: Member, sales_deal_id: UUID):
    result = await db.execute(
        _joined_select(*_read_entities()).where(
            SalesDeal.id == sales_deal_id,
            *_scope(member),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal_not_found")
    return row


async def _locked_sales_deal(
    db: AsyncSession,
    member: Member,
    sales_deal_id: UUID,
) -> SalesDeal:
    conditions = [
        SalesDeal.id == sales_deal_id,
        SalesDeal.team_id == member.team_id,
        SalesDeal.deleted_at.is_(None),
        SalesPipeline.team_id == member.team_id,
        SalesPipeline.status_code == "published",
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)
    result = await db.execute(
        select(SalesDeal)
        .join(Member, SalesDeal.owner_member_id == Member.id)
        .join(SalesPipeline, SalesDeal.sales_pipeline_id == SalesPipeline.id)
        .where(*conditions)
        .with_for_update(of=SalesDeal)
    )
    sales_deal = result.scalar_one_or_none()
    if sales_deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal_not_found")
    return sales_deal


async def _team_company(
    db: AsyncSession,
    member: Member,
    company_id: UUID,
) -> CustomerCompany:
    result = await db.execute(
        select(CustomerCompany).where(
            CustomerCompany.id == company_id,
            CustomerCompany.team_id == member.team_id,
        )
    )
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_company_not_found",
        )
    return company


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    return product


async def _team_deal_type(
    db: AsyncSession,
    member: Member,
    deal_type_code: str,
) -> SalesDealType:
    result = await db.execute(
        select(SalesDealType).where(
            SalesDealType.team_id == member.team_id,
            SalesDealType.code == deal_type_code,
            SalesDealType.deleted_at.is_(None),
        )
    )
    deal_type = result.scalar_one_or_none()
    if deal_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="sales_deal_type_code_not_found",
        )
    return deal_type


async def _team_contact(
    db: AsyncSession,
    member: Member,
    customer_contact_id: UUID,
    company_id: UUID,
    owner_member_id: UUID,
) -> CustomerContact:
    result = await db.execute(
        select(CustomerContact)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .where(
            CustomerContact.id == customer_contact_id,
            CustomerCompany.team_id == member.team_id,
            Member.team_id == member.team_id,
            Member.active.is_(True),
            Member.role_code.in_(("member", "manager")),
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_contact_not_found",
        )
    if contact.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="contact_company_mismatch",
        )
    if contact.owner_member_id != owner_member_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="contact_owner_mismatch",
        )
    return contact


async def _stage_sales_deals(
    db: AsyncSession,
    member: Member,
    stage_ids: tuple[UUID, ...],
) -> list[SalesDeal]:
    # ponytail: 작은 보드는 단계 전체를 재번호한다. 느려지면 sparse rank로 바꾼다.
    conditions = [
        SalesDeal.team_id == member.team_id,
        SalesDeal.sales_pipeline_stage_id.in_(stage_ids),
        SalesDeal.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)
    result = await db.execute(
        select(SalesDeal)
        .where(*conditions)
        .order_by(
            SalesDeal.sales_pipeline_stage_id,
            SalesDeal.stage_position,
            SalesDeal.id,
        )
        .with_for_update(of=SalesDeal)
    )
    return list(result.scalars().all())


async def _next_deal_no(db: AsyncSession, member: Member, year: int) -> str:
    team_result = await db.execute(
        select(Team.id).where(Team.id == member.team_id).with_for_update(of=Team)
    )
    if team_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team_not_found")

    prefix = f"SL-DL-{year}-"
    numbers_result = await db.execute(
        select(SalesDeal.deal_no).where(
            SalesDeal.team_id == member.team_id,
            SalesDeal.deal_no.like(f"{prefix}%"),
        )
    )
    numbers = []
    for deal_no in numbers_result.scalars().all():
        suffix = deal_no.removeprefix(prefix)
        if len(suffix) == 4 and suffix.isascii() and suffix.isdigit():
            numbers.append(int(suffix))
    next_number = max(numbers, default=0) + 1
    if next_number > 9_999:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="sales_deal_number_exhausted",
        )
    return f"{prefix}{next_number:04d}"


@router.get("/sales-pipelines", response_model=list[SalesPipelineRead])
async def list_sales_pipelines(
    member: CurrentMember,
    db: DbSession,
) -> list[SalesPipelineRead]:
    result = await db.execute(
        select(SalesPipeline)
        .where(
            SalesPipeline.team_id == member.team_id,
            SalesPipeline.status_code.in_(("published", "archived")),
        )
        .order_by(SalesPipeline.is_default.desc(), SalesPipeline.name, SalesPipeline.id)
    )
    return [_pipeline_read(pipeline) for pipeline in result.scalars().all()]


@router.get(
    "/sales-pipelines/{sales_pipeline_id}/stages",
    response_model=list[SalesPipelineStageRead],
)
async def list_sales_pipeline_stages(
    sales_pipeline_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> list[SalesPipelineStage]:
    await _team_pipeline(db, member, sales_pipeline_id)
    result = await db.execute(
        select(SalesPipelineStage)
        .where(SalesPipelineStage.sales_pipeline_id == sales_pipeline_id)
        .order_by(SalesPipelineStage.position, SalesPipelineStage.id)
    )
    return list(result.scalars().all())


@router.get("/sales-deal-types", response_model=list[SalesDealTypeRead])
async def list_sales_deal_types(
    member: CurrentMember,
    db: DbSession,
) -> list[SalesDealType]:
    result = await db.execute(
        select(SalesDealType)
        .where(
            SalesDealType.team_id == member.team_id,
            SalesDealType.deleted_at.is_(None),
        )
        .order_by(SalesDealType.position, SalesDealType.id)
    )
    return list(result.scalars().all())


@router.get("/products", response_model=ProductPage)
async def list_products(
    page: Annotated[ProductPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> ProductPage:
    scope = [Product.team_id == member.team_id, Product.active.is_(True)]
    if page.q is not None:
        scope.append(Product.name.ilike(_contains(page.q), escape="\\"))
    total_result = await db.execute(select(func.count(Product.id)).where(*scope))
    total = total_result.scalar_one()
    products_result = await db.execute(
        select(Product)
        .where(*scope)
        .order_by(Product.name, Product.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    products = list(products_result.scalars().all())
    has_more = page.skip + len(products) < total
    return ProductPage(
        items=products,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(products) if has_more else None,
    )


@router.get("/sales-deals", response_model=SalesDealPage)
async def list_sales_deals(
    page: Annotated[SalesDealPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> SalesDealPage:
    owner_ids = await _owner_filter(db, member, page.owner_member_id)
    stage_ids = await _stage_filter(db, member, page.sales_pipeline_stage_id)
    if page.sales_pipeline_id is not None:
        await _team_pipeline(db, member, page.sales_pipeline_id)

    scope = _scope(member, owner_ids)
    if page.sales_pipeline_id is not None:
        scope.append(SalesDeal.sales_pipeline_id == page.sales_pipeline_id)
    if stage_ids is not None:
        scope.append(SalesDeal.sales_pipeline_stage_id.in_(stage_ids))
    if page.phase_code is not None:
        scope.append(_stage.phase_code.in_(tuple(dict.fromkeys(page.phase_code))))
    if page.start_date is not None:
        scope.append(SalesDeal.opened_on >= page.start_date)
    if page.end_date is not None:
        scope.append(SalesDeal.opened_on <= page.end_date)
    if page.q is not None:
        pattern = _contains(page.q)
        scope.append(
            or_(
                SalesDeal.deal_no.ilike(pattern, escape="\\"),
                SalesDeal.title.ilike(pattern, escape="\\"),
                SalesDeal.memo.ilike(pattern, escape="\\"),
                _company.name.ilike(pattern, escape="\\"),
                _contact.name.ilike(pattern, escape="\\"),
                _product.name.ilike(pattern, escape="\\"),
                _owner.display_name.ilike(pattern, escape="\\"),
                _pipeline.name.ilike(pattern, escape="\\"),
                _stage.name.ilike(pattern, escape="\\"),
                _deal_type.name.ilike(pattern, escape="\\"),
            )
        )

    total_result = await db.execute(_joined_select(func.count(SalesDeal.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(*_read_entities())
        .where(*scope)
        .order_by(SalesDeal.opened_on.desc(), SalesDeal.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    items = [_sales_deal_read(*row) for row in rows_result.all()]
    has_more = page.skip + len(items) < total
    return SalesDealPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/sales-deals/{sales_deal_id}", response_model=SalesDealRead)
async def get_sales_deal(
    sales_deal_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> SalesDealRead:
    return _sales_deal_read(*await _sales_deal_row(db, member, sales_deal_id))


@router.post(
    "/sales-deals",
    response_model=SalesDealRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sales_deal(
    payload: SalesDealCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> SalesDealRead:
    try:
        company = await _team_company(db, member, payload.customer_company_id)
        product = await _team_product(db, member, payload.product_id)
        pipeline = await _team_pipeline(
            db,
            member,
            payload.sales_pipeline_id,
            published_only=True,
        )
        stage = await _team_stage(db, member, payload.sales_pipeline_stage_id)
        if stage.sales_pipeline_id != pipeline.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="sales_pipeline_stage_pipeline_mismatch",
            )
        deal_type = await _team_deal_type(db, member, payload.deal_type_code)
        if payload.customer_contact_id is not None:
            await _team_contact(
                db,
                member,
                payload.customer_contact_id,
                company.id,
                member.id,
            )
        deal_no = await _next_deal_no(db, member, payload.opened_on.year)

        now = datetime.now(UTC)
        for existing in await _stage_sales_deals(db, member, (stage.id,)):
            existing.stage_position += 1
            existing.updated_at = now

        values = payload.model_dump(
            exclude={"title", "deal_type_code", "sales_pipeline_id", "sales_pipeline_stage_id"}
        )
        sales_deal = SalesDeal(
            id=uuid4(),
            team_id=member.team_id,
            deal_no=deal_no,
            owner_member_id=member.id,
            sales_pipeline_id=pipeline.id,
            sales_pipeline_stage_id=stage.id,
            sales_deal_type_id=deal_type.id,
            title=payload.title or f"{company.name} {product.name}",
            closed_on=datetime.now(_SEOUL).date() if stage.phase_code == "closed" else None,
            stage_position=0,
            deleted_at=None,
            **values,
        )
        _validate_sales_deal_dates(sales_deal)
        db.add(sales_deal)
        await db.flush()
        read = _sales_deal_read(*await _sales_deal_row(db, member, sales_deal.id))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="sales_deal_conflict",
        ) from exc
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/sales-deals/{sales_deal.id}"
    return read


@router.patch("/sales-deals/{sales_deal_id}", response_model=SalesDealRead)
async def update_sales_deal(
    sales_deal_id: UUID,
    payload: SalesDealPatch,
    member: CurrentMember,
    db: DbSession,
) -> SalesDealRead:
    try:
        sales_deal = await _locked_sales_deal(db, member, sales_deal_id)
        values = payload.model_dump(exclude_unset=True, exclude={"deal_type_code"})
        company_id = values.get("customer_company_id", sales_deal.customer_company_id)
        customer_contact_id = values.get("customer_contact_id", sales_deal.customer_contact_id)
        relation_changed = "customer_company_id" in values or "product_id" in values
        old_row = await _sales_deal_row(db, member, sales_deal_id) if relation_changed else None

        company = None
        if "customer_company_id" in values:
            company = await _team_company(db, member, company_id)
        product = None
        if "product_id" in values:
            product = await _team_product(db, member, values["product_id"])
        if customer_contact_id is not None and (
            "customer_contact_id" in values or "customer_company_id" in values
        ):
            await _team_contact(
                db,
                member,
                customer_contact_id,
                company_id,
                sales_deal.owner_member_id,
            )
        if "deal_type_code" in payload.model_fields_set:
            assert payload.deal_type_code is not None
            deal_type = await _team_deal_type(db, member, payload.deal_type_code)
            values["sales_deal_type_id"] = deal_type.id
        if old_row is not None and "title" not in values:
            old_company_name = old_row[2]
            old_product_name = old_row[5]
            if (
                old_product_name is not None
                and sales_deal.title == f"{old_company_name} {old_product_name}"
            ):
                values["title"] = (
                    f"{company.name if company is not None else old_company_name} "
                    f"{product.name if product is not None else old_product_name}"
                )

        for field_name, value in values.items():
            setattr(sales_deal, field_name, value)
        sales_deal.updated_at = datetime.now(UTC)
        _validate_sales_deal_dates(sales_deal)
        await db.flush()
        read = _sales_deal_read(*await _sales_deal_row(db, member, sales_deal_id))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="sales_deal_conflict",
        ) from exc
    except Exception:
        await db.rollback()
        raise
    return read


@router.post("/sales-deals/{sales_deal_id}/move", response_model=SalesDealRead)
async def move_sales_deal(
    sales_deal_id: UUID,
    payload: SalesDealMove,
    member: CurrentMember,
    db: DbSession,
) -> SalesDealRead:
    try:
        target_stage = await _team_stage(db, member, payload.sales_pipeline_stage_id)
        sales_deal = await _locked_sales_deal(db, member, sales_deal_id)
        if sales_deal.sales_pipeline_stage_id != payload.expected_sales_pipeline_stage_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )
        if target_stage.sales_pipeline_id != sales_deal.sales_pipeline_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="sales_pipeline_stage_pipeline_mismatch",
            )

        source_stage_id = sales_deal.sales_pipeline_stage_id
        stage_ids = tuple(dict.fromkeys((source_stage_id, target_stage.id)))
        sales_deals = await _stage_sales_deals(db, member, stage_ids)
        source = [
            item
            for item in sales_deals
            if item.sales_pipeline_stage_id == source_stage_id and item.id != sales_deal.id
        ]
        target = (
            source.copy()
            if source_stage_id == target_stage.id
            else [item for item in sales_deals if item.sales_pipeline_stage_id == target_stage.id]
        )
        if payload.stage_position > len(target):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_sales_deal_position",
            )

        target.insert(payload.stage_position, sales_deal)
        now = datetime.now(UTC)
        for position, item in enumerate(source):
            item.stage_position = position
            item.updated_at = now
        for position, item in enumerate(target):
            item.sales_pipeline_stage_id = target_stage.id
            item.stage_position = position
            item.updated_at = now

        today = datetime.now(_SEOUL).date()
        sales_deal.closed_on = today if target_stage.phase_code == "closed" else None
        if (
            target_stage.phase_code == "contract"
            and target_stage.outcome_code == "confirmed"
            and sales_deal.contract_signed_on is None
        ):
            sales_deal.contract_signed_on = today

        _validate_sales_deal_dates(sales_deal)
        await db.flush()
        read = _sales_deal_read(*await _sales_deal_row(db, member, sales_deal_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.delete("/sales-deals/{sales_deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sales_deal(
    sales_deal_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    try:
        sales_deal = await _locked_sales_deal(db, member, sales_deal_id)
        now = datetime.now(UTC)
        sales_deal.deleted_at = now
        sales_deal.updated_at = now
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
