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
from app.api.deps import CurrentMember, DbSession
from app.models.crm import Activity, SupportRequest
from app.models.sales import PurchaseOrder, SalesDeal, SalesTarget
from app.models.workspace import Member, Notice
from app.schemas.dashboard import (
    RENEWAL_WITHIN_DAYS,
    CountCard,
    DashboardParams,
    DashboardRead,
    FollowUpCard,
    NoticeSummary,
    RenewalCard,
    RenewalItem,
    SalesTargetCard,
    SupportCard,
    WeeklyBand,
    WeeklyDay,
)

router = APIRouter(tags=["dashboard"])

_SEOUL = ZoneInfo("Asia/Seoul")
# 주간 밴드는 기준일이 속한 주의 일요일부터 7일이다. 유스케이스의 전 주·오늘·다음 주
# 이동이 주 단위라서 달력 주에 맞춘다.
_WEEK_DAYS = 7


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
    return NoticeSummary(total=total, items=[notices_api._notice_read(*row) for row in rows])


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


async def _support_card(db: AsyncSession, member: Member) -> SupportCard:
    scope = support_api._scope(member)
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
) -> RenewalCard:
    """확정된 계약 중 종료일이 기준일 이내인 딜. 갱신 대상이다."""
    rows = (
        await db.execute(
            deals_api._joined_select(SalesDeal, deals_api._company.name)
            .where(
                *deals_api._scope(member, owner_ids),
                deals_api._stage.outcome_code == "confirmed",
                SalesDeal.contract_ends_on.is_not(None),
                SalesDeal.contract_ends_on >= day,
                SalesDeal.contract_ends_on <= day + timedelta(days=RENEWAL_WITHIN_DAYS),
            )
            .order_by(SalesDeal.contract_ends_on, SalesDeal.id)
        )
    ).all()
    items = [
        RenewalItem(
            sales_deal_id=deal.id,
            deal_no=deal.deal_no,
            title=deal.title,
            customer_company_name=company_name,
            contract_no=deal.contract_no,
            contract_ends_on=deal.contract_ends_on,
        )
        for deal, company_name in rows
    ]
    return RenewalCard(within_days=RENEWAL_WITHIN_DAYS, count=len(items), items=items)


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
    day: date,
) -> WeeklyBand:
    # weekday() 는 월요일이 0 이라 일요일 시작으로 옮긴다.
    start_date = day - timedelta(days=(day.weekday() + 1) % 7)
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
    owner_ids = await activities_api._owner_filter(db, member, params.owner_member_id)

    visited, activity_total, follow_ups = await _activity_cards(db, member, owner_ids, day, as_of)
    return DashboardRead(
        as_of=as_of,
        date=day,
        notices=await _notice_summary(db, member, "team", params.notice_limit),
        directives=await _notice_summary(db, member, "personal", params.notice_limit),
        visited_companies=visited,
        activities=activity_total,
        follow_ups=follow_ups,
        support_requests=await _support_card(db, member),
        contract_renewals=await _renewal_card(db, member, owner_ids, day),
        sales_target=await _sales_target_card(db, member, owner_ids, day),
        weekly=await _weekly_band(db, member, owner_ids, day),
    )
