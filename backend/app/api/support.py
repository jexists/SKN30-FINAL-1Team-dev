from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession
from app.models.crm import CustomerCompany, CustomerContact, SupportRequest, SupportResponse
from app.models.workspace import Member
from app.schemas.support import (
    SupportRequestCreate,
    SupportRequestPage,
    SupportRequestPageParams,
    SupportRequestRead,
    SupportResponseCreate,
    SupportResponseRead,
    SupportTransition,
)

router = APIRouter(tags=["support"])

_SEOUL = ZoneInfo("Asia/Seoul")
_assignee = aliased(Member)
_contact = aliased(CustomerContact)
_contact_owner = aliased(Member)
_company = aliased(CustomerCompany)
_responder = aliased(Member)


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(SupportRequest)
        .join(_assignee, SupportRequest.assignee_member_id == _assignee.id)
        .join(_contact, SupportRequest.customer_contact_id == _contact.id)
        .join(_company, _contact.company_id == _company.id)
        .join(_contact_owner, _contact.owner_member_id == _contact_owner.id)
    )


def _scope(member: Member):
    conditions = [
        SupportRequest.team_id == member.team_id,
        _assignee.team_id == member.team_id,
        _assignee.active.is_(True),
        _assignee.role_code.in_(("member", "manager")),
        _company.team_id == member.team_id,
        _contact_owner.team_id == member.team_id,
        _contact_owner.active.is_(True),
        _contact_owner.role_code.in_(("member", "manager")),
    ]
    if member.role_code == "member":
        conditions.append(SupportRequest.assignee_member_id == member.id)
    return conditions


def _read_entities():
    return (
        SupportRequest,
        _contact.name,
        _company.id,
        _company.name,
        _assignee.display_name,
    )


def _response_read(response: SupportResponse, responder_display_name: str) -> SupportResponseRead:
    return SupportResponseRead(
        id=response.id,
        request_id=response.request_id,
        responder_member_id=response.responder_member_id,
        responder_display_name=responder_display_name,
        body=response.body,
        responded_at=response.responded_at.astimezone(_SEOUL),
    )


def _request_read(
    request: SupportRequest,
    contact_name: str,
    company_id: UUID,
    company_name: str,
    assignee_display_name: str,
    responses: list[SupportResponseRead],
) -> SupportRequestRead:
    return SupportRequestRead(
        id=request.id,
        customer_contact_id=request.customer_contact_id,
        customer_contact_name=contact_name,
        customer_company_id=company_id,
        customer_company_name=company_name,
        assignee_member_id=request.assignee_member_id,
        assignee_display_name=assignee_display_name,
        title=request.title,
        body=request.body,
        is_urgent=request.is_urgent,
        status_code=request.status_code,
        registered_at=request.registered_at.astimezone(_SEOUL),
        responses=responses,
    )


async def _responses_by_request_ids(
    db: AsyncSession,
    member: Member,
    request_ids: list[UUID],
) -> dict[UUID, list[SupportResponseRead]]:
    responses = {request_id: [] for request_id in request_ids}
    if not request_ids:
        return responses
    result = await db.execute(
        select(SupportResponse, _responder.display_name)
        .join(_responder, SupportResponse.responder_member_id == _responder.id)
        .where(
            SupportResponse.request_id.in_(request_ids),
            _responder.team_id == member.team_id,
            _responder.role_code.in_(("member", "manager")),
        )
        .order_by(SupportResponse.responded_at, SupportResponse.id)
    )
    for response, responder_name in result.all():
        responses[response.request_id].append(_response_read(response, responder_name))
    return responses


async def _request_row(db: AsyncSession, member: Member, request_id: UUID):
    result = await db.execute(
        _joined_select(*_read_entities()).where(
            SupportRequest.id == request_id,
            *_scope(member),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="support_request_not_found",
        )
    return row


async def _locked_request(
    db: AsyncSession,
    member: Member,
    request_id: UUID,
) -> SupportRequest:
    result = await db.execute(
        _joined_select(SupportRequest)
        .where(SupportRequest.id == request_id, *_scope(member))
        .with_for_update(of=SupportRequest)
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="support_request_not_found",
        )
    return request


async def _visible_contact(
    db: AsyncSession,
    member: Member,
    contact_id: UUID,
) -> tuple[CustomerContact, CustomerCompany]:
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
        select(CustomerContact, CustomerCompany)
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


@router.get("/support-requests", response_model=SupportRequestPage)
async def list_support_requests(
    page: Annotated[SupportRequestPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> SupportRequestPage:
    scope = _scope(member)
    if page.status_code is not None:
        scope.append(SupportRequest.status_code.in_(tuple(dict.fromkeys(page.status_code))))
    if page.q is not None:
        pattern = _contains(page.q)
        scope.append(
            or_(
                SupportRequest.title.ilike(pattern, escape="\\"),
                SupportRequest.body.ilike(pattern, escape="\\"),
                _contact.name.ilike(pattern, escape="\\"),
                _company.name.ilike(pattern, escape="\\"),
                _assignee.display_name.ilike(pattern, escape="\\"),
            )
        )

    total_result = await db.execute(_joined_select(func.count(SupportRequest.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(*_read_entities())
        .where(*scope)
        .order_by(SupportRequest.registered_at.desc(), SupportRequest.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    rows = rows_result.all()
    response_map = await _responses_by_request_ids(db, member, [row[0].id for row in rows])
    items = [_request_read(*row, response_map[row[0].id]) for row in rows]
    has_more = page.skip + len(items) < total
    return SupportRequestPage(
        items=items,
        skip=page.skip,
        limit=page.limit,
        total=total,
        has_more=has_more,
        next_skip=page.skip + len(items) if has_more else None,
    )


@router.get("/support-requests/{request_id}", response_model=SupportRequestRead)
async def get_support_request(
    request_id: UUID,
    member: CurrentMember,
    db: DbSession,
) -> SupportRequestRead:
    row = await _request_row(db, member, request_id)
    response_map = await _responses_by_request_ids(db, member, [request_id])
    return _request_read(*row, response_map[request_id])


@router.post(
    "/support-requests",
    response_model=SupportRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_support_request(
    payload: SupportRequestCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> SupportRequestRead:
    try:
        contact, company = await _visible_contact(db, member, payload.customer_contact_id)
        request = SupportRequest(
            id=uuid4(),
            team_id=member.team_id,
            customer_contact_id=contact.id,
            assignee_member_id=member.id,
            title=payload.title,
            body=payload.body,
            is_urgent=payload.is_urgent,
            status_code=payload.status_code,
        )
        db.add(request)
        await db.flush()
        read = _request_read(
            request,
            contact.name,
            company.id,
            company.name,
            member.display_name,
            [],
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = f"/api/support-requests/{request.id}"
    return read


@router.post(
    "/support-requests/{request_id}/transition",
    response_model=SupportRequestRead,
)
async def transition_support_request(
    request_id: UUID,
    payload: SupportTransition,
    member: CurrentMember,
    db: DbSession,
) -> SupportRequestRead:
    try:
        request = await _locked_request(db, member, request_id)
        if (
            request.status_code != payload.expected_status_code
            or payload.status_code == payload.expected_status_code
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="invalid_state_transition",
            )
        request.status_code = payload.status_code
        await db.flush()
        row = await _request_row(db, member, request_id)
        response_map = await _responses_by_request_ids(db, member, [request_id])
        read = _request_read(*row, response_map[request_id])
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return read


@router.post(
    "/support-requests/{request_id}/responses",
    response_model=SupportResponseRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_support_response(
    request_id: UUID,
    payload: SupportResponseCreate,
    response: Response,
    member: CurrentMember,
    db: DbSession,
) -> SupportResponseRead:
    try:
        await _locked_request(db, member, request_id)
        support_response = SupportResponse(
            id=uuid4(),
            request_id=request_id,
            responder_member_id=member.id,
            body=payload.body,
        )
        db.add(support_response)
        await db.flush()
        read = _response_read(support_response, member.display_name)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    response.headers["Location"] = (
        f"/api/support-requests/{request_id}/responses/{support_response.id}"
    )
    return read
