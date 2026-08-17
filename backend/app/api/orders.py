from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.crm import CustomerCompany
from app.models.sales import Contract, Product, PurchaseOrder, PurchaseOrderItem
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
)

router = APIRouter(tags=["orders"])

_SEOUL = ZoneInfo("Asia/Seoul")
_owner = aliased(Member)
_company = aliased(CustomerCompany)
_contract = aliased(Contract)
_search_item = aliased(PurchaseOrderItem)
_search_product = aliased(Product)


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(PurchaseOrder)
        .join(_owner, PurchaseOrder.owner_member_id == _owner.id)
        .join(_company, PurchaseOrder.customer_company_id == _company.id)
        .outerjoin(_contract, PurchaseOrder.contract_id == _contract.id)
    )


def _items_are_team_scoped(team_id: UUID):
    item = aliased(PurchaseOrderItem)
    product = aliased(Product)
    invalid_item = (
        select(1)
        .select_from(item)
        .outerjoin(product, item.product_id == product.id)
        .where(
            item.order_id == PurchaseOrder.id,
            or_(product.id.is_(None), product.team_id != team_id),
        )
        .exists()
    )
    return ~invalid_item


def _scope(member: Member, owner_ids: tuple[UUID, ...] | None = None):
    conditions = [
        PurchaseOrder.team_id == member.team_id,
        PurchaseOrder.deleted_at.is_(None),
        _owner.team_id == member.team_id,
        _owner.active.is_(True),
        _owner.role_code.in_(("member", "manager")),
        _company.team_id == member.team_id,
        or_(
            PurchaseOrder.contract_id.is_(None),
            and_(
                _contract.team_id == member.team_id,
                _contract.deleted_at.is_(None),
                _contract.customer_company_id == PurchaseOrder.customer_company_id,
                _contract.owner_member_id == PurchaseOrder.owner_member_id,
            ),
        ),
        _items_are_team_scoped(member.team_id),
    ]
    if member.role_code == "member":
        conditions.append(PurchaseOrder.owner_member_id == member.id)
    elif owner_ids is not None:
        conditions.append(PurchaseOrder.owner_member_id.in_(owner_ids))
    return conditions


def _read_entities():
    return (
        PurchaseOrder,
        _owner.display_name,
        _company.name,
        _contract.contract_no,
    )


def _seoul(value: datetime) -> datetime:
    return value.astimezone(_SEOUL)


def _order_read(
    order: PurchaseOrder,
    owner_display_name: str,
    company_name: str,
    contract_no: str | None,
    items: list[OrderItemRead],
) -> OrderRead:
    return OrderRead(
        id=order.id,
        order_no=order.order_no,
        contract_id=order.contract_id,
        contract_no=contract_no,
        customer_company_id=order.customer_company_id,
        customer_company_name=company_name,
        owner_member_id=order.owner_member_id,
        owner_display_name=owner_display_name,
        supplier_name=order.supplier_name,
        stage_code=order.stage_code,
        ordered_on=order.ordered_on,
        due_on=order.due_on,
        expected_receipt_on=order.expected_receipt_on,
        memo=order.memo,
        items=items,
        created_at=_seoul(order.created_at),
        updated_at=_seoul(order.updated_at),
    )


async def _items_by_order_ids(
    db: AsyncSession,
    member: Member,
    order_ids: list[UUID],
) -> dict[UUID, list[OrderItemRead]]:
    items_by_order = {order_id: [] for order_id in order_ids}
    if not order_ids:
        return items_by_order
    result = await db.execute(
        select(PurchaseOrderItem, Product.name)
        .join(Product, PurchaseOrderItem.product_id == Product.id)
        .where(
            PurchaseOrderItem.order_id.in_(order_ids),
            Product.team_id == member.team_id,
        )
        .order_by(PurchaseOrderItem.order_id, PurchaseOrderItem.position, PurchaseOrderItem.id)
    )
    for item, product_name in result.all():
        items_by_order[item.order_id].append(
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


async def _order_row(db: AsyncSession, member: Member, order_id: UUID):
    result = await db.execute(
        _joined_select(*_read_entities()).where(
            PurchaseOrder.id == order_id,
            *_scope(member),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order_not_found",
        )
    return row


async def _locked_order(db: AsyncSession, member: Member, order_id: UUID) -> PurchaseOrder:
    conditions = [
        PurchaseOrder.id == order_id,
        PurchaseOrder.team_id == member.team_id,
        PurchaseOrder.deleted_at.is_(None),
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
        CustomerCompany.team_id == member.team_id,
        or_(
            PurchaseOrder.contract_id.is_(None),
            and_(
                Contract.team_id == member.team_id,
                Contract.deleted_at.is_(None),
                Contract.customer_company_id == PurchaseOrder.customer_company_id,
                Contract.owner_member_id == PurchaseOrder.owner_member_id,
            ),
        ),
        _items_are_team_scoped(member.team_id),
    ]
    if member.role_code == "member":
        conditions.append(PurchaseOrder.owner_member_id == member.id)
    result = await db.execute(
        select(PurchaseOrder)
        .join(Member, PurchaseOrder.owner_member_id == Member.id)
        .join(CustomerCompany, PurchaseOrder.customer_company_id == CustomerCompany.id)
        .outerjoin(Contract, PurchaseOrder.contract_id == Contract.id)
        .where(*conditions)
        .with_for_update(of=PurchaseOrder)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order_not_found",
        )
    return order


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


async def _team_contract(
    db: AsyncSession,
    member: Member,
    contract_id: UUID,
) -> tuple[Contract, str]:
    conditions = [
        Contract.id == contract_id,
        Contract.team_id == member.team_id,
        Contract.deleted_at.is_(None),
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(Contract.owner_member_id == member.id)
    result = await db.execute(
        select(Contract, Member.display_name)
        .join(Member, Contract.owner_member_id == Member.id)
        .where(*conditions)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="contract_not_found",
        )
    return row


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="product_not_found",
        )
    return products


async def _next_order_no(
    db: AsyncSession,
    member: Member,
    year: int,
) -> str:
    team_result = await db.execute(
        select(Team.id).where(Team.id == member.team_id).with_for_update(of=Team)
    )
    if team_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="team_not_found",
        )

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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="order_number_exhausted",
        )
    return f"{prefix}{next_number:04d}"


def _new_items(
    order_id: UUID,
    values: list[OrderItemWrite],
) -> list[PurchaseOrderItem]:
    return [
        PurchaseOrderItem(
            id=uuid4(),
            order_id=order_id,
            product_id=value.product_id,
            quantity=value.quantity,
            unit_price=value.unit_price,
            position=position,
        )
        for position, value in enumerate(values)
    ]


def _item_reads(
    items: list[PurchaseOrderItem],
    products: dict[UUID, Product],
) -> list[OrderItemRead]:
    return [
        OrderItemRead(
            id=item.id,
            product_id=item.product_id,
            product_name=products[item.product_id].name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            position=item.position,
        )
        for item in items
    ]


@router.get("/orders", response_model=OrderPage)
async def list_orders(
    page: Annotated[OrderPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> OrderPage:
    owner_ids = await _owner_filter(db, member, page.owner_member_id)
    scope = _scope(member, owner_ids)
    if page.supplier_name is not None:
        scope.append(PurchaseOrder.supplier_name == page.supplier_name)
    if page.stage_code is not None:
        scope.append(PurchaseOrder.stage_code.in_(tuple(dict.fromkeys(page.stage_code))))
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
                _search_item.order_id == PurchaseOrder.id,
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
                _contract.contract_no.ilike(pattern, escape="\\"),
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


@router.get("/orders/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> OrderRead:
    row = await _order_row(db, member, order_id)
    item_map = await _items_by_order_ids(db, member, [order_id])
    return _order_read(*row, item_map[order_id])


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
        company = await _team_company(db, member, payload.customer_company_id)
        contract = None
        contract_no = None
        owner_id = member.id
        owner_display_name = member.display_name
        if payload.contract_id is not None:
            contract, owner_display_name = await _team_contract(db, member, payload.contract_id)
            if contract.customer_company_id != company.id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="contract_company_mismatch",
                )
            contract_no = contract.contract_no
            owner_id = contract.owner_member_id

        products = await _team_products(db, member, payload.items)
        order_no = await _next_order_no(db, member, payload.ordered_on.year)
        order = PurchaseOrder(
            id=uuid4(),
            team_id=member.team_id,
            order_no=order_no,
            contract_id=payload.contract_id,
            customer_company_id=payload.customer_company_id,
            owner_member_id=owner_id,
            supplier_name=payload.supplier_name,
            stage_code=payload.stage_code,
            ordered_on=payload.ordered_on,
            due_on=payload.due_on,
            expected_receipt_on=payload.expected_receipt_on,
            memo=payload.memo,
            deleted_at=None,
        )
        order_items = _new_items(order.id, payload.items)
        db.add(order)
        for item in order_items:
            db.add(item)
        await db.flush()
        read = _order_read(
            order,
            owner_display_name,
            company.name,
            contract_no,
            _item_reads(order_items, products),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/orders/{order.id}"
    return read


@router.patch("/orders/{order_id}", response_model=OrderRead)
async def update_order(
    order_id: UUID,
    payload: OrderPatch,
    member: CurrentMember,
    db: DbSession,
) -> OrderRead:
    try:
        order = await _locked_order(db, member, order_id)
        values = payload.model_dump(exclude_unset=True, exclude={"items"})
        company_id = values.get("customer_company_id", order.customer_company_id)
        if "customer_company_id" in values:
            await _team_company(db, member, company_id)

        contract_id = values.get("contract_id", order.contract_id)
        if contract_id is not None:
            contract, _owner_display_name = await _team_contract(db, member, contract_id)
            if contract.customer_company_id != company_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="contract_company_mismatch",
                )
            order.owner_member_id = contract.owner_member_id

        for field_name, value in values.items():
            setattr(order, field_name, value)

        if "items" in payload.model_fields_set:
            assert payload.items is not None
            await _team_products(db, member, payload.items)
            await db.execute(
                delete(PurchaseOrderItem).where(PurchaseOrderItem.order_id == order.id)
            )
            for item in _new_items(order.id, payload.items):
                db.add(item)

        order.updated_at = datetime.now(UTC)
        await db.flush()
        row = await _order_row(db, member, order_id)
        item_map = await _items_by_order_ids(db, member, [order_id])
        read = _order_read(*row, item_map[order_id])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.post("/orders/{order_id}/move", response_model=OrderRead)
async def move_order(
    order_id: UUID,
    payload: OrderMove,
    member: CurrentMember,
    db: DbSession,
) -> OrderRead:
    try:
        order = await _locked_order(db, member, order_id)
        if order.stage_code != payload.expected_stage_code:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )
        order.stage_code = payload.stage_code
        order.updated_at = datetime.now(UTC)
        await db.flush()
        row = await _order_row(db, member, order_id)
        item_map = await _items_by_order_ids(db, member, [order_id])
        read = _order_read(*row, item_map[order_id])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    try:
        order = await _locked_order(db, member, order_id)
        now = datetime.now(UTC)
        order.deleted_at = now
        order.updated_at = now
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
