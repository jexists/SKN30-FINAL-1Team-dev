from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import CurrentMember, DbSession, owner_scope
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
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
)
from app.schemas.agent_runs import AgentRunCreate
from app.services import agent_runs as agent_run_service
from app.services import briefing_documents, briefing_refresh, contract_next_meeting_pipeline

router = APIRouter(tags=["activities"])

_SEOUL = ZoneInfo("Asia/Seoul")
# 일정 등록이 만드는 첫 브리핑의 멱등키 네임스페이스. 이후 재생성은 사람이 새로고침을
# 누를 때마다 새 키로 요청한다.
_BRIEFING_IDEMPOTENCY_NAMESPACE = uuid5(NAMESPACE_URL, "urn:salesluv:contract_management_briefing")
# 한 미팅의 브리핑 실행 이력에서 최신 상태를 판정할 때 훑는 행 수. 갱신이 잦아도 최근
# 몇 건 안에 성공 실행이 들어 있다.
_BRIEFING_RUN_SCAN_LIMIT = 20
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
        .outerjoin(_company, Activity.customer_company_id == _company.id)
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
        or_(
            Activity.customer_contact_id.is_(None),
            Activity.sales_deal_id.is_(None),
            _sales_deal.customer_company_id == _company.id,
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
    ai_briefing: dict | None = None,
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
        activity_category_id=category.id,
        activity_category_name=category.name,
        activity_category_tone=category.tone,
        category_code=category.code,
        title=activity.title,
        starts_at=_seoul(activity.starts_at),
        ends_at=_seoul(activity.ends_at),
        all_day=activity.all_day,
        due_at=_seoul(activity.due_at),
        location=activity.location,
        activity_action_tag_id=None if action_tag is None else action_tag.id,
        activity_action_tag_name=None if action_tag is None else action_tag.name,
        activity_action_tag_tone=None if action_tag is None else action_tag.tone,
        action_tag=None if action_tag is None else action_tag.code,
        completed_at=_seoul(activity.completed_at),
        note=activity.note,
        created_at=_seoul(activity.created_at),
        updated_at=_seoul(activity.updated_at),
        ai_briefing=ai_briefing,
    )


async def _briefing_runs(
    db: AsyncSession, member: Member, activity_id: UUID
) -> tuple[AgentRun | None, AgentRun | None]:
    """이 미팅의 브리핑 실행 중 (게시할 것, 가장 최근 것)을 고른다.

    게시 대상은 "가장 최근에 끝난 실행" 이 아니라 **가장 나중 상태의 자료를 보고 만든
    성공 실행** 이다. 정렬 키가 ``finished_at`` 이 아니라 ``source_observed_at`` 인 이유가
    그것이다 — 옛 자료로 시작한 실행이 늦게 끝났다고 해서 더 새 자료로 만든 브리핑을
    덮으면 안 된다. 실패한 실행은 애초에 후보가 아니므로 마지막 성공 브리핑이 남는다.
    """
    runs = list(
        (
            await db.execute(
                select(AgentRun)
                .where(
                    AgentRun.team_id == member.team_id,
                    AgentRun.agent_code == "contract_management_briefing",
                    AgentRun.source_refs["activity_id"].as_string() == str(activity_id),
                )
                .order_by(AgentRun.created_at.desc().nullslast(), AgentRun.id.desc())
                .limit(_BRIEFING_RUN_SCAN_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not runs:
        return None, None
    completed = [run for run in runs if run.status_code == "completed"]
    published = max(
        completed,
        key=lambda run: (
            (run.source_refs or {}).get("source_observed_at") or "",
            run.finished_at.isoformat() if run.finished_at else "",
        ),
        default=None,
    )
    return published, runs[0]


async def _activity_briefing(db: AsyncSession, member: Member, activity_id: UUID) -> dict | None:
    """일정에 연결된 브리핑의 최신 성공 결과와, 갱신이 도는 중인지를 함께 돌려준다.

    화면은 이 응답을 읽기만 한다. 여기서 실행을 만들지 않는다 — 미팅 상세를 열었다고
    RAG 검색이나 LLM 생성을 시작하고 기다리게 하지 않기 위해서다. 브리핑은 일정 등록 때
    한 번 만들고, 그 뒤에는 사람이 새로고침을 눌렀을 때만 다시 만든다.

    대신 게시 중인 브리핑이 본 입력 지문과 지금 지문을 비교해 ``outdated`` 로 알린다.
    재생성이 도는 중에는 곧 최신 결과가 나오므로 계산하지 않는다 — 화면이 완료를 기다리며
    반복 조회하는 동안 지문 질의가 되풀이되지 않게 한다.
    """
    published, latest = await _briefing_runs(db, member, activity_id)
    if latest is None:
        return None
    run = published or latest
    refreshing = latest.status_code in {"queued", "running"}
    outdated = False
    stored_revision = (published.source_refs or {}).get("source_revision") if published else None
    if stored_revision and not refreshing:
        activity = (
            await db.execute(
                select(Activity).where(
                    Activity.id == activity_id,
                    Activity.team_id == member.team_id,
                    Activity.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if activity is not None:
            current_revision = await briefing_refresh.source_revision(
                db, activity=activity, member=await briefing_refresh.owner(db, activity)
            )
            outdated = current_revision != stored_revision
    # 이미 성공 브리핑이 있는데 그 뒤 갱신이 실패했을 때만 따로 알린다. 보여줄 이전 결과가
    # 없으면 그 실패는 run 자체의 error 로 나간다.
    superseded = published is not None and latest.id != published.id
    return {
        "run_id": str(run.id),
        "status": run.status_code,
        "content": run.output_snapshot,
        "error": run.error_message,
        "generated_at": _seoul(run.finished_at).isoformat() if run.finished_at else None,
        # 갱신이 도는 중이어도 본문을 가리지 않는다. 화면은 이 값으로 작은 상태 문구만
        # 띄우고, 완료되면 조회로 교체한다.
        "refreshing": refreshing,
        # 브리핑을 만든 뒤 입력(자료·보고서·딜·일정 등)이 바뀌었다. 화면은 새로고침을 권한다.
        "outdated": outdated,
        "refresh_error": (
            latest.error_message
            if superseded and latest.status_code in {"failed", "cancelled"}
            else None
        ),
        "documents": await briefing_documents.visible_documents(
            db,
            team_id=member.team_id,
            member=member,
            context=(getattr(run, "input_snapshot", None) or {}).get("document_context") or {},
        ),
        "support_requests": await briefing_documents.visible_support_requests(
            db, member=member, snapshot=getattr(run, "input_snapshot", None) or {}
        ),
    }


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
        # 지운 고객은 새 일정의 대상으로 고를 수 없다. 이미 걸려 있던 일정은 그대로 둔다.
        CustomerContact.deleted_at.is_(None),
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


async def _team_company(db: AsyncSession, member: Member, company_id: UUID) -> str:
    """팀의 고객사인지 보고 이름을 돌려준다.

    이름까지 함께 읽는 것은 등록 응답 때문이다. 담당자 없이 고객사만 지정하면 응답이
    담당자 조회 결과에서 회사를 가져올 수 없어, 저장된 값과 달리 회사가 빈 채로 나갔다.
    """
    result = await db.execute(
        select(CustomerCompany.name).where(
            CustomerCompany.id == company_id,
            CustomerCompany.team_id == member.team_id,
        )
    )
    name = result.scalar_one_or_none()
    if name is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer_company_not_found",
        )
    return name


async def _resolve_company_id(
    db: AsyncSession,
    member: Member,
    company_id: UUID | None,
    contact_info: tuple[CustomerContact, UUID, str] | None,
) -> tuple[UUID, str]:
    """일정이 붙을 고객사를 정한다. 등록 응답이 쓸 수 있게 이름도 함께 돌려준다.

    담당자가 있으면 회사는 그 사람의 회사다 — 따로 보낸 값이 다르면 조용히 한쪽을 고르지 않고
    막는다. 담당자가 없으면 회사만이라도 있어야 한다. 둘 다 없으면 그 일정은 어느 고객사 것인지
    알 수 없고, AI 브리핑도 만들 수 없다.
    """
    if contact_info is not None:
        contact_company_id = contact_info[1]
        if company_id is not None and company_id != contact_company_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="customer_company_mismatch",
            )
        return contact_company_id, contact_info[2]
    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="customer_company_required",
        )
    return company_id, await _team_company(db, member, company_id)


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
) -> ActivityCategory:
    result = await db.execute(
        select(ActivityCategory).where(
            ActivityCategory.team_id == member.team_id,
            ActivityCategory.code == code,
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
) -> ActivityActionTag:
    result = await db.execute(
        select(ActivityActionTag).where(
            ActivityActionTag.team_id == member.team_id,
            ActivityActionTag.code == code,
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


def _validate_customer_company(
    contact_company_id: UUID | None, sales_deal: SalesDeal | None
) -> None:
    if (
        contact_company_id is not None
        and sales_deal is not None
        and sales_deal.customer_company_id != contact_company_id
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="contact_company_mismatch",
        )


@router.get("/activity-categories", response_model=list[ActivityOptionRead])
async def list_activity_categories(
    member: CurrentMember,
    db: DbSession,
) -> list[ActivityCategory]:
    result = await db.execute(
        select(ActivityCategory)
        .where(
            ActivityCategory.team_id == member.team_id,
            ActivityCategory.deleted_at.is_(None),
        )
        .order_by(ActivityCategory.position, ActivityCategory.id)
    )
    return list(result.scalars().all())


@router.get("/activity-action-tags", response_model=list[ActivityOptionRead])
async def list_activity_action_tags(
    member: CurrentMember,
    db: DbSession,
) -> list[ActivityActionTag]:
    result = await db.execute(
        select(ActivityActionTag)
        .where(
            ActivityActionTag.team_id == member.team_id,
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
    owner_ids = await owner_scope(db, member, page.owner_member_id)
    scope = [*_scope(member, owner_ids)]
    if page.start_date is not None:
        start_at = datetime.combine(page.start_date, time.min, _SEOUL)
        end_at = datetime.combine(page.end_date or page.start_date, time.min, _SEOUL) + timedelta(
            days=1
        )
        scope += [Activity.starts_at >= start_at, Activity.starts_at < end_at]
    if page.completed is not None:
        # 대시보드 후속업무 카드가 세는 조건과 글자 그대로 같아야 카드 숫자와 목록 총계가
        # 맞는다. 한쪽만 고치면 눌러서 나온 목록이 타일과 어긋난다.
        scope.append(
            Activity.completed_at.is_not(None)
            if page.completed
            else Activity.completed_at.is_(None)
        )
    order = (
        (Activity.due_at, Activity.id)
        if page.sort == "due_at"
        else (Activity.starts_at, Activity.id)
    )
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
        .order_by(*order)
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
    row = await _activity_row(db, member, activity_id)
    briefing = await _activity_briefing(db, member, activity_id)
    return _activity_read(*row, ai_briefing=briefing)


@router.post(
    "/activities",
    response_model=ActivityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity(
    payload: ActivityCreate,
    response: Response,
    background: BackgroundTasks,
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
        sales_deal = (
            None
            if payload.sales_deal_id is None
            else await _team_sales_deal(db, member, payload.sales_deal_id)
        )
        _validate_customer_company(None if contact_info is None else contact_info[1], sales_deal)
        category = await _active_activity_category(db, member, payload.category_code)
        action_tag = (
            None
            if payload.action_tag is None
            else await _active_activity_action_tag(db, member, payload.action_tag)
        )
        values = payload.model_dump()
        values.pop("category_code")
        values.pop("action_tag")
        schedule_management_run_id = values.pop("schedule_management_run_id")
        values["customer_company_id"], company_name = await _resolve_company_id(
            db, member, values["customer_company_id"], contact_info
        )
        claimed_suggestion = None
        if schedule_management_run_id is not None:
            if payload.ends_at is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="recommendation_duration_required",
                )
            # 일정을 만들기 전에 제안을 선점한다 — 커밋 뒤에 표시하면 동시 요청 둘이
            # 모두 pending 을 읽어 같은 추천에서 일정이 두 번 등록된다.
            claimed_suggestion = await _claim_suggestion(db, member, schedule_management_run_id)
            if claimed_suggestion is not None:
                conflict = await _conflict_warning(
                    db,
                    team_id=member.team_id,
                    owner_member_id=member.id,
                    activity_id=None,
                    starts_at=payload.starts_at,
                    ends_at=payload.ends_at,
                )
                if conflict is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="schedule_conflict",
                    )
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
        if claimed_suggestion is not None:
            duration_minutes = int((payload.ends_at - payload.starts_at).total_seconds() // 60)
            if duration_minutes not in {30, 60, 90}:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="invalid_recommendation_duration",
                )
            claimed_suggestion.target_date = payload.starts_at.astimezone(_SEOUL).date()
            claimed_suggestion.target_time = (
                payload.starts_at.astimezone(_SEOUL).time().replace(tzinfo=None)
            )
            claimed_suggestion.selected_duration_minutes = duration_minutes
            claimed_suggestion.applied_activity_id = activity.id
        read = _activity_read(
            activity,
            member.display_name,
            None if contact_info is None else contact_info[0],
            # 담당자가 없어도 고객사는 정해져 있다. 담당자 조회 결과에서만 가져오면
            # 저장된 값과 달리 응답의 회사가 빈 채로 나간다.
            activity.customer_company_id,
            company_name,
            None if product is None else product.name,
            category,
            action_tag,
        )
        activity_id = activity.id
        activity_company_id = activity.customer_company_id
        activity_owner_id = activity.owner_member_id
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # 일정 등록은 이미 커밋됐다 — 이 아래에서 브리핑 큐잉이 실패해도 등록 자체는 되돌리지
    # 않고, 실패 사유만 응답에 경고로 실어 보낸다.
    # 브리핑은 어느 경로로 만든 일정이든 붙인다. 미팅 전에 훑어보라고 만드는 것인데
    # AI 추천을 수락한 일정에만 붙어 있어, 사람이 직접 잡은 일정에는 없었다. 딜이 없어도
    # 만들어진다 — 입력은 activity_id 하나로 고객사·그 회사의 열린 딜·자료실까지 모인다.
    # AI 제안을 거친 일정만 parent_run_id 를 남긴다(agent_runs 가 그 필드를 선택으로 둔
    # 이유다: "캘린더 직접 입력이나 팀장 대리 입력처럼 AI 제안을 거치지 않은 일정은
    # 부모 없이 activity_id만으로 만든다").
    try:
        _, briefing_run_id = await agent_run_service.create(
            AgentRunCreate(
                agent_code="contract_management_briefing",
                activity_id=activity_id,
                parent_run_id=schedule_management_run_id,
                # 등록 직후의 "첫 브리핑" 한 번만 책임진다. 이후 자료·연결이 바뀌어도 서버가
                # 다시 만들지 않는다 — 사람이 새로고침을 눌러야 재생성된다.
                idempotency_key=uuid5(_BRIEFING_IDEMPOTENCY_NAMESPACE, str(activity_id)),
            ),
            member,
            db,
        )
        if briefing_run_id is not None:
            background.add_task(agent_run_service.execute, briefing_run_id)
    except HTTPException as error:
        read.briefing_queue_warning = str(error.detail)

    if schedule_management_run_id is None:
        # AI 추천을 거치지 않은 수동 등록이다 — 이 고객사가 AI 추천 체인을 거치지 않았을
        # 수 있다는 신호로 보고 고객사 추천을 갱신한다(계약에이전트_설계.md 3장).
        contract_next_meeting_pipeline.queue_company(
            background, activity_company_id, activity_owner_id, {"activity_id": str(activity_id)}
        )

    response.headers["Location"] = f"/api/activities/{activity_id}"
    return read


async def _conflict_warning(
    db: AsyncSession,
    *,
    team_id: UUID,
    owner_member_id: UUID,
    activity_id: UUID | None,
    starts_at: datetime,
    ends_at: datetime | None,
) -> str | None:
    """승인하려는 시간에 이 담당자의 다른 일정이 이미 있으면 안내 문구를 만든다.

    추천 카드가 만들어진 뒤 일정이 바뀔 수 있으므로 INSERT 직전에 다시 조회한다. 충돌이
    있으면 호출자가 409를 반환하고 같은 트랜잭션을 롤백하므로 일정은 저장되지 않는다.
    """
    # 종료가 없는(하루 종일) 일정은 그날 전체를 차지한 것으로 본다.
    ends_at = ends_at or starts_at + timedelta(days=1)
    statement = select(Activity.title, Activity.starts_at).where(
        Activity.team_id == team_id,
        Activity.owner_member_id == owner_member_id,
        Activity.deleted_at.is_(None),
        Activity.starts_at < ends_at,
        func.coalesce(Activity.ends_at, Activity.starts_at + timedelta(days=1)) > starts_at,
    )
    if activity_id is not None:
        statement = statement.where(Activity.id != activity_id)
    rows = (await db.execute(statement.order_by(Activity.starts_at).limit(1))).all()
    if not rows:
        return None
    title, other_start = rows[0]
    when = other_start.astimezone(_SEOUL).strftime("%m/%d %H:%M")
    return f"이 시간에 이미 다른 일정이 있습니다: {when} {title}"


async def _claim_suggestion(
    db: AsyncSession, member: Member, schedule_management_run_id: UUID
) -> ContractNextMeetingSuggestion | None:
    """AI 추천 카드를 승인해서 만든 등록이다 — 그 제안을 이 요청의 것으로 선점한다.

    승인 버튼을 연달아 누르거나 두 탭에서 함께 누르면 요청이 겹친다. 제안을 읽기만 하고
    등록을 커밋한 뒤에 상태를 바꾸면 두 요청 모두 pending 을 보게 되어, 하나의 추천에서
    같은 미팅이 두 번 등록된다. 그래서 등록보다 먼저, 같은 트랜잭션 안에서 잠근다
    (계약에이전트_설계.md 6장 "제안 상태 저장").

    with_for_update 는 이 줄을 커밋할 때까지 붙잡는다. 뒤늦게 들어온 요청은 여기서
    기다렸다가 바뀐 상태를 읽고 409 로 끝난다.

    잠금은 순서를 세울 뿐 권한을 보지 않는다. 조회 범위는 목록 조회
    (contract_suggestions.list_contract_next_meeting_suggestions)와 같게 건다 — 실행 ID 만
    보면 그 값을 아는 사람이 다른 팀이나 다른 담당자의 제안을 내려 버릴 수 있다.

    범위 밖이거나 제안이 아예 없으면 그대로 진행한다. 캘린더 카드를 거치지 않고 일정관리
    실행 ID 만 들고 온 등록이라 막을 근거가 없고, 남의 제안은 손대지 않은 채로 남는다.
    """
    conditions = [
        ContractNextMeetingSuggestion.schedule_management_run_id == schedule_management_run_id,
        ContractNextMeetingSuggestion.team_id == member.team_id,
    ]
    if member.role_code == "member":
        conditions.append(ContractNextMeetingSuggestion.owner_member_id == member.id)

    suggestion = (
        await db.execute(
            select(ContractNextMeetingSuggestion)
            .where(*conditions)
            # 딜은 범위를 거는 데만 쓴다 — of 를 빼면 조인한 딜 행까지 함께 잠근다.
            .with_for_update(of=ContractNextMeetingSuggestion)
        )
    ).scalar_one_or_none()
    if suggestion is None:
        return None
    if suggestion.status_code != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="suggestion_already_processed"
        )
    suggestion.status_code = "accepted"
    suggestion.updated_at = datetime.now(UTC)
    return suggestion


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
        if {"customer_contact_id", "customer_company_id", "sales_deal_id"} & values.keys():
            # 담당자·고객사·딜 중 하나만 바꿔도 셋의 짝이 어긋날 수 있어 함께 다시 정한다.
            contact_id = values.get("customer_contact_id", activity.customer_contact_id)
            sales_deal_id = values.get("sales_deal_id", activity.sales_deal_id)
            contact_info = (
                None if contact_id is None else await _contact_info(db, member, contact_id)
            )
            # 담당자가 있으면 회사는 거기서 나온다. 담당자를 지우기만 했다면 원래 회사를 남긴다.
            company_id = (
                values.get("customer_company_id")
                if contact_info is not None
                else values.get("customer_company_id", activity.customer_company_id)
            )
            values["customer_company_id"], _company_name = await _resolve_company_id(
                db, member, company_id, contact_info
            )
            sales_deal = (
                None if sales_deal_id is None else await _team_sales_deal(db, member, sales_deal_id)
            )
            _validate_customer_company(
                None if contact_info is None else contact_info[1], sales_deal
            )
        if "category_code" in values:
            category_code = values.pop("category_code")
            category = await _active_activity_category(db, member, category_code)
            activity.activity_category_id = category.id
        if "action_tag" in values:
            action_tag = values.pop("action_tag")
            activity.activity_action_tag_id = (
                None
                if action_tag is None
                else (await _active_activity_action_tag(db, member, action_tag)).id
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
