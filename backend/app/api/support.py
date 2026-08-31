from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession, owner_scope
from app.models.crm import CustomerCompany, SupportRequest, SupportResponse
from app.models.sales import Product, SalesDeal, SalesPipelineStage
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
from app.services import contract_next_meeting_pipeline

router = APIRouter(tags=["support"])

_SEOUL = ZoneInfo("Asia/Seoul")
_assignee = aliased(Member)
_company = aliased(CustomerCompany)
_deal = aliased(SalesDeal)
_product = aliased(Product)
_responder = aliased(Member)

# 불만을 걸 수 있는 딜의 단계. 계약이 실제로 맺어진 뒤의 건만 후보다.
_COMPLAINT_PHASES = ("contract", "order", "closed")


def _contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _joined_select(*entities):
    return (
        select(*entities)
        .select_from(SupportRequest)
        .join(_assignee, SupportRequest.assignee_member_id == _assignee.id)
        .join(_company, SupportRequest.customer_company_id == _company.id)
        .join(_deal, SupportRequest.sales_deal_id == _deal.id)
        .outerjoin(_product, _deal.product_id == _product.id)
    )


def _scope(member: Member, assignee_ids: tuple[UUID, ...] | None = None):
    conditions = [
        SupportRequest.team_id == member.team_id,
        _assignee.team_id == member.team_id,
        _assignee.active.is_(True),
        _assignee.role_code.in_(("member", "manager")),
        _company.team_id == member.team_id,
        _deal.team_id == member.team_id,
        _deal.deleted_at.is_(None),
    ]
    if member.role_code == "member":
        conditions.append(SupportRequest.assignee_member_id == member.id)
    elif assignee_ids is not None:
        conditions.append(SupportRequest.assignee_member_id.in_(assignee_ids))
    return conditions


def _read_entities():
    return (
        SupportRequest,
        _company.name,
        _deal.deal_no,
        _deal.contract_no,
        _deal.title,
        _product.name,
        _deal.warranty_terms,
        _assignee.display_name,
    )


def _response_read(response: SupportResponse, responder_display_name: str) -> SupportResponseRead:
    return SupportResponseRead(
        id=response.id,
        support_request_id=response.support_request_id,
        responder_member_id=response.responder_member_id,
        responder_display_name=responder_display_name,
        body=response.body,
        responded_at=response.responded_at.astimezone(_SEOUL),
    )


def _request_read(
    request: SupportRequest,
    company_name: str,
    deal_no: str,
    contract_no: str | None,
    deal_title: str,
    product_name: str | None,
    warranty_terms: str | None,
    assignee_display_name: str,
    responses: list[SupportResponseRead],
) -> SupportRequestRead:
    return SupportRequestRead(
        id=request.id,
        customer_company_id=request.customer_company_id,
        customer_company_name=company_name,
        sales_deal_id=request.sales_deal_id,
        deal_no=deal_no,
        contract_no=contract_no,
        deal_title=deal_title,
        product_name=product_name,
        warranty_terms=warranty_terms,
        assignee_member_id=request.assignee_member_id,
        assignee_display_name=assignee_display_name,
        title=request.title,
        body=request.body,
        is_urgent=request.is_urgent,
        status_code=request.status_code,
        occurred_at=request.occurred_at.astimezone(_SEOUL),
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
            SupportResponse.support_request_id.in_(request_ids),
            _responder.team_id == member.team_id,
            _responder.role_code.in_(("member", "manager")),
        )
        .order_by(SupportResponse.responded_at, SupportResponse.id)
    )
    for response, responder_name in result.all():
        responses[response.support_request_id].append(_response_read(response, responder_name))
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


async def _visible_deal(db: AsyncSession, member: Member, deal_id: UUID):
    """불만을 걸 수 있는 딜인지 확인하고 화면이 보여줄 값까지 함께 가져온다.

    화면이 보낸 딜 id 를 그대로 믿으면 팀 경계가 요청 본문 하나로 뚫린다. 팀원은
    자기 딜에만 걸 수 있고, 계약 전 단계의 딜에는 아직 불만이 생길 수 없다.
    """
    conditions = [
        SalesDeal.id == deal_id,
        SalesDeal.team_id == member.team_id,
        SalesDeal.deleted_at.is_(None),
        CustomerCompany.team_id == member.team_id,
        SalesPipelineStage.phase_code.in_(_COMPLAINT_PHASES),
    ]
    if member.role_code == "member":
        conditions.append(SalesDeal.owner_member_id == member.id)
    result = await db.execute(
        select(SalesDeal, CustomerCompany.name, Product.name)
        .join(CustomerCompany, SalesDeal.customer_company_id == CustomerCompany.id)
        .join(
            SalesPipelineStage,
            and_(
                SalesDeal.sales_pipeline_id == SalesPipelineStage.sales_pipeline_id,
                SalesDeal.sales_pipeline_stage_id == SalesPipelineStage.id,
            ),
        )
        .outerjoin(Product, SalesDeal.product_id == Product.id)
        .where(*conditions)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sales_deal_not_found",
        )
    return row


@router.get("/support-requests", response_model=SupportRequestPage)
async def list_support_requests(
    page: Annotated[SupportRequestPageParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> SupportRequestPage:
    # 범위를 먼저 검증한다. 거절이면 데이터 쿼리가 한 건도 나가지 않아야 한다.
    assignee_ids = await owner_scope(db, member, page.assignee_member_id)
    # 상태를 뺀 나머지 조건. 탭 건수가 이 범위를 센다.
    shared = _scope(member, assignee_ids)
    if page.q is not None:
        pattern = _contains(page.q)
        shared.append(
            or_(
                SupportRequest.title.ilike(pattern, escape="\\"),
                SupportRequest.body.ilike(pattern, escape="\\"),
                _company.name.ilike(pattern, escape="\\"),
                _deal.deal_no.ilike(pattern, escape="\\"),
                _deal.contract_no.ilike(pattern, escape="\\"),
                _assignee.display_name.ilike(pattern, escape="\\"),
            )
        )

    scope = [*shared]
    if page.status_code is not None:
        scope.append(SupportRequest.status_code.in_(tuple(dict.fromkeys(page.status_code))))

    total_result = await db.execute(_joined_select(func.count(SupportRequest.id)).where(*scope))
    total = total_result.scalar_one()
    rows_result = await db.execute(
        _joined_select(*_read_entities())
        .where(*scope)
        # 목록이 보여 주는 날짜가 발생일시다. 등록 순으로 놓으면 눈에 보이는 칸이
        # 정렬돼 있지 않은 것처럼 읽힌다.
        .order_by(SupportRequest.occurred_at.desc(), SupportRequest.id)
        .offset(page.skip)
        .limit(page.limit)
    )
    rows = rows_result.all()
    # 탭 옆 건수. 고른 상태는 빼고 센다. 상태까지 적용하면 고른 탭만 숫자가 남고 나머지가
    # 0 이 되어, 다른 탭에 무엇이 얼마나 있는지 알 수 없다.
    counts_result = await db.execute(
        _joined_select(SupportRequest.status_code, func.count(SupportRequest.id))
        .where(*shared)
        .group_by(SupportRequest.status_code)
    )
    counts = {code: count for code, count in counts_result.all()}
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
        counts=counts,
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
        deal, company_name, product_name = await _visible_deal(db, member, payload.sales_deal_id)
        # 회사와 딜이 어긋나면 복합 외래키가 막지만, 그대로 두면 500 으로 새어 나간다.
        # 화면이 회사를 바꾸고 딜을 비우지 않은 경우이므로 앱이 먼저 뜻이 보이는 4xx 를 낸다.
        if deal.customer_company_id != payload.customer_company_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="company_deal_mismatch",
            )
        request = SupportRequest(
            id=uuid4(),
            team_id=member.team_id,
            customer_company_id=deal.customer_company_id,
            sales_deal_id=deal.id,
            assignee_member_id=member.id,
            title=payload.title,
            body=payload.body,
            is_urgent=payload.is_urgent,
            status_code=payload.status_code,
            occurred_at=payload.occurred_at,
        )
        db.add(request)
        await db.flush()
        read = _request_read(
            request,
            company_name,
            deal.deal_no,
            deal.contract_no,
            deal.title,
            product_name,
            deal.warranty_terms,
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
    background: BackgroundTasks,
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
        sales_deal_id = request.sales_deal_id
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    # 처리중으로 넘어가는 순간이 신호다 — 위험 신호 스냅샷이 보는 조건(미해결 C/S)과
    # 맞춘다(계약에이전트_설계.md 3장).
    if payload.status_code == "in_progress":
        contract_next_meeting_pipeline.queue(
            background, sales_deal_id, {"support_request_id": str(request_id)}
        )
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
            support_request_id=request_id,
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
