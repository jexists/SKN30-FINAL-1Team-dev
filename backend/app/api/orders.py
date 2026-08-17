from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.configuration import PurchaseOrderStatus
from app.models.crm import CustomerCompany
from app.models.sales import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesDeal,
    SalesPipeline,
    SalesPipelineStage,
)
from app.models.workspace import Member, Team
from app.schemas.orders import (
    OrderCreate,
    OrderItemRead,
    OrderItemWrite,
    OrderMove,
    OrderPage,
    OrderPageParams,
    OrderPatch,
    OrderRead,
    PurchaseOrderStatusRead,
)

router = APIRouter(tags=["orders"])

_SEOUL = ZoneInfo("Asia/Seoul")
_owner = aliased(Member)
_company = aliased(CustomerCompany)
_sales_deal = aliased(SalesDeal)
_sales_stage = aliased(SalesPipelineStage)
_order_status = aliased(PurchaseOrderStatus)
_search_item = aliased(PurchaseOrderItem)
_search_product = aliased(Product)


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _seoul(value: datetime) -> datetime:
    return value.astimezone(_SEOUL)


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(PurchaseOrder)
        .join(_sales_deal, PurchaseOrder.sales_deal_id == _sales_deal.id)
        .join(_sales_stage, _sales_deal.sales_pipeline_stage_id == _sales_stage.id)
        .join(_owner, _sales_deal.owner_member_id == _owner.id)
        .join(_company, _sales_deal.customer_company_id == _company.id)
        .join(_order_status, PurchaseOrder.purchase_order_status_id == _order_status.id)
    )


def _items_are_team_scoped(team_id: UUID):
    item = aliased(PurchaseOrderItem)
    product = aliased(Product)
    invalid_item = (
        select(1)
        .select_from(item)
        .outerjoin(product, item.product_id == product.id)
        .where(
            item.purchase_order_id == PurchaseOrder.id,
            or_(product.id.is_(None), product.team_id != team_id),
        )
        .exists()
    )
    return ~invalid_item


def _scope(member: Member, owner_ids: tuple[UUID, ...] | None = None):
    conditions = [
        PurchaseOrder.team_id == member.team_id,
        PurchaseOrder.deleted_at.is_(None),
        _sales_deal.team_id == member.team_id,
        _sales_deal.deleted_at.is_(None),
        _owner.team_id == member.team_id,
        _owner.active.is_(True),
        _owner.role_code.in_(("member", "manager")),
        _company.team_id == member.team_id,
        _order_status.team_id == member.team_id,
        _items_are_team_scoped(member.team_id),
    ]
    if member.role_code == "member":
        conditions.append(_sales_deal.owner_member_id == member.id)
    elif owner_ids is not None:
        conditions.append(_sales_deal.owner_member_id.in_(owner_ids))
    return conditions


def _read_entities():
    return (
        PurchaseOrder,
        _sales_deal.deal_no,
        _sales_deal.customer_company_id,
        _company.name,
        _sales_deal.owner_member_id,
        _owner.display_name,
        _order_status.code,
        _order_status.name,
        _order_status.tone,
        _order_status.outcome_code,
        _order_status.position,
    )


def _order_read(
    order: PurchaseOrder,
    deal_no: str,
    customer_company_id: UUID,
    company_name: str,
    owner_member_id: UUID,
    owner_display_name: str,
    stage_code: str,
    stage_name: str,
    stage_tone: str,
    stage_outcome_code: str,
    stage_position: int,
    items: list[OrderItemRead],
) -> OrderRead:
    return OrderRead(
        id=order.id,
        order_no=order.order_no,
        sales_deal_id=order.sales_deal_id,
        deal_no=deal_no,
        customer_company_id=customer_company_id,
        customer_company_name=company_name,
        owner_member_id=owner_member_id,
        owner_display_name=owner_display_name,
        supplier_name=order.supplier_name,
        purchase_order_status_id=order.purchase_order_status_id,
        stage_code=stage_code,
        stage_name=stage_name,
        stage_tone=stage_tone,
        stage_outcome_code=stage_outcome_code,
        stage_position=stage_position,
        ordered_on=order.ordered_on,
        due_on=order.due_on,
        expected_receipt_on=order.expected_receipt_on,
        memo=order.memo,
        items=items,
        created_at=_seoul(order.created_at),
        updated_at=_seoul(order.updated_at),
    )


def _validate_order_dates(order: PurchaseOrder) -> None:
    if order.due_on < order.ordered_on or order.expected_receipt_on < order.ordered_on:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="invalid_order_dates",
        )


async def _items_by_order_ids(
    db: AsyncSession,
    member: Member,
    order_ids: list[UUID],
) -> dict[UUID, list[OrderItemRead]]:
    items_by_order = {purchase_order_id: [] for purchase_order_id in order_ids}
    if not order_ids:
        return items_by_order
    result = await db.execute(
        select(PurchaseOrderItem, Product.name)
        .join(Product, PurchaseOrderItem.product_id == Product.id)
        .where(
            PurchaseOrderItem.purchase_order_id.in_(order_ids),
            Product.team_id == member.team_id,
        )
        .order_by(
            PurchaseOrderItem.purchase_order_id,
            PurchaseOrderItem.position,
            PurchaseOrderItem.id,
        )
    )
    for item, product_name in result.all():
        items_by_order[item.purchase_order_id].append(
            OrderItemRead(
                id=item.id,
                product_id=item.product_id,
                product_name=product_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                position=item.position,
            )
        )
    return items_by_order


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


async def _order_row(
    db: AsyncSession,
    member: Member,
    purchase_order_id: UUID,
    *,
    order_phase_only: bool = False,
):
    scope = _scope(member)
    if order_phase_only:
        scope.append(_sales_stage.phase_code == "order")
    result = await db.execute(
        _joined_select(*_read_entities()).where(
            PurchaseOrder.id == purchase_order_id,
            *scope,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order_not_found")
    return row


async def _locked_order(
    db: AsyncSession,
    member: Member,
    purchase_order_id: UUID,
) -> tuple[PurchaseOrder, str]:
    conditions = [
        PurchaseOrder.id == purchase_order_id,
        PurchaseOrder.team_id == member.team_id,
        PurchaseOrder.deleted_at.is_(None),
        SalesDeal.team_id == member.team_id,
        SalesDeal.deleted_at.is_(None),
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
        CustomerCompany.team_id == member.team_id,
        PurchaseOrderStatus.team_id == member.team_id,
        _items_are_team_scoped(member.team_id),
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)
    result = await db.execute(
        select(PurchaseOrder, PurchaseOrderStatus.code)
        .join(SalesDeal, PurchaseOrder.sales_deal_id == SalesDeal.id)
        .join(Member, SalesDeal.owner_member_id == Member.id)
        .join(CustomerCompany, SalesDeal.customer_company_id == CustomerCompany.id)
        .join(PurchaseOrderStatus, PurchaseOrder.purchase_order_status_id == PurchaseOrderStatus.id)
        .where(*conditions)
        .with_for_update(of=PurchaseOrder)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="order_not_found")
    return row


async def _team_sales_deal(
    db: AsyncSession,
    member: Member,
    sales_deal_id: UUID,
    *,
    lock: bool = False,
) -> tuple[SalesDeal, str, str]:
    conditions = [
        SalesDeal.id == sales_deal_id,
        SalesDeal.team_id == member.team_id,
        SalesDeal.deleted_at.is_(None),
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
        SalesPipeline.team_id == member.team_id,
        SalesPipeline.status_code == "published",
        SalesPipelineStage.id == SalesDeal.sales_pipeline_stage_id,
        SalesPipelineStage.sales_pipeline_id == SalesDeal.sales_pipeline_id,
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)
    statement = (
        select(SalesDeal, Member.display_name, SalesPipelineStage.phase_code)
        .join(Member, SalesDeal.owner_member_id == Member.id)
        .join(SalesPipeline, SalesDeal.sales_pipeline_id == SalesPipeline.id)
        .join(
            SalesPipelineStage,
            SalesDeal.sales_pipeline_stage_id == SalesPipelineStage.id,
        )
        .where(*conditions)
    )
    if lock:
        statement = statement.with_for_update(of=SalesDeal)
    result = await db.execute(statement)
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal_not_found")
    return row


async def _active_order_status(
    db: AsyncSession,
    member: Member,
    stage_code: str,
) -> PurchaseOrderStatus:
    result = await db.execute(
        select(PurchaseOrderStatus).where(
            PurchaseOrderStatus.team_id == member.team_id,
            PurchaseOrderStatus.code == stage_code,
            PurchaseOrderStatus.deleted_at.is_(None),
        )
    )
    order_status = result.scalar_one_or_none()
    if order_status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="purchase_order_status_code_not_found",
        )
    return order_status


async def _team_products(
    db: AsyncSession,
    member: Member,
    items: list[OrderItemWrite],
) -> dict[UUID, Product]:
    product_ids = tuple(dict.fromkeys(item.product_id for item in items))
    result = await db.execute(
        select(Product).where(
            Product.id.in_(product_ids),
            Product.team_id == member.team_id,
            Product.active.is_(True),
        )
    )
    products = {product.id: product for product in result.scalars().all()}
    if set(products) != set(product_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    return products


async def _move_deal_to_first_order_stage(
    db: AsyncSession,
    member: Member,
    sales_deal: SalesDeal,
    current_phase_code: str,
) -> None:
    if current_phase_code == "order":
        return
    target_result = await db.execute(
        select(SalesPipelineStage)
        .where(
            SalesPipelineStage.sales_pipeline_id == sales_deal.sales_pipeline_id,
            SalesPipelineStage.phase_code == "order",
        )
        .order_by(SalesPipelineStage.position, SalesPipelineStage.id)
        .limit(1)
    )
    target_stage = target_result.scalar_one_or_none()
    if target_stage is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="sales_pipeline_order_stage_not_found",
        )

    # ponytail: 작은 보드는 단계 전체를 재번호한다. 느려지면 sparse rank로 바꾼다.
    stage_ids = (sales_deal.sales_pipeline_stage_id, target_stage.id)
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
    deals = list(result.scalars().all())
    source = [
        item
        for item in deals
        if item.sales_pipeline_stage_id == sales_deal.sales_pipeline_stage_id
        and item.id != sales_deal.id
    ]
    target = [item for item in deals if item.sales_pipeline_stage_id == target_stage.id]
    target.insert(0, sales_deal)
    now = datetime.now(UTC)
    for position, item in enumerate(source):
        item.stage_position = position
        item.updated_at = now
    for position, item in enumerate(target):
        item.sales_pipeline_stage_id = target_stage.id
        item.stage_position = position
        item.updated_at = now
    sales_deal.closed_on = None


async def _next_order_no(db: AsyncSession, member: Member, year: int) -> str:
    team_result = await db.execute(
        select(Team.id).where(Team.id == member.team_id).with_for_update(of=Team)
    )
    if team_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team_not_found")

    prefix = f"SL-PO-{year}-"
    numbers_result = await db.execute(
        select(PurchaseOrder.order_no).where(
            PurchaseOrder.team_id == member.team_id,
            PurchaseOrder.order_no.like(f"{prefix}%"),
        )
    )
    numbers = []
    for order_no in numbers_result.scalars().all():
        suffix = order_no.removeprefix(prefix)
        if len(suffix) == 4 and suffix.isascii() and suffix.isdigit():
            numbers.append(int(suffix))
    next_number = max(numbers, default=0) + 1
    if next_number > 9_999:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="order_number_exhausted")
    return f"{prefix}{next_number:04d}"


def _new_items(
    purchase_order_id: UUID,
    values: list[OrderItemWrite],
) -> list[PurchaseOrderItem]:
    return [
        PurchaseOrderItem(
            id=uuid4(),
            purchase_order_id=purchase_order_id,
            product_id=value.product_id,
            quantity=value.quantity,
            unit_price=value.unit_price,
            position=position,
        )
        for position, value in enumerate(values)
    ]


@router.get("/purchase-order-statuses", response_model=list[PurchaseOrderStatusRead])
async def list_purchase_order_statuses(
    member: CurrentMember,
    db: DbSession,
) -> list[PurchaseOrderStatus]:
    result = await db.execute(
        select(PurchaseOrderStatus)
        .where(
            PurchaseOrderStatus.team_id == member.team_id,
            PurchaseOrderStatus.deleted_at.is_(None),
        )
        .order_by(PurchaseOrderStatus.position, PurchaseOrderStatus.id)
    )
    return list(result.scalars().all())


@router.get("/orders", response_model=OrderPage)
async def list_orders(
    page: Annotated[OrderPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> OrderPage:
    owner_ids = await _owner_filter(db, member, page.owner_member_id)
    scope = _scope(member, owner_ids)
    scope.append(_sales_stage.phase_code == "order")
    if page.supplier_name is not None:
        scope.append(PurchaseOrder.supplier_name == page.supplier_name)
    if page.stage_code is not None:
        scope.append(_order_status.code.in_(tuple(dict.fromkeys(page.stage_code))))
    if page.start_date is not None:
        scope.append(PurchaseOrder.ordered_on >= page.start_date)
    if page.end_date is not None:
        scope.append(PurchaseOrder.ordered_on <= page.end_date)
    if page.q is not None:
        pattern = _contains(page.q)
        product_match = (
            select(1)
            .select_from(_search_item)
            .join(_search_product, _search_item.product_id == _search_product.id)
            .where(
                _search_item.purchase_order_id == PurchaseOrder.id,
                _search_product.team_id == member.team_id,
                _search_product.name.ilike(pattern, escape="\\"),
            )
            .exists()
        )
        scope.append(
            or_(
                PurchaseOrder.order_no.ilike(pattern, escape="\\"),
                PurchaseOrder.supplier_name.ilike(pattern, escape="\\"),
                PurchaseOrder.memo.ilike(pattern, escape="\\"),
                _company.name.ilike(pattern, escape="\\"),
                _sales_deal.deal_no.ilike(pattern, escape="\\"),
                _order_status.name.ilike(pattern, escape="\\"),
                product_match,
            )
        )

    total_result = await db.execute(_joined_select(func.count(PurchaseOrder.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(*_read_entities())
        .where(*scope)
        .order_by(PurchaseOrder.ordered_on.desc(), PurchaseOrder.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    rows = rows_result.all()
    item_map = await _items_by_order_ids(db, member, [row[0].id for row in rows])
    items = [_order_read(*row, item_map[row[0].id]) for row in rows]
    has_more = page.skip + len(items) < total
    return OrderPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/orders/{purchase_order_id}", response_model=OrderRead)
async def get_order(
    purchase_order_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> OrderRead:
    row = await _order_row(db, member, purchase_order_id, order_phase_only=True)
    item_map = await _items_by_order_ids(db, member, [purchase_order_id])
    return _order_read(*row, item_map[purchase_order_id])


@router.post(
    "/orders",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    payload: OrderCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> OrderRead:
    try:
        sales_deal, _owner_display_name, phase_code = await _team_sales_deal(
            db,
            member,
            payload.sales_deal_id,
            lock=True,
        )
        order_status = await _active_order_status(db, member, payload.stage_code)
        products = await _team_products(db, member, payload.items)
        await _move_deal_to_first_order_stage(db, member, sales_deal, phase_code)
        order_no = await _next_order_no(db, member, payload.ordered_on.year)
        order = PurchaseOrder(
            id=uuid4(),
            team_id=member.team_id,
            order_no=order_no,
            sales_deal_id=sales_deal.id,
            supplier_name=payload.supplier_name,
            purchase_order_status_id=order_status.id,
            ordered_on=payload.ordered_on,
            due_on=payload.due_on,
            expected_receipt_on=payload.expected_receipt_on,
            memo=payload.memo,
            deleted_at=None,
        )
        _validate_order_dates(order)
        order_items = _new_items(order.id, payload.items)
        db.add(order)
        for item in order_items:
            db.add(item)
        await db.flush()
        row = await _order_row(db, member, order.id)
        items = [
            OrderItemRead(
                id=item.id,
                product_id=item.product_id,
                product_name=products[item.product_id].name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                position=item.position,
            )
            for item in order_items
        ]
        read = _order_read(*row, items)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="order_conflict",
        ) from exc
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/orders/{order.id}"
    return read


@router.patch("/orders/{purchase_order_id}", response_model=OrderRead)
async def update_order(
    purchase_order_id: UUID,
    payload: OrderPatch,
    member: CurrentMember,
    db: DbSession,
) -> OrderRead:
    try:
        order, _stage_code = await _locked_order(db, member, purchase_order_id)
        values = payload.model_dump(exclude_unset=True, exclude={"items"})
        if "sales_deal_id" in values:
            sales_deal, _owner_display_name, _phase_code = await _team_sales_deal(
                db,
                member,
                values["sales_deal_id"],
            )
            values["sales_deal_id"] = sales_deal.id

        for field_name, value in values.items():
            setattr(order, field_name, value)

        if "items" in payload.model_fields_set:
            assert payload.items is not None
            await _team_products(db, member, payload.items)
            await db.execute(
                delete(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == order.id)
            )
            for item in _new_items(order.id, payload.items):
                db.add(item)

        order.updated_at = datetime.now(UTC)
        _validate_order_dates(order)
        await db.flush()
        row = await _order_row(db, member, purchase_order_id)
        item_map = await _items_by_order_ids(db, member, [purchase_order_id])
        read = _order_read(*row, item_map[purchase_order_id])
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="order_conflict",
        ) from exc
    except Exception:
        await db.rollback()
        raise
    return read


@router.post("/orders/{purchase_order_id}/move", response_model=OrderRead)
async def move_order(
    purchase_order_id: UUID,
    payload: OrderMove,
    member: CurrentMember,
    db: DbSession,
) -> OrderRead:
    try:
        order, current_stage_code = await _locked_order(db, member, purchase_order_id)
        if current_stage_code != payload.expected_stage_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )
        order_status = await _active_order_status(db, member, payload.stage_code)
        order.purchase_order_status_id = order_status.id
        order.updated_at = datetime.now(UTC)
        await db.flush()
        row = await _order_row(db, member, purchase_order_id)
        item_map = await _items_by_order_ids(db, member, [purchase_order_id])
        read = _order_read(*row, item_map[purchase_order_id])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.delete("/orders/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    purchase_order_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    try:
        order, _stage_code = await _locked_order(db, member, purchase_order_id)
        now = datetime.now(UTC)
        order.deleted_at = now
        order.updated_at = now
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
