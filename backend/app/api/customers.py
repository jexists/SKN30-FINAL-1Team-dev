from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession, owner_scope
from app.models.configuration import CustomerContactStatus
from app.models.crm import CustomerCompany, CustomerContact, CustomerContactAssignee
from app.models.workspace import Member
from app.schemas.customers import (
    ContactAssigneeRead,
    CustomerCompanyCreate,
    CustomerCompanyPage,
    CustomerCompanyPatch,
    CustomerCompanyRead,
    CustomerContactCreate,
    CustomerContactPage,
    CustomerContactPageParams,
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


def _assigned_to(member_ids: tuple[UUID, ...]):
    """대표 담당자가 아니어도 담당자로 지정됐으면 자기 고객이다.

    담당자는 별도 표에 있어 조인으로 끌어오면 고객 한 명이 담당자 수만큼 늘어난다.
    EXISTS 로만 묻는다.

    한 명이면 IN 대신 = 로 쓴다. 본인 것만 보는 팀원이 이 경로를 늘 지나므로 지금 나가는
    쿼리 모양을 그대로 둔다.
    """
    one = len(member_ids) == 1

    def matches(column):
        return column == member_ids[0] if one else column.in_(member_ids)

    return or_(
        matches(CustomerContact.owner_member_id),
        select(CustomerContactAssignee.member_id)
        .where(
            CustomerContactAssignee.customer_contact_id == CustomerContact.id,
            matches(CustomerContactAssignee.member_id),
        )
        .exists(),
    )


def _contact_scope(member: Member, owner_ids: tuple[UUID, ...] | None = None):
    conditions = [
        # 지운 고객은 목록에도 상세에도 나오지 않는다. 수정·삭제도 여기서 404 가 된다.
        CustomerContact.deleted_at.is_(None),
        CustomerCompany.team_id == member.team_id,
        Member.team_id == member.team_id,
        Member.active.is_(True),
        Member.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(_assigned_to((member.id,)))
    elif owner_ids is not None:
        # 팀장이 고른 보기 범위다. 목록 쿼리가 Member 를 owner_member_id 로 조인하고
        # 있어서 Member.id.in_() 로 쓰고 싶어지지만, 그러면 그 사람이 담당자이되
        # 대표 담당자가 아닌 고객이 조용히 빠진다. 팀원이 볼 때와 기준이 달라진다.
        conditions.append(_assigned_to(owner_ids))
    return conditions


# owner_member_id 조인은 _contact_scope 가 이름 없는 Member 로 참조하므로 그대로 두고,
# 등록한 사람은 별칭으로 한 번 더 조인한다.
_creator = aliased(Member)


async def _load_assignees(
    db: AsyncSession,
    contacts: list[CustomerContact],
) -> dict[UUID, list[ContactAssigneeRead]]:
    """고객들의 담당자를 한 번에 읽는다. 행마다 따로 묻지 않는다.

    대표 담당자를 맨 앞에 두고, 나머지는 지정된 순서를 따른다.
    """
    if not contacts:
        return {}
    result = await db.execute(
        select(
            CustomerContactAssignee.customer_contact_id,
            Member.id,
            Member.display_name,
        )
        .join(Member, CustomerContactAssignee.member_id == Member.id)
        .where(
            CustomerContactAssignee.customer_contact_id.in_([contact.id for contact in contacts])
        )
        .order_by(CustomerContactAssignee.created_at, Member.display_name, Member.id)
    )
    grouped: dict[UUID, list[ContactAssigneeRead]] = {contact.id: [] for contact in contacts}
    for contact_id, member_id, display_name in result.all():
        grouped[contact_id].append(ContactAssigneeRead(id=member_id, display_name=display_name))
    owner_of = {contact.id: contact.owner_member_id for contact in contacts}
    return {
        contact_id: sorted(assignees, key=lambda row: row.id != owner_of[contact_id])
        for contact_id, assignees in grouped.items()
    }


async def _resolve_assignees(
    db: AsyncSession,
    member: Member,
    assignee_member_ids: list[UUID] | None,
) -> list[Member]:
    """담당자를 정한다. 남을 담당자로 세우는 건 팀장만 할 수 있다.

    본인만 담은 목록은 권한을 따지지 않고 통과시킨다. 화면이 늘 값을 보내도 동작이 달라지지 않게
    하기 위해서다. 반환 순서가 표시 순서이고 첫 번째가 대표 담당자가 된다.
    """
    if assignee_member_ids is None:
        return [member]

    ordered = list(dict.fromkeys(assignee_member_ids))
    if not ordered:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="assignee_required",
        )
    if ordered != [member.id] and member.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="manager_required",
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
            detail="assignee_member_not_found",
        )
    return [found[assignee_id] for assignee_id in ordered]


async def _get_contact_row(
    db: AsyncSession,
    member: Member,
    contact_id: UUID,
) -> tuple[
    CustomerContact,
    str,
    str | None,
    str,
    CustomerContactStatus | None,
    str,
    list[ContactAssigneeRead],
]:
    result = await db.execute(
        select(
            CustomerContact,
            CustomerCompany.name,
            CustomerCompany.region_code,
            Member.display_name,
            CustomerContactStatus,
            _creator.display_name,
        )
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .join(_creator, CustomerContact.created_by_member_id == _creator.id)
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
    (
        contact,
        company_name,
        company_region_code,
        owner_display_name,
        contact_status,
        created_by_display_name,
    ) = row
    assignees = (await _load_assignees(db, [contact]))[contact.id]
    return (
        contact,
        company_name,
        company_region_code,
        owner_display_name,
        contact_status,
        created_by_display_name,
        assignees,
    )


def _contact_read(
    contact: CustomerContact,
    company_name: str,
    company_region_code: str | None,
    owner_display_name: str,
    contact_status: CustomerContactStatus | None,
    created_by_display_name: str,
    assignees: list[ContactAssigneeRead],
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
        visited=contact.visited,
        registered_at=contact.registered_at,
        company_name=company_name,
        company_region_code=company_region_code,
        owner_display_name=owner_display_name,
        created_by_member_id=contact.created_by_member_id,
        created_by_display_name=created_by_display_name,
        assignees=assignees,
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
    page: Annotated[CustomerContactPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> CustomerContactPage:
    # 범위를 먼저 검증한다. 거절이면 데이터 쿼리가 한 건도 나가지 않아야 한다.
    owner_ids = await owner_scope(db, member, page.owner_member_id)
    scope = _contact_scope(member, owner_ids)
    if page.company_id is not None:
        scope.append(CustomerContact.company_id == page.company_id)
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
            _creator.display_name,
        )
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .join(_creator, CustomerContact.created_by_member_id == _creator.id)
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
    rows = contacts_result.all()
    assignees_by_contact = await _load_assignees(db, [row[0] for row in rows])
    contacts = [_contact_read(*row, assignees_by_contact[row[0].id]) for row in rows]
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
    assignees = await _resolve_assignees(db, member, values.pop("assignee_member_ids"))
    contact = CustomerContact(
        id=uuid4(),
        owner_member_id=assignees[0].id,
        created_by_member_id=member.id,
        customer_contact_status_id=None if contact_status is None else contact_status.id,
        **values,
    )
    db.add(contact)
    for assignee in assignees:
        db.add(CustomerContactAssignee(customer_contact_id=contact.id, member_id=assignee.id))
    await _flush_and_commit(db)
    response.headers["Location"] = f"/api/customer-contacts/{contact.id}"
    return _contact_read(
        contact,
        company.name,
        company.region_code,
        assignees[0].display_name,
        contact_status,
        member.display_name,
        [
            ContactAssigneeRead(id=assignee.id, display_name=assignee.display_name)
            for assignee in assignees
        ],
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
        created_by_display_name,
        assignees,
    ) = await _get_contact_row(
        db,
        member,
        contact_id,
    )
    values = payload.model_dump(exclude_unset=True)
    if "assignee_member_ids" in values:
        resolved = await _resolve_assignees(db, member, values.pop("assignee_member_ids"))
        await db.execute(
            delete(CustomerContactAssignee).where(
                CustomerContactAssignee.customer_contact_id == contact.id
            )
        )
        for assignee in resolved:
            db.add(CustomerContactAssignee(customer_contact_id=contact.id, member_id=assignee.id))
        contact.owner_member_id = resolved[0].id
        # 담당자가 바뀌면 표시 이름도 바뀐다. 갱신 전 조인 값을 그대로 돌려주지 않는다.
        owner_display_name = resolved[0].display_name
        assignees = [
            ContactAssigneeRead(id=assignee.id, display_name=assignee.display_name)
            for assignee in resolved
        ]
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
        created_by_display_name,
        assignees,
    )


@router.delete("/customer-contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_contact(
    contact_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> None:
    """고객을 지운다. 팀장만 할 수 있다.

    역할을 쿼리보다 먼저 본다. 그래야 팀원이 남의 팀 고객 id 를 넣어도 404 대신 403 을
    받고, 그 id 가 있는지 없는지가 새지 않는다. update_customer_company 와 같은 순서다.

    행은 남기고 deleted_at 만 채운다. activity, sales_deal, sales_deal_participant 가
    이 고객을 참조하고 있어 실제 DELETE 는 외래키에 막히고, 참조를 먼저 끊으면 지난 딜과
    일정에서 누구를 만났는지가 사라진다. 담당자 행도 그대로 둔다.
    """
    if member.role_code != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="manager_required",
        )
    result = await db.execute(
        select(CustomerContact)
        .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
        .join(Member, CustomerContact.owner_member_id == Member.id)
        .where(CustomerContact.id == contact_id, *_contact_scope(member))
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_contact_not_found",
        )
    contact.deleted_at = datetime.now(UTC)
    await _flush_and_commit(db)
