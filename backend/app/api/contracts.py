from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.crm import CustomerCompany, CustomerContact
from app.models.sales import Contract, PipelineStage, Product
from app.models.workspace import Member, Team
from app.schemas.contracts import (
    ContractCreate,
    ContractMove,
    ContractPage,
    ContractPageParams,
    ContractPatch,
    ContractRead,
    PipelineStageParams,
    PipelineStageRead,
    ProductPage,
    ProductPageParams,
)

router = APIRouter(tags=["contracts"])

_SEOUL = ZoneInfo("Asia/Seoul")
_owner = aliased(Member)
_company = aliased(CustomerCompany)
_contact = aliased(CustomerContact)
_contact_owner = aliased(Member)
_product = aliased(Product)
_stage = aliased(PipelineStage)


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(Contract)
        .join(_owner, Contract.owner_member_id == _owner.id)
        .join(_company, Contract.customer_company_id == _company.id)
        .outerjoin(_contact, Contract.contact_id == _contact.id)
        .outerjoin(_contact_owner, _contact.owner_member_id == _contact_owner.id)
        .outerjoin(_product, Contract.product_id == _product.id)
        .join(_stage, Contract.stage_id == _stage.id)
    )


def _scope(member: Member, owner_ids: tuple[UUID, ...] | None = None):
    conditions = [
        Contract.team_id == member.team_id,
        Contract.deleted_at.is_(None),
        _owner.team_id == member.team_id,
        _owner.active.is_(True),
        _owner.role_code.in_(("member", "manager")),
        _company.team_id == member.team_id,
        _stage.team_id == member.team_id,
        or_(Contract.product_id.is_(None), _product.team_id == member.team_id),
        or_(
            Contract.contact_id.is_(None),
            and_(
                _contact.company_id == Contract.customer_company_id,
                _contact_owner.team_id == member.team_id,
                _contact_owner.active.is_(True),
                _contact_owner.role_code.in_(("member", "manager")),
            ),
        ),
    ]
    if member.role_code == "member":
        conditions.extend(
            (
                Contract.owner_member_id == member.id,
                or_(Contract.contact_id.is_(None), _contact.owner_member_id == member.id),
            )
        )
    elif owner_ids is not None:
        conditions.append(Contract.owner_member_id.in_(owner_ids))
    return conditions


def _seoul(value: datetime | None) -> datetime | None:
    return None if value is None else value.astimezone(_SEOUL)


def _contract_read(
    contract: Contract,
    owner_display_name: str,
    company_name: str,
    company_region_code: str | None,
    contact_name: str | None,
    product_name: str | None,
    stage_name: str,
    stage_tone: str,
    stage_outcome_code: str,
    stage_position: int,
) -> ContractRead:
    return ContractRead(
        id=contract.id,
        contract_no=contract.contract_no,
        customer_company_id=contract.customer_company_id,
        customer_company_name=company_name,
        customer_company_region_code=company_region_code,
        contact_id=contract.contact_id,
        contact_name=contact_name,
        owner_member_id=contract.owner_member_id,
        owner_display_name=owner_display_name,
        product_id=contract.product_id,
        product_name=product_name,
        stage_id=contract.stage_id,
        stage_name=stage_name,
        stage_tone=stage_tone,
        stage_outcome_code=stage_outcome_code,
        stage_position=stage_position,
        title=contract.title,
        description=contract.description,
        contract_type=contract.contract_type,
        amount=contract.amount,
        contract_date=contract.contract_date,
        ends_on=contract.ends_on,
        warranty_terms=contract.warranty_terms,
        expected_delivery_at=_seoul(contract.expected_delivery_at),
        memo=contract.memo,
        position=contract.position,
        created_at=_seoul(contract.created_at),
        updated_at=_seoul(contract.updated_at),
    )


def _read_entities():
    return (
        Contract,
        _owner.display_name,
        _company.name,
        _company.region_code,
        _contact.name,
        _product.name,
        _stage.name,
        _stage.tone,
        _stage.outcome_code,
        _stage.position,
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


async def _stage_filter(
    db: AsyncSession,
    member: Member,
    requested: list[UUID] | None,
) -> tuple[UUID, ...] | None:
    if requested is None:
        return None
    stage_ids = tuple(dict.fromkeys(requested))
    result = await db.execute(
        select(PipelineStage.id).where(
            PipelineStage.id.in_(stage_ids),
            PipelineStage.team_id == member.team_id,
        )
    )
    if set(result.scalars().all()) != set(stage_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pipeline_stage_not_found",
        )
    return stage_ids


async def _contract_row(db: AsyncSession, member: Member, contract_id: UUID):
    result = await db.execute(
        _joined_select(*_read_entities()).where(
            Contract.id == contract_id,
            *_scope(member),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="contract_not_found",
        )
    return row


async def _locked_contract(
    db: AsyncSession,
    member: Member,
    contract_id: UUID,
) -> Contract:
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
        select(Contract)
        .join(Member, Contract.owner_member_id == Member.id)
        .where(*conditions)
        .with_for_update(of=Contract)
    )
    contract = result.scalar_one_or_none()
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="contract_not_found",
        )
    return contract


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="product_not_found",
        )
    return product


async def _team_stage(
    db: AsyncSession,
    member: Member,
    stage_id: UUID,
) -> PipelineStage:
    result = await db.execute(
        select(PipelineStage).where(
            PipelineStage.id == stage_id,
            PipelineStage.team_id == member.team_id,
        )
    )
    stage = result.scalar_one_or_none()
    if stage is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pipeline_stage_not_found",
        )
    return stage


async def _team_contact(
    db: AsyncSession,
    member: Member,
    contact_id: UUID,
    company_id: UUID,
    owner_member_id: UUID,
) -> CustomerContact:
    result = await db.execute(
        select(CustomerContact)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .where(
            CustomerContact.id == contact_id,
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


async def _stage_contracts(
    db: AsyncSession,
    member: Member,
    stage_ids: tuple[UUID, ...],
) -> list[Contract]:
    # ponytail: 단계 전체 잠금·재번호는 작은 보드용이다. 느려지면 sparse rank로 바꾼다.
    conditions = [
        Contract.team_id == member.team_id,
        Contract.stage_id.in_(stage_ids),
        Contract.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(Contract.owner_member_id == member.id)
    result = await db.execute(
        select(Contract)
        .where(*conditions)
        .order_by(Contract.stage_id, Contract.position, Contract.id)
        .with_for_update(of=Contract)
    )
    return list(result.scalars().all())


async def _next_contract_no(
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

    prefix = f"SL-CT-{year}-"
    numbers_result = await db.execute(
        select(Contract.contract_no).where(
            Contract.team_id == member.team_id,
            Contract.contract_no.like(f"{prefix}%"),
        )
    )
    numbers = []
    for contract_no in numbers_result.scalars().all():
        suffix = contract_no.removeprefix(prefix)
        if len(suffix) == 4 and suffix.isascii() and suffix.isdigit():
            numbers.append(int(suffix))
    next_number = max(numbers, default=0) + 1
    if next_number > 9_999:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="contract_number_exhausted",
        )
    return f"{prefix}{next_number:04d}"


@router.get("/pipeline-stages", response_model=list[PipelineStageRead])
async def list_pipeline_stages(
    _params: Annotated[PipelineStageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> list[PipelineStage]:
    result = await db.execute(
        select(PipelineStage)
        .where(PipelineStage.team_id == member.team_id)
        .order_by(PipelineStage.position, PipelineStage.id)
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


@router.get("/contracts", response_model=ContractPage)
async def list_contracts(
    page: Annotated[ContractPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> ContractPage:
    owner_ids = await _owner_filter(db, member, page.owner_member_id)
    stage_ids = await _stage_filter(db, member, page.stage_id)
    scope = _scope(member, owner_ids)
    if stage_ids is not None:
        scope.append(Contract.stage_id.in_(stage_ids))
    if page.start_date is not None:
        scope.append(Contract.contract_date >= page.start_date)
    if page.end_date is not None:
        scope.append(Contract.contract_date <= page.end_date)
    if page.q is not None:
        pattern = _contains(page.q)
        scope.append(
            or_(
                Contract.contract_no.ilike(pattern, escape="\\"),
                Contract.title.ilike(pattern, escape="\\"),
                Contract.memo.ilike(pattern, escape="\\"),
                _company.name.ilike(pattern, escape="\\"),
                _contact.name.ilike(pattern, escape="\\"),
                _product.name.ilike(pattern, escape="\\"),
                _owner.display_name.ilike(pattern, escape="\\"),
            )
        )

    total_result = await db.execute(_joined_select(func.count(Contract.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(*_read_entities())
        .where(*scope)
        .order_by(Contract.contract_date.desc(), Contract.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    items = [_contract_read(*row) for row in rows_result.all()]
    has_more = page.skip + len(items) < total
    return ContractPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/contracts/{contract_id}", response_model=ContractRead)
async def get_contract(
    contract_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> ContractRead:
    return _contract_read(*await _contract_row(db, member, contract_id))


@router.post(
    "/contracts",
    response_model=ContractRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_contract(
    payload: ContractCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> ContractRead:
    try:
        company = await _team_company(db, member, payload.customer_company_id)
        product = await _team_product(db, member, payload.product_id)
        stage = await _team_stage(db, member, payload.stage_id)
        contact = (
            None
            if payload.contact_id is None
            else await _team_contact(
                db,
                member,
                payload.contact_id,
                company.id,
                member.id,
            )
        )
        contract_no = await _next_contract_no(db, member, payload.contract_date.year)

        now = datetime.now(UTC)
        for existing in await _stage_contracts(db, member, (stage.id,)):
            existing.position += 1
            existing.updated_at = now

        values = payload.model_dump(exclude={"title"})
        contract = Contract(
            id=uuid4(),
            team_id=member.team_id,
            contract_no=contract_no,
            owner_member_id=member.id,
            title=payload.title or f"{company.name} {product.name}",
            position=0,
            deleted_at=None,
            **values,
        )
        db.add(contract)
        await db.flush()
        read = _contract_read(
            contract,
            member.display_name,
            company.name,
            company.region_code,
            None if contact is None else contact.name,
            product.name,
            stage.name,
            stage.tone,
            stage.outcome_code,
            stage.position,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/contracts/{contract.id}"
    return read


@router.patch("/contracts/{contract_id}", response_model=ContractRead)
async def update_contract(
    contract_id: UUID,
    payload: ContractPatch,
    member: CurrentMember,
    db: DbSession,
) -> ContractRead:
    try:
        contract = await _locked_contract(db, member, contract_id)
        values = payload.model_dump(exclude_unset=True)
        company_id = values.get("customer_company_id", contract.customer_company_id)
        contact_id = values.get("contact_id", contract.contact_id)
        relation_changed = "customer_company_id" in values or "product_id" in values
        old_row = await _contract_row(db, member, contract_id) if relation_changed else None

        company = None
        if "customer_company_id" in values:
            company = await _team_company(db, member, company_id)
        product = None
        if "product_id" in values:
            product = await _team_product(db, member, values["product_id"])
        if contact_id is not None and ("contact_id" in values or "customer_company_id" in values):
            await _team_contact(
                db,
                member,
                contact_id,
                company_id,
                contract.owner_member_id,
            )
        if old_row is not None and "title" not in values:
            old_company_name = old_row[2]
            old_product_name = old_row[5]
            if (
                old_product_name is not None
                and contract.title == f"{old_company_name} {old_product_name}"
            ):
                values["title"] = (
                    f"{company.name if company is not None else old_company_name} "
                    f"{product.name if product is not None else old_product_name}"
                )

        for field_name, value in values.items():
            setattr(contract, field_name, value)
        contract.updated_at = datetime.now(UTC)
        await db.flush()
        read = _contract_read(*await _contract_row(db, member, contract_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.post("/contracts/{contract_id}/move", response_model=ContractRead)
async def move_contract(
    contract_id: UUID,
    payload: ContractMove,
    member: CurrentMember,
    db: DbSession,
) -> ContractRead:
    try:
        target_stage = await _team_stage(db, member, payload.stage_id)
        contract = await _locked_contract(db, member, contract_id)
        if contract.stage_id != payload.expected_stage_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )

        source_stage_id = contract.stage_id
        stage_ids = tuple(dict.fromkeys((source_stage_id, target_stage.id)))
        contracts = await _stage_contracts(db, member, stage_ids)
        source = [
            item
            for item in contracts
            if item.stage_id == source_stage_id and item.id != contract.id
        ]
        target = (
            source
            if source_stage_id == target_stage.id
            else [item for item in contracts if item.stage_id == target_stage.id]
        )
        if payload.position > len(target):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid_contract_position",
            )

        target.insert(payload.position, contract)
        now = datetime.now(UTC)
        for position, item in enumerate(source):
            item.position = position
            item.updated_at = now
        for position, item in enumerate(target):
            item.stage_id = target_stage.id
            item.position = position
            item.updated_at = now

        await db.flush()
        read = _contract_read(*await _contract_row(db, member, contract_id))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    try:
        contract = await _locked_contract(db, member, contract_id)
        now = datetime.now(UTC)
        contract.deleted_at = now
        contract.updated_at = now
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
