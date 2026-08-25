"""대시보드 집계.

카드 숫자는 각 화면 목록의 전체 수와 반드시 같아야 한다. 그래서 조건을 새로 쓰지 않고
도메인 라우터의 `_joined_select` 와 `_scope` 를 그대로 가져다 쓴다. 조건을 복사하면
한쪽만 고쳤을 때 숫자가 어긋난다.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import activities as activities_api
from app.api import notices as notices_api
from app.api import orders as orders_api
from app.api import sales_deals as deals_api
from app.api import support as support_api
from app.api.deps import CurrentMember, DbSession, owner_scope
from app.models.crm import Activity, SupportRequest
from app.models.sales import PurchaseOrder, SalesDeal, SalesTarget
from app.models.workspace import Member, Notice
from app.schemas.activities import ActivityRead
from app.schemas.dashboard import (
    CountCard,
    DashboardParams,
    DashboardRead,
    FollowUpCard,
    NoticeBrief,
    NoticeSummary,
    RenewalCard,
    SalesTargetCard,
    SupportCard,
    WeeklyBand,
    WeeklyDay,
)

router = APIRouter(tags=["dashboard"])

_SEOUL = ZoneInfo("Asia/Seoul")
# 주간 밴드는 요청이 준 시작일부터 7일이다. 화면이 "오늘을 셋째 칸에" 처럼 자기 기준으로
# 7일을 세우므로 시작일은 요청이 정한다. 주지 않으면 기준일이 속한 주의 일요일로 둔다.
_WEEK_DAYS = 7


def _week_start(day: date) -> date:
    """weekday() 는 월요일이 0 이라 일요일 시작으로 옮긴다."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """업무상 하루는 [00:00, 다음 날 00:00) 반개방 구간이다."""
    start = datetime.combine(day, time.min, tzinfo=_SEOUL)
    return start, start + timedelta(days=1)


async def _notice_summary(
    db: AsyncSession,
    member: Member,
    scope: str,
    limit: int,
) -> NoticeSummary:
    """공지와 지시는 담당자 범위와 무관하다. notices 라우터의 조건을 그대로 쓴다."""
    conditions = notices_api._scope(member, scope)
    total = (
        await db.execute(notices_api._joined_select(func.count(Notice.id)).where(*conditions))
    ).scalar_one()
    rows = (
        await db.execute(
            notices_api._joined_select(Notice, notices_api._author.display_name)
            .where(*conditions)
            .order_by(Notice.published_at.desc(), Notice.id)
            .limit(limit)
        )
    ).all()
    # 티커는 제목과 게시 시각만 세운다. 본문과 이미지는 눌렀을 때 /api/notices/{id} 가 준다.
    return NoticeSummary(
        total=total,
        items=[
            NoticeBrief(
                id=notice.id,
                tag=notice.tag,
                author_display_name=author_display_name,
                title=notice.title,
                published_at=notices_api._seoul(notice.published_at),
                due_at=notices_api._seoul(notice.due_at),
                due_text=notice.due_text,
            )
            for notice, author_display_name in rows
        ],
    )


async def _activity_cards(
    db: AsyncSession,
    member: Member,
    owner_ids: tuple[UUID, ...] | None,
    day: date,
    as_of: datetime,
) -> tuple[CountCard, CountCard, FollowUpCard]:
    scope = activities_api._scope(member, owner_ids)
    start, end = _day_bounds(day)
    today = and_(Activity.starts_at >= start, Activity.starts_at < end)

    # 오늘 카드 두 개는 같은 범위라 한 번에 센다.
    visited, total = (
        await db.execute(
            activities_api._joined_select(
                func.count(func.distinct(activities_api._company.id)).filter(
                    Activity.activity_type == "meeting"
                ),
                func.count(Activity.id),
            ).where(*scope, today)
        )
    ).one()

    horizon = as_of + timedelta(days=7)
    follow_total, overdue, due_soon = (
        await db.execute(
            activities_api._joined_select(
                func.count(Activity.id),
                func.count(Activity.id).filter(Activity.due_at < as_of),
                func.count(Activity.id).filter(
                    and_(Activity.due_at >= as_of, Activity.due_at < horizon)
                ),
            ).where(
                *scope,
                Activity.activity_type == "task",
                Activity.completed_at.is_(None),
            )
        )
    ).one()

    return (
        CountCard(count=visited),
        CountCard(count=total),
        FollowUpCard(total=follow_total, overdue=overdue, due_within_7_days=due_soon),
    )


async def _today_activities(
    db: AsyncSession,
    member: Member,
    owner_ids: tuple[UUID, ...] | None,
    day: date,
) -> list[ActivityRead]:
    """오늘 목록은 눌러야 열리는 드로어와 달리 진입하자마자 화면에 선다.

    카드 숫자와 같은 담당자 범위·같은 하루 경계를 써야 "오늘 일정 N건" 과 목록 길이가
    어긋나지 않는다.
    """
    start, end = _day_bounds(day)
    rows = (
        await db.execute(
            activities_api._joined_select(
                Activity,
                activities_api._owner.display_name,
                activities_api._contact,
                activities_api._company.id,
                activities_api._company.name,
                activities_api._product.name,
                activities_api._activity_category,
                activities_api._activity_action_tag,
            )
            .where(
                *activities_api._scope(member, owner_ids),
                Activity.starts_at >= start,
                Activity.starts_at < end,
            )
            .order_by(Activity.starts_at, Activity.id)
        )
    ).all()
    return [activities_api._activity_read(*row) for row in rows]


async def _support_card(
    db: AsyncSession,
    member: Member,
    owner_ids: tuple[UUID, ...] | None,
) -> SupportCard:
    """C/S 카드도 다른 카드와 같은 담당자 범위를 쓴다. 여기만 팀 전체면 숫자가 어긋난다."""
    scope = support_api._scope(member, owner_ids)
    total, in_progress, urgent = (
        await db.execute(
            support_api._joined_select(
                func.count(SupportRequest.id),
                func.count(SupportRequest.id).filter(SupportRequest.status_code == "in_progress"),
                func.count(SupportRequest.id).filter(SupportRequest.is_urgent.is_(True)),
            ).where(*scope)
        )
    ).one()
    return SupportCard(total=total, in_progress=in_progress, urgent=urgent)


async def _renewal_card(
    db: AsyncSession,
    member: Member,
    owner_ids: tuple[UUID, ...] | None,
    day: date,
    within_days: int | None,
) -> RenewalCard:
    """확정된 계약 중 종료일이 다가오는 딜. 갱신 대상이다.

    목록 전체는 카드를 눌렀을 때 /api/sales-deals 가 같은 조건으로 준다. 여기서는
    타일이 쓰는 개수와 대표 회사 이름만 센다.
    """
    conditions = [
        *deals_api._scope(member, owner_ids),
        deals_api._stage.outcome_code == "confirmed",
        SalesDeal.contract_ends_on.is_not(None),
        SalesDeal.contract_ends_on >= day,
    ]
    if within_days is not None:
        conditions.append(SalesDeal.contract_ends_on <= day + timedelta(days=within_days))
    count = (
        await db.execute(deals_api._joined_select(func.count(SalesDeal.id)).where(*conditions))
    ).scalar_one()
    # "새봄정형외과 외 1곳" 의 앞자리. 종료가 가장 급한 한 건이면 충분하다.
    lead_company_name = (
        await db.execute(
            deals_api._joined_select(deals_api._company.name)
            .where(*conditions)
            .order_by(SalesDeal.contract_ends_on, SalesDeal.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return RenewalCard(within_days=within_days, count=count, lead_company_name=lead_company_name)


async def _sales_target_card(
    db: AsyncSession,
    member: Member,
    owner_ids: tuple[UUID, ...] | None,
    day: date,
) -> SalesTargetCard:
    month_start = day.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)

    owners = [member.id] if member.role_code == "member" else owner_ids
    target_conditions = [
        SalesTarget.target_month == month_start,
        Member.team_id == member.team_id,
        Member.active.is_(True),
    ]
    if owners is not None:
        target_conditions.append(SalesTarget.owner_member_id.in_(owners))
    target_amount = (
        await db.execute(
            select(func.sum(SalesTarget.target_amount))
            .select_from(SalesTarget)
            .join(Member, SalesTarget.owner_member_id == Member.id)
            .where(*target_conditions)
        )
    ).scalar_one()

    # 계약 상태를 구분해 확정과 진행 중을 한 번에 센다.
    amount = func.sum(SalesDeal.deal_amount)
    confirmed, in_progress = (
        await db.execute(
            deals_api._joined_select(
                amount.filter(deals_api._stage.outcome_code == "confirmed"),
                amount.filter(deals_api._stage.outcome_code == "in_progress"),
            ).where(
                *deals_api._scope(member, owner_ids),
                SalesDeal.contract_signed_on.is_not(None),
                SalesDeal.contract_signed_on >= month_start,
                SalesDeal.contract_signed_on < next_month,
            )
        )
    ).one()
    confirmed = confirmed or 0
    in_progress = in_progress or 0

    # 목표가 없으면 0% 가 아니라 null 로 두어 "목표 미설정" 과 "미달성" 을 구분한다.
    rate = None if not target_amount else round(confirmed / target_amount * 100, 1)
    return SalesTargetCard(
        target_month=month_start.strftime("%Y-%m"),
        target_amount=target_amount,
        confirmed_amount=confirmed,
        in_progress_amount=in_progress,
        achievement_rate=rate,
    )


async def _weekly_band(
    db: AsyncSession,
    member: Member,
    owner_ids: tuple[UUID, ...] | None,
    start_date: date,
) -> WeeklyBand:
    end_date = start_date + timedelta(days=_WEEK_DAYS - 1)
    range_start, _ = _day_bounds(start_date)
    _, range_end = _day_bounds(end_date)

    activity_day = func.date(func.timezone("Asia/Seoul", Activity.starts_at))
    activity_rows = (
        await db.execute(
            activities_api._joined_select(
                activity_day,
                func.count(Activity.id).filter(Activity.activity_type == "meeting"),
                func.count(Activity.id).filter(Activity.activity_type == "task"),
            )
            .where(
                *activities_api._scope(member, owner_ids),
                Activity.starts_at >= range_start,
                Activity.starts_at < range_end,
            )
            .group_by(activity_day)
        )
    ).all()
    by_day = {row[0]: (row[1], row[2]) for row in activity_rows}

    # 납기는 발주의 입고 예정일 기준이다.
    due_rows = (
        await db.execute(
            orders_api._joined_select(
                PurchaseOrder.expected_receipt_on,
                func.count(PurchaseOrder.id),
            )
            .where(
                *orders_api._scope(member, owner_ids),
                PurchaseOrder.expected_receipt_on >= start_date,
                PurchaseOrder.expected_receipt_on <= end_date,
            )
            .group_by(PurchaseOrder.expected_receipt_on)
        )
    ).all()
    due_by_day = {row[0]: row[1] for row in due_rows}

    days = []
    for offset in range(_WEEK_DAYS):
        current = start_date + timedelta(days=offset)
        meeting_count, task_count = by_day.get(current, (0, 0))
        days.append(
            WeeklyDay(
                date=current,
                meeting_count=meeting_count,
                task_count=task_count,
                due_count=due_by_day.get(current, 0),
            )
        )
    return WeeklyBand(start_date=start_date, end_date=end_date, days=days)


@router.get("/dashboard", response_model=DashboardRead)
async def read_dashboard(
    params: Annotated[DashboardParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> DashboardRead:
    # 한 요청의 모든 집계는 같은 시각을 기준으로 한다.
    as_of = datetime.now(UTC).astimezone(_SEOUL)
    day = params.date or as_of.date()
    owner_ids = await owner_scope(db, member, params.owner_member_id)

    visited, activity_total, follow_ups = await _activity_cards(db, member, owner_ids, day, as_of)
    return DashboardRead(
        as_of=as_of,
        date=day,
        notices=await _notice_summary(db, member, "team", params.notice_limit),
        directives=await _notice_summary(db, member, "personal", params.notice_limit),
        visited_companies=visited,
        activities=activity_total,
        today_activities=await _today_activities(db, member, owner_ids, day),
        follow_ups=follow_ups,
        support_requests=await _support_card(db, member, owner_ids),
        contract_renewals=await _renewal_card(
            db, member, owner_ids, day, params.renewal_within_days
        ),
        sales_target=await _sales_target_card(db, member, owner_ids, day),
        weekly=await _weekly_band(
            db, member, owner_ids, params.weekly_start_date or _week_start(day)
        ),
    )
