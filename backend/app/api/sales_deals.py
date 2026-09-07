from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession, owner_scope
from app.core.config import settings
from app.models.configuration import (
    ContractStatus,
    PurchaseOrderStatus,
    QuoteStatus,
    SalesDealType,
)
from app.models.crm import CustomerCompany, CustomerContact
from app.models.sales import (
    Product,
    PurchaseOrder,
    SalesDeal,
    SalesDealItem,
    SalesDealParticipant,
    SalesPipeline,
    SalesPipelineStage,
)
from app.models.workspace import Member, Team
from app.schemas.sales_deals import (
    ContractStatusRead,
    ProductCreate,
    ProductImageRead,
    ProductPage,
    ProductPageParams,
    ProductRead,
    QuoteStatusRead,
    SalesDealCreate,
    SalesDealItemRead,
    SalesDealItemWrite,
    SalesDealMove,
    SalesDealPage,
    SalesDealPageParams,
    SalesDealParticipantRead,
    SalesDealPatch,
    SalesDealRead,
    SalesDealTypeRead,
    SalesPipelineRead,
    SalesPipelineStageRead,
)
from app.services import contract_next_meeting_pipeline, storage
from app.services.storage import StorageError
from app.services.upload_guard import UploadRejected, check_image_upload, check_size

router = APIRouter(tags=["sales-deals"])

# 상품 사진 한 장의 상한. 자료실 문서용 upload_max_bytes(50MB)는 사진에 맞지 않는다.
PRODUCT_IMAGE_MAX_BYTES = 5 * 1024 * 1024
PRODUCT_IMAGE_EXPIRES_IN = 300

_SEOUL = ZoneInfo("Asia/Seoul")
_owner = aliased(Member)
_company = aliased(CustomerCompany)
_contact = aliased(CustomerContact)
_contact_owner = aliased(Member)
_product = aliased(Product)
_pipeline = aliased(SalesPipeline)
_stage = aliased(SalesPipelineStage)
_deal_type = aliased(SalesDealType)
_quote_status = aliased(QuoteStatus)
_contract_status = aliased(ContractStatus)
_team = aliased(Team)


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
        .outerjoin(_quote_status, SalesDeal.quote_status_id == _quote_status.id)
        .outerjoin(_contract_status, SalesDeal.contract_status_id == _contract_status.id)
        # 견적서를 내는 쪽(자사) 이름. 딜마다 같은 값이지만 견적 화면이 보여 줘야 한다.
        .join(_team, SalesDeal.team_id == _team.id)
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
        or_(SalesDeal.quote_status_id.is_(None), _quote_status.team_id == member.team_id),
        or_(SalesDeal.contract_status_id.is_(None), _contract_status.team_id == member.team_id),
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
        _quote_status.code,
        _quote_status.name,
        _quote_status.tone,
        _contract_status.code,
        _contract_status.name,
        _contract_status.tone,
        _team.company_name,
        _team.business_no,
        _company.business_no,
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
    quote_status_code: str | None,
    quote_status_name: str | None,
    quote_status_tone: str | None,
    contract_status_code: str | None,
    contract_status_name: str | None,
    contract_status_tone: str | None,
    team_company_name: str | None,
    team_business_no: str | None,
    company_business_no: str | None,
    items: list[SalesDealItemRead] | None = None,
    order_status: tuple[str, str, str] | None = None,
    participants: list[SalesDealParticipantRead] | None = None,
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
        source_code=sales_deal.source_code,
        quote_status_id=sales_deal.quote_status_id,
        quote_status_code=quote_status_code,
        quote_status_name=quote_status_name,
        quote_status_tone=quote_status_tone,
        contract_status_id=sales_deal.contract_status_id,
        contract_status_code=contract_status_code,
        contract_status_name=contract_status_name,
        contract_status_tone=contract_status_tone,
        quote_amount=sales_deal.quote_amount,
        contract_amount=sales_deal.contract_amount,
        quote_delivery_terms=sales_deal.quote_delivery_terms,
        contract_payment_terms=sales_deal.contract_payment_terms,
        contract_late_interest_terms=sales_deal.contract_late_interest_terms,
        team_company_name=team_company_name,
        team_business_no=team_business_no,
        customer_company_business_no=company_business_no,
        items=items or [],
        participants=participants or [],
        order_status_code=None if order_status is None else order_status[0],
        order_status_name=None if order_status is None else order_status[1],
        order_status_tone=None if order_status is None else order_status[2],
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
) -> CustomerContact:
    """딜에 붙일 고객 담당자를 확인한다.

    고를 수 있는 범위는 일정(activities._contact_info)과 같다 — 담당자 역할은 자기 고객만,
    팀장은 팀 전체다. 예전에는 여기에 더해 "딜 주인과 고객 담당자가 같은 사람" 이어야 했는데,
    딜 등록 화면이 담당자를 아예 보내지 않던 동안에는 드러나지 않던 규칙이었다. 담당자를
    필수로 받게 되면서 팀장이 팀원의 고객으로 딜을 만드는 흔한 경우가 전부 막혔고, 같은
    고객으로 일정은 잡히는데 딜은 못 만드는 상태가 되어 두 화면의 범위를 맞췄다.
    """
    result = await db.execute(
        select(CustomerContact)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .where(
            CustomerContact.id == customer_contact_id,
            # 지운 고객은 딜의 담당자로 새로 세울 수 없다.
            CustomerContact.deleted_at.is_(None),
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
    if member.role_code == "member" and contact.owner_member_id != member.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="contact_owner_mismatch",
        )
    return contact


async def _team_quote_status(db: AsyncSession, member: Member, code: str) -> QuoteStatus:
    result = await db.execute(
        select(QuoteStatus).where(
            QuoteStatus.team_id == member.team_id,
            QuoteStatus.code == code,
            QuoteStatus.deleted_at.is_(None),
        )
    )
    quote_status = result.scalar_one_or_none()
    if quote_status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="quote_status_code_not_found",
        )
    return quote_status


async def _team_contract_status(db: AsyncSession, member: Member, code: str) -> ContractStatus:
    result = await db.execute(
        select(ContractStatus).where(
            ContractStatus.team_id == member.team_id,
            ContractStatus.code == code,
            ContractStatus.deleted_at.is_(None),
        )
    )
    contract_status = result.scalar_one_or_none()
    if contract_status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="contract_status_code_not_found",
        )
    return contract_status


async def _team_products(
    db: AsyncSession,
    member: Member,
    items: list[SalesDealItemWrite],
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


async def _team_participants(
    db: AsyncSession,
    member: Member,
    contact_ids: list[UUID],
    company_id: UUID,
) -> None:
    """미팅 대상자는 그 딜의 고객사 사람이어야 한다. 담당자와 달리 소유자는 따지지 않는다."""
    unique_ids = tuple(dict.fromkeys(contact_ids))
    if not unique_ids:
        return
    result = await db.execute(
        select(CustomerContact.id)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .where(
            CustomerContact.id.in_(unique_ids),
            # 지운 고객은 미팅 대상자로 새로 넣을 수 없다.
            CustomerContact.deleted_at.is_(None),
            CustomerContact.company_id == company_id,
            CustomerCompany.team_id == member.team_id,
        )
    )
    if set(result.scalars().all()) != set(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="customer_contact_not_found",
        )


def _new_items(sales_deal_id: UUID, values: list[SalesDealItemWrite]) -> list[SalesDealItem]:
    return [
        SalesDealItem(
            id=uuid4(),
            sales_deal_id=sales_deal_id,
            product_id=value.product_id,
            quantity=value.quantity,
            unit_price=value.unit_price,
            position=position,
        )
        for position, value in enumerate(values)
    ]


async def _items_by_deal_ids(
    db: AsyncSession,
    member: Member,
    deal_ids: list[UUID],
) -> dict[UUID, list[SalesDealItemRead]]:
    items_by_deal: dict[UUID, list[SalesDealItemRead]] = {
        sales_deal_id: [] for sales_deal_id in deal_ids
    }
    if not deal_ids:
        return items_by_deal
    result = await db.execute(
        select(SalesDealItem, Product.name)
        .join(Product, SalesDealItem.product_id == Product.id)
        .where(
            SalesDealItem.sales_deal_id.in_(deal_ids),
            Product.team_id == member.team_id,
        )
        .order_by(SalesDealItem.sales_deal_id, SalesDealItem.position, SalesDealItem.id)
    )
    for item, product_name in result.all():
        items_by_deal[item.sales_deal_id].append(
            SalesDealItemRead(
                id=item.id,
                product_id=item.product_id,
                product_name=product_name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                position=item.position,
            )
        )
    return items_by_deal


async def _participants_by_deal_ids(
    db: AsyncSession,
    member: Member,
    deal_ids: list[UUID],
) -> dict[UUID, list[SalesDealParticipantRead]]:
    by_deal: dict[UUID, list[SalesDealParticipantRead]] = {
        sales_deal_id: [] for sales_deal_id in deal_ids
    }
    if not deal_ids:
        return by_deal
    result = await db.execute(
        select(SalesDealParticipant.sales_deal_id, CustomerContact.id, CustomerContact.name)
        .join(CustomerContact, SalesDealParticipant.customer_contact_id == CustomerContact.id)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .where(
            SalesDealParticipant.sales_deal_id.in_(deal_ids),
            CustomerCompany.team_id == member.team_id,
        )
        .order_by(SalesDealParticipant.sales_deal_id, CustomerContact.name, CustomerContact.id)
    )
    for sales_deal_id, contact_id, contact_name in result.all():
        by_deal[sales_deal_id].append(
            SalesDealParticipantRead(
                customer_contact_id=contact_id,
                customer_contact_name=contact_name,
            )
        )
    return by_deal


async def _order_statuses_by_deal_ids(
    db: AsyncSession,
    member: Member,
    deal_ids: list[UUID],
) -> dict[UUID, tuple[str, str, str]]:
    """딜마다 가장 최근 발주의 상태. join 으로 붙이면 발주 수만큼 딜이 불어난다."""
    if not deal_ids:
        return {}
    result = await db.execute(
        select(
            PurchaseOrder.sales_deal_id,
            PurchaseOrderStatus.code,
            PurchaseOrderStatus.name,
            PurchaseOrderStatus.tone,
        )
        .join(
            PurchaseOrderStatus,
            PurchaseOrder.purchase_order_status_id == PurchaseOrderStatus.id,
        )
        .where(
            PurchaseOrder.sales_deal_id.in_(deal_ids),
            PurchaseOrder.team_id == member.team_id,
            PurchaseOrder.deleted_at.is_(None),
            PurchaseOrderStatus.team_id == member.team_id,
        )
        .order_by(
            PurchaseOrder.sales_deal_id,
            PurchaseOrder.ordered_on.desc(),
            PurchaseOrder.id.desc(),
        )
    )
    latest: dict[UUID, tuple[str, str, str]] = {}
    for sales_deal_id, code, name, tone in result.all():
        latest.setdefault(sales_deal_id, (code, name, tone))
    return latest


async def _read_one(db: AsyncSession, member: Member, sales_deal_id: UUID) -> SalesDealRead:
    row = await _sales_deal_row(db, member, sales_deal_id)
    items = await _items_by_deal_ids(db, member, [sales_deal_id])
    participants = await _participants_by_deal_ids(db, member, [sales_deal_id])
    order_statuses = await _order_statuses_by_deal_ids(db, member, [sales_deal_id])
    return _sales_deal_read(
        *row,
        items=items[sales_deal_id],
        participants=participants[sales_deal_id],
        order_status=order_statuses.get(sales_deal_id),
    )


async def _replace_items(
    db: AsyncSession,
    member: Member,
    sales_deal: SalesDeal,
    values: list[SalesDealItemWrite],
) -> None:
    await _team_products(db, member, values)
    await db.execute(delete(SalesDealItem).where(SalesDealItem.sales_deal_id == sales_deal.id))
    for item in _new_items(sales_deal.id, values):
        db.add(item)
    # 견적금액은 품목의 합이 정답이다. 화면이 보낸 값과 어긋나면 합계를 이긴다.
    sales_deal.quote_amount = sum(value.quantity * value.unit_price for value in values)


async def _replace_participants(
    db: AsyncSession,
    member: Member,
    sales_deal: SalesDeal,
    contact_ids: list[UUID],
) -> None:
    await _team_participants(db, member, contact_ids, sales_deal.customer_company_id)
    await db.execute(
        delete(SalesDealParticipant).where(SalesDealParticipant.sales_deal_id == sales_deal.id)
    )
    for contact_id in dict.fromkeys(contact_ids):
        db.add(
            SalesDealParticipant(
                sales_deal_id=sales_deal.id,
                customer_contact_id=contact_id,
            )
        )


async def _move_deal_to_first_stage_of_phase(
    db: AsyncSession,
    member: Member,
    sales_deal: SalesDeal,
    current_phase_code: str,
    target_phase_code: str,
) -> None:
    """딜을 그 국면의 첫 단계로 옮긴다. 이미 그 국면이면 아무것도 하지 않는다."""
    if current_phase_code == target_phase_code:
        return
    target_result = await db.execute(
        select(SalesPipelineStage)
        .where(
            SalesPipelineStage.sales_pipeline_id == sales_deal.sales_pipeline_id,
            SalesPipelineStage.phase_code == target_phase_code,
        )
        .order_by(SalesPipelineStage.position, SalesPipelineStage.id)
        .limit(1)
    )
    target_stage = target_result.scalar_one_or_none()
    if target_stage is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"sales_pipeline_{target_phase_code}_stage_not_found",
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


@router.get("/quote-statuses", response_model=list[QuoteStatusRead])
async def list_quote_statuses(
    member: CurrentMember,
    db: DbSession,
) -> list[QuoteStatus]:
    result = await db.execute(
        select(QuoteStatus)
        .where(QuoteStatus.team_id == member.team_id, QuoteStatus.deleted_at.is_(None))
        .order_by(QuoteStatus.position, QuoteStatus.id)
    )
    return list(result.scalars().all())


@router.get("/contract-statuses", response_model=list[ContractStatusRead])
async def list_contract_statuses(
    member: CurrentMember,
    db: DbSession,
) -> list[ContractStatus]:
    result = await db.execute(
        select(ContractStatus)
        .where(ContractStatus.team_id == member.team_id, ContractStatus.deleted_at.is_(None))
        .order_by(ContractStatus.position, ContractStatus.id)
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
        pattern = _contains(page.q)
        matches = [
            Product.name.ilike(pattern, escape="\\"),
            Product.memo.ilike(pattern, escape="\\"),
        ]
        if page.q_category_code is not None:
            matches.append(Product.category_code.in_(tuple(dict.fromkeys(page.q_category_code))))
        scope.append(or_(*matches))
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


def _require_manager(member: Member) -> None:
    """상품 마스터는 팀장이 관리한다. 목록 조회는 팀원도 그대로 쓴다."""
    if member.role_code != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager_required")


def _require_storage() -> None:
    if not settings.storage_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage_not_configured",
        )


async def _team_product_for_update(db: AsyncSession, member: Member, product_id: UUID) -> Product:
    product = (
        await db.execute(
            select(Product)
            .where(Product.id == product_id, Product.team_id == member.team_id)
            .with_for_update(of=Product)
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    return product


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> Product:
    _require_manager(member)
    product = Product(
        id=uuid4(),
        team_id=member.team_id,
        # DB 기본값에 기대지 않고 넣는다. 넣은 객체를 그대로 응답으로 쓰기 때문이다.
        active=True,
        name=payload.name,
        category_code=payload.category_code,
        unit_price=payload.unit_price,
        shelf_life_months=payload.shelf_life_months,
        memo=payload.memo,
        image_storage_key=None,
    )
    try:
        db.add(product)
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/products/{product.id}"
    return product


@router.put("/products/{product_id}/image", response_model=ProductRead)
async def upload_product_image(
    product_id: UUID,
    member: CurrentMember,
    db: DbSession,
    upload: Annotated[UploadFile, File()],
) -> Product:
    _require_manager(member)
    _require_storage()
    content = await upload.read()

    try:
        check_size(len(content), PRODUCT_IMAGE_MAX_BYTES)
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

    try:
        product = await _team_product_for_update(db, member, product_id)
        replaced_key = product.image_storage_key
        product.image_storage_key = storage_key
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        # DB 기록이 실패하면 올린 객체를 지워 고아를 남기지 않는다.
        await storage.remove(storage_key=storage_key)
        raise
    if replaced_key is not None:
        await storage.remove(storage_key=replaced_key)
    return product


@router.get("/products/{product_id}/image", response_model=ProductImageRead)
async def get_product_image(
    product_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> ProductImageRead:
    """짧게 사는 사진 주소. 요청마다 팀 권한을 다시 확인한다.

    ponytail: 목록이 행마다 한 번씩 부르므로 저장소 호출이 N번이다.
    상품 수가 커지면 한 번에 여러 건을 발급하는 방식으로 바꾼다.
    """
    _require_storage()
    product = (
        await db.execute(
            select(Product).where(Product.id == product_id, Product.team_id == member.team_id)
        )
    ).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_not_found")
    if product.image_storage_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="product_image_not_found")

    try:
        url = await storage.signed_url(
            storage_key=product.image_storage_key,
            expires_in=PRODUCT_IMAGE_EXPIRES_IN,
        )
    except StorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    return ProductImageRead(url=url, expires_in=PRODUCT_IMAGE_EXPIRES_IN)


@router.get("/sales-deals", response_model=SalesDealPage)
async def list_sales_deals(
    page: Annotated[SalesDealPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> SalesDealPage:
    owner_ids = await owner_scope(db, member, page.owner_member_id)
    stage_ids = await _stage_filter(db, member, page.sales_pipeline_stage_id)
    if page.sales_pipeline_id is not None:
        await _team_pipeline(db, member, page.sales_pipeline_id)

    # 단계를 뺀 나머지 조건. 단계 탭 옆 건수가 이 범위를 센다. 단계까지 넣고 세면
    # 고른 탭에만 숫자가 남아 다른 단계에 무엇이 얼마나 있는지 알 수 없다.
    scope = _scope(member, owner_ids)
    if page.customer_company_id is not None:
        scope.append(SalesDeal.customer_company_id == page.customer_company_id)
    if page.sales_pipeline_id is not None:
        scope.append(SalesDeal.sales_pipeline_id == page.sales_pipeline_id)
    if page.sales_pipeline_status_code is not None:
        scope.append(
            _pipeline.status_code.in_(tuple(dict.fromkeys(page.sales_pipeline_status_code)))
        )
    if page.phase_code is not None:
        scope.append(_stage.phase_code.in_(tuple(dict.fromkeys(page.phase_code))))
    if page.outcome_code is not None:
        scope.append(_stage.outcome_code.in_(tuple(dict.fromkeys(page.outcome_code))))
    # 견적·계약이 붙었는지로 거른다. phase_code 로 거르면 계약으로 넘어간 딜이 견적번호를
    # 그대로 들고 있는데도 견적현황에서 사라진다.
    if page.has_quote is not None:
        scope.append(
            SalesDeal.quote_status_id.isnot(None)
            if page.has_quote
            else SalesDeal.quote_status_id.is_(None)
        )
    if page.has_contract is not None:
        scope.append(
            SalesDeal.contract_status_id.isnot(None)
            if page.has_contract
            else SalesDeal.contract_status_id.is_(None)
        )
    # 계약 종료일 범위. 대시보드 계약갱신 카드가 세는 조건과 같아야 타일 숫자와 목록
    # 총계가 맞는다. 종료일이 없는 딜은 이 비교에서 스스로 빠진다.
    if page.contract_ends_from is not None:
        scope.append(SalesDeal.contract_ends_on >= page.contract_ends_from)
    if page.contract_ends_to is not None:
        scope.append(SalesDeal.contract_ends_on <= page.contract_ends_to)
    basis = {
        "opened": SalesDeal.opened_on,
        "quote_issued": func.coalesce(SalesDeal.quote_issued_on, SalesDeal.opened_on),
        "contract_signed": func.coalesce(SalesDeal.contract_signed_on, SalesDeal.opened_on),
    }[page.date_basis]
    if page.start_date is not None:
        scope.append(basis >= page.start_date)
    if page.end_date is not None:
        scope.append(basis <= page.end_date)
    if page.q is not None:
        pattern = _contains(page.q)
        scope.append(
            or_(
                SalesDeal.deal_no.ilike(pattern, escape="\\"),
                # 견적·계약 화면은 그 국면의 번호로 찾는다. 번호가 아직 없으면 딜 번호를
                # 쓰므로 둘 다 본다.
                SalesDeal.quote_no.ilike(pattern, escape="\\"),
                SalesDeal.contract_no.ilike(pattern, escape="\\"),
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

    # 탭으로 고른 조건과, 탭 옆 건수를 셀 열. 견적·계약 목록은 파이프라인 단계가 아니라
    # 그 국면의 상태로 탭을 세운다. 고른 탭 자신만 세는 범위에서 빼야 나머지 탭 숫자가
    # 0 으로 죽지 않는다.
    by_stage = [] if stage_ids is None else [SalesDeal.sales_pipeline_stage_id.in_(stage_ids)]
    by_quote_status = (
        []
        if page.quote_status_id is None
        else [SalesDeal.quote_status_id.in_(tuple(dict.fromkeys(page.quote_status_id)))]
    )
    by_contract_status = (
        []
        if page.contract_status_id is None
        else [SalesDeal.contract_status_id.in_(tuple(dict.fromkeys(page.contract_status_id)))]
    )
    if page.has_quote:
        counts_column = SalesDeal.quote_status_id
        by_tab = by_quote_status
        scope = [*scope, *by_stage, *by_contract_status]
    elif page.has_contract:
        counts_column = SalesDeal.contract_status_id
        by_tab = by_contract_status
        scope = [*scope, *by_stage, *by_quote_status]
    else:
        counts_column = SalesDeal.sales_pipeline_stage_id
        by_tab = by_stage
        scope = [*scope, *by_quote_status, *by_contract_status]
    rows_scope = [*scope, *by_tab]

    total_result = await db.execute(_joined_select(func.count(SalesDeal.id)).where(*rows_scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(*_read_entities())
        .where(*rows_scope)
        .order_by(SalesDeal.opened_on.desc(), SalesDeal.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    rows = rows_result.all()
    deal_ids = [row[0].id for row in rows]
    items_by_deal = await _items_by_deal_ids(db, member, deal_ids)
    participants_by_deal = await _participants_by_deal_ids(db, member, deal_ids)
    order_statuses = await _order_statuses_by_deal_ids(db, member, deal_ids)
    items = [
        _sales_deal_read(
            *row,
            items=items_by_deal[row[0].id],
            participants=participants_by_deal[row[0].id],
            order_status=order_statuses.get(row[0].id),
        )
        for row in rows
    ]
    # 탭 옆 건수. 고른 탭만 빼고 센다.
    counts_result = await db.execute(
        _joined_select(counts_column, func.count(SalesDeal.id))
        .where(*scope)
        .group_by(counts_column)
    )
    counts = {str(key): count for key, count in counts_result.all()}
    has_more = page.skip + len(items) < total
    return SalesDealPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
        counts=counts,
    )


@router.get("/sales-deals/{sales_deal_id}", response_model=SalesDealRead)
async def get_sales_deal(
    sales_deal_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> SalesDealRead:
    return await _read_one(db, member, sales_deal_id)


@router.post(
    "/sales-deals",
    response_model=SalesDealRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sales_deal(
    payload: SalesDealCreate,
    response: Response,
    background: BackgroundTasks,
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
            await _team_contact(db, member, payload.customer_contact_id, company.id)
        quote_status = (
            None
            if payload.quote_status_code is None
            else await _team_quote_status(db, member, payload.quote_status_code)
        )
        contract_status = (
            None
            if payload.contract_status_code is None
            else await _team_contract_status(db, member, payload.contract_status_code)
        )
        if payload.participant_contact_ids is not None:
            await _team_participants(db, member, payload.participant_contact_ids, company.id)
        deal_no = await _next_deal_no(db, member, payload.opened_on.year)

        now = datetime.now(UTC)
        for existing in await _stage_sales_deals(db, member, (stage.id,)):
            existing.stage_position += 1
            existing.updated_at = now

        values = payload.model_dump(
            exclude={
                "title",
                "deal_type_code",
                "sales_pipeline_id",
                "sales_pipeline_stage_id",
                "quote_status_code",
                "contract_status_code",
                "items",
                "participant_contact_ids",
            }
        )
        if payload.items is not None:
            values["quote_amount"] = sum(item.quantity * item.unit_price for item in payload.items)
        sales_deal = SalesDeal(
            id=uuid4(),
            team_id=member.team_id,
            deal_no=deal_no,
            owner_member_id=member.id,
            sales_pipeline_id=pipeline.id,
            sales_pipeline_stage_id=stage.id,
            sales_deal_type_id=deal_type.id,
            quote_status_id=None if quote_status is None else quote_status.id,
            contract_status_id=None if contract_status is None else contract_status.id,
            title=payload.title or f"{company.name} {product.name}",
            closed_on=datetime.now(_SEOUL).date() if stage.phase_code == "closed" else None,
            stage_position=0,
            deleted_at=None,
            **values,
        )
        _validate_sales_deal_dates(sales_deal)
        db.add(sales_deal)
        await db.flush()
        if payload.items is not None:
            for item in _new_items(sales_deal.id, payload.items):
                db.add(item)
        if payload.participant_contact_ids is not None:
            for contact_id in dict.fromkeys(payload.participant_contact_ids):
                db.add(
                    SalesDealParticipant(
                        sales_deal_id=sales_deal.id,
                        customer_contact_id=contact_id,
                    )
                )
        await db.flush()
        read = await _read_one(db, member, sales_deal.id)
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
    # 새 딜이 생겼다는 신호로 트리거한다(계약에이전트_설계.md 3장).
    contract_next_meeting_pipeline.queue(
        background, sales_deal.id, {"sales_deal_id": str(sales_deal.id)}
    )
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
        values = payload.model_dump(
            exclude_unset=True,
            exclude={
                "deal_type_code",
                "quote_status_code",
                "contract_status_code",
                "items",
                "participant_contact_ids",
            },
        )
        had_quote = sales_deal.quote_status_id is not None
        had_contract = sales_deal.contract_status_id is not None
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
            await _team_contact(db, member, customer_contact_id, company_id)
        if "deal_type_code" in payload.model_fields_set:
            assert payload.deal_type_code is not None
            deal_type = await _team_deal_type(db, member, payload.deal_type_code)
            values["sales_deal_type_id"] = deal_type.id
        if "quote_status_code" in payload.model_fields_set:
            values["quote_status_id"] = (
                None
                if payload.quote_status_code is None
                else (await _team_quote_status(db, member, payload.quote_status_code)).id
            )
        if "contract_status_code" in payload.model_fields_set:
            values["contract_status_id"] = (
                None
                if payload.contract_status_code is None
                else (await _team_contract_status(db, member, payload.contract_status_code)).id
            )
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

        if "items" in payload.model_fields_set:
            assert payload.items is not None
            await _replace_items(db, member, sales_deal, payload.items)
        if "participant_contact_ids" in payload.model_fields_set:
            assert payload.participant_contact_ids is not None
            await _replace_participants(db, member, sales_deal, payload.participant_contact_ids)
        elif "customer_company_id" in values:
            # 고객사를 바꾸면 남아 있던 대상자는 다른 회사 사람이다. 대표 담당자를
            # 비우는 것과 같은 이유로 여기서 지운다.
            await db.execute(
                delete(SalesDealParticipant).where(
                    SalesDealParticipant.sales_deal_id == sales_deal.id
                )
            )

        # 견적·계약을 처음 걸면 딜도 그 국면으로 옮긴다. 서류만 앞서 나가고 파이프라인이
        # 영업 단계에 남아 있으면 칸반과 목록이 서로 다른 얘기를 한다. 둘이 같이 걸리면
        # 더 나아간 계약 쪽으로 간다.
        target_phase = None
        if not had_quote and sales_deal.quote_status_id is not None:
            target_phase = "quote"
        if not had_contract and sales_deal.contract_status_id is not None:
            target_phase = "contract"
        if target_phase is not None:
            phase_result = await db.execute(
                select(SalesPipelineStage.phase_code).where(
                    SalesPipelineStage.id == sales_deal.sales_pipeline_stage_id
                )
            )
            await _move_deal_to_first_stage_of_phase(
                db, member, sales_deal, phase_result.scalar_one(), target_phase
            )

        sales_deal.updated_at = datetime.now(UTC)
        _validate_sales_deal_dates(sales_deal)
        await db.flush()
        read = await _read_one(db, member, sales_deal_id)
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
    background: BackgroundTasks,
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
        read = await _read_one(db, member, sales_deal_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    # 단계 이동도 신호가 된다(계약에이전트_설계.md 3장). 칸반에서 연달아 옮겨도 파이프라인
    # 쪽 쿨다운이 중복 실행을 막는다.
    contract_next_meeting_pipeline.queue(
        background, sales_deal_id, {"sales_deal_id": str(sales_deal_id)}
    )
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
