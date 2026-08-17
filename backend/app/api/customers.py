from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentMember, DbSession
from app.models.configuration import CustomerContactStatus
from app.models.crm import CustomerCompany, CustomerContact
from app.models.workspace import Member
from app.schemas.customers import (
    CustomerCompanyCreate,
    CustomerCompanyPage,
    CustomerCompanyPatch,
    CustomerCompanyRead,
    CustomerContactCreate,
    CustomerContactPage,
    CustomerContactPatch,
    CustomerContactRead,
    CustomerContactStatusOptionRead,
    CustomerPageParams,
)

router = APIRouter(tags=["customers"])


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _get_company(
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


def _contact_scope(member: Member):
    conditions = [
        CustomerCompany.team_id == member.team_id,
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(CustomerContact.owner_member_id == member.id)
    return conditions


async def _get_contact_row(
    db: AsyncSession,
    member: Member,
    contact_id: UUID,
) -> tuple[CustomerContact, str, str | None, str, CustomerContactStatus | None]:
    result = await db.execute(
        select(
            CustomerContact,
            CustomerCompany.name,
            CustomerCompany.region_code,
            Member.display_name,
            CustomerContactStatus,
        )
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .outerjoin(
            CustomerContactStatus,
            and_(
                CustomerContact.customer_contact_status_id == CustomerContactStatus.id,
                CustomerContactStatus.team_id == member.team_id,
            ),
        )
        .where(CustomerContact.id == contact_id, *_contact_scope(member))
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_contact_not_found",
        )
    contact, company_name, company_region_code, owner_display_name, contact_status = row
    return contact, company_name, company_region_code, owner_display_name, contact_status


def _contact_read(
    contact: CustomerContact,
    company_name: str,
    company_region_code: str | None,
    owner_display_name: str,
    contact_status: CustomerContactStatus | None,
) -> CustomerContactRead:
    return CustomerContactRead(
        id=contact.id,
        company_id=contact.company_id,
        owner_member_id=contact.owner_member_id,
        name=contact.name,
        department=contact.department,
        job_title=contact.job_title,
        email=contact.email,
        phone=contact.phone,
        customer_contact_status_id=None if contact_status is None else contact_status.id,
        customer_contact_status_name=None if contact_status is None else contact_status.name,
        customer_contact_status_tone=None if contact_status is None else contact_status.tone,
        status_code=None if contact_status is None else contact_status.code,
        source_code=contact.source_code,
        memo=contact.memo,
        registered_at=contact.registered_at,
        company_name=company_name,
        company_region_code=company_region_code,
        owner_display_name=owner_display_name,
    )


async def _active_customer_contact_status(
    db: AsyncSession,
    member: Member,
    code: str,
) -> CustomerContactStatus:
    result = await db.execute(
        select(CustomerContactStatus).where(
            CustomerContactStatus.team_id == member.team_id,
            CustomerContactStatus.code == code,
            CustomerContactStatus.deleted_at.is_(None),
        )
    )
    contact_status = result.scalar_one_or_none()
    if contact_status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="customer_contact_status_code_not_found",
        )
    return contact_status


async def _flush_and_commit(db: AsyncSession) -> None:
    try:
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@router.get(
    "/customer-contact-statuses",
    response_model=list[CustomerContactStatusOptionRead],
)
async def list_customer_contact_statuses(
    member: CurrentMember,
    db: DbSession,
) -> list[CustomerContactStatus]:
    result = await db.execute(
        select(CustomerContactStatus)
        .where(
            CustomerContactStatus.team_id == member.team_id,
            CustomerContactStatus.deleted_at.is_(None),
        )
        .order_by(CustomerContactStatus.position, CustomerContactStatus.id)
    )
    return list(result.scalars().all())


@router.get("/customer-companies", response_model=CustomerCompanyPage)
async def list_customer_companies(
    page: Annotated[CustomerPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> CustomerCompanyPage:
    scope = [CustomerCompany.team_id == member.team_id]
    if page.q is not None:
        scope.append(CustomerCompany.name.ilike(_contains(page.q), escape="\\"))
    total_result = await db.execute(select(func.count(CustomerCompany.id)).where(*scope))
    total = total_result.scalar_one()
    companies_result = await db.execute(
        select(CustomerCompany)
        .where(*scope)
        .order_by(CustomerCompany.created_at.desc(), CustomerCompany.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    companies = list(companies_result.scalars().all())
    has_more = page.skip + len(companies) < total
    return CustomerCompanyPage(
        items=companies,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(companies) if has_more else None,
    )


@router.get("/customer-companies/{company_id}", response_model=CustomerCompanyRead)
async def get_customer_company(
    company_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> CustomerCompany:
    return await _get_company(db, member, company_id)


@router.post(
    "/customer-companies",
    response_model=CustomerCompanyRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_company(
    payload: CustomerCompanyCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> CustomerCompany:
    team_id = member.team_id
    company = CustomerCompany(
        id=uuid4(),
        team_id=team_id,
        **payload.model_dump(),
    )
    db.add(company)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        result = await db.execute(
            select(CustomerCompany).where(
                CustomerCompany.team_id == team_id,
                CustomerCompany.name == payload.name,
            )
        )
        company = result.scalar_one_or_none()
        if company is None:
            raise exc
        response.status_code = status.HTTP_200_OK
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/customer-companies/{company.id}"
    return company


@router.patch("/customer-companies/{company_id}", response_model=CustomerCompanyRead)
async def update_customer_company(
    company_id: UUID,
    payload: CustomerCompanyPatch,
    member: CurrentMember,
    db: DbSession,
) -> CustomerCompany:
    if member.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="manager_required",
        )
    company = await _get_company(db, member, company_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, field_name, value)
    await _flush_and_commit(db)
    return company


@router.get("/customer-contacts", response_model=CustomerContactPage)
async def list_customer_contacts(
    page: Annotated[CustomerPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> CustomerContactPage:
    scope = _contact_scope(member)
    if page.q is not None:
        pattern = _contains(page.q)
        scope.append(
            or_(
                CustomerContact.name.ilike(pattern, escape="\\"),
                CustomerCompany.name.ilike(pattern, escape="\\"),
                CustomerContact.department.ilike(pattern, escape="\\"),
                CustomerContact.job_title.ilike(pattern, escape="\\"),
                CustomerContact.email.ilike(pattern, escape="\\"),
                CustomerContact.phone.ilike(pattern, escape="\\"),
            )
        )
    total_result = await db.execute(
        select(func.count(CustomerContact.id))
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .where(*scope)
    )
    total = total_result.scalar_one()
    contacts_result = await db.execute(
        select(
            CustomerContact,
            CustomerCompany.name,
            CustomerCompany.region_code,
            Member.display_name,
            CustomerContactStatus,
        )
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .outerjoin(
            CustomerContactStatus,
            and_(
                CustomerContact.customer_contact_status_id == CustomerContactStatus.id,
                CustomerContactStatus.team_id == member.team_id,
            ),
        )
        .where(*scope)
        .order_by(CustomerContact.registered_at.desc(), CustomerContact.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    contacts = [_contact_read(*row) for row in contacts_result.all()]
    has_more = page.skip + len(contacts) < total
    return CustomerContactPage(
        items=contacts,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(contacts) if has_more else None,
    )


@router.get("/customer-contacts/{contact_id}", response_model=CustomerContactRead)
async def get_customer_contact(
    contact_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> CustomerContactRead:
    return _contact_read(*await _get_contact_row(db, member, contact_id))


@router.post(
    "/customer-contacts",
    response_model=CustomerContactRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_contact(
    payload: CustomerContactCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> CustomerContactRead:
    company = await _get_company(db, member, payload.company_id)
    values = payload.model_dump()
    status_code = values.pop("status_code")
    contact_status = (
        None
        if status_code is None
        else await _active_customer_contact_status(db, member, status_code)
    )
    contact = CustomerContact(
        id=uuid4(),
        owner_member_id=member.id,
        customer_contact_status_id=None if contact_status is None else contact_status.id,
        **values,
    )
    db.add(contact)
    await _flush_and_commit(db)
    response.headers["Location"] = f"/api/customer-contacts/{contact.id}"
    return _contact_read(
        contact,
        company.name,
        company.region_code,
        member.display_name,
        contact_status,
    )


@router.patch("/customer-contacts/{contact_id}", response_model=CustomerContactRead)
async def update_customer_contact(
    contact_id: UUID,
    payload: CustomerContactPatch,
    member: CurrentMember,
    db: DbSession,
) -> CustomerContactRead:
    (
        contact,
        company_name,
        company_region_code,
        owner_display_name,
        contact_status,
    ) = await _get_contact_row(
        db,
        member,
        contact_id,
    )
    values = payload.model_dump(exclude_unset=True)
    if "company_id" in values:
        company = await _get_company(db, member, values["company_id"])
        company_name = company.name
        company_region_code = company.region_code
    if "status_code" in values:
        status_code = values.pop("status_code")
        contact_status = (
            None
            if status_code is None
            else await _active_customer_contact_status(db, member, status_code)
        )
        contact.customer_contact_status_id = None if contact_status is None else contact_status.id
    for field_name, value in values.items():
        setattr(contact, field_name, value)
    await _flush_and_commit(db)
    return _contact_read(
        contact,
        company_name,
        company_region_code,
        owner_display_name,
        contact_status,
    )
