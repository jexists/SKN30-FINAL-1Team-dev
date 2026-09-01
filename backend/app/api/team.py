"""팀 관리(팀장 전용).

팀장이 팀원의 인사 정보와 매출 목표를 한 화면에서 다룬다. 담당자 선택 드롭다운이 쓰는
GET /team-members 와는 다른 자리다. 그쪽은 이름 목록일 뿐이고 여기는 이메일과 금액까지
담으므로 팀장에게만 연다.

달성률은 dashboard._sales_target_card 와 같은 규약으로 센다. 실적은 그달에 계약이
체결된(contract_signed_on) 확정 단계 딜의 금액이고, 목표는 sales_target 에서 거래처를
가리지 않는 행이다. 두 화면이 다른 숫자를 말하면 안 되므로 조건을 그대로 맞춘다.
"""

from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import sales_deals as deals_api
from app.api.deps import CurrentMember, DbSession
from app.models.sales import SalesDeal, SalesTarget
from app.models.workspace import Member
from app.schemas.team import (
    TeamMemberPatch,
    TeamMemberRow,
    TeamOverviewParams,
    TeamOverviewRead,
)

router = APIRouter(tags=["team"])

_SEOUL = ZoneInfo("Asia/Seoul")
# 팀당 활성 팀장이 한 명이라는 규칙은 DB 의 부분 유니크 인덱스가 지킨다.
_ONE_MANAGER_INDEX = "member_one_manager_per_team_uq"


def _this_month() -> date:
    """업무상 이번 달은 Asia/Seoul 기준이다. notices._today 와 같은 규약이다."""
    return datetime.now(_SEOUL).date().replace(day=1)


def _next_month(month_start: date) -> date:
    return (month_start + timedelta(days=32)).replace(day=1)


def _rate(confirmed: int, target: int) -> float | None:
    """목표가 없으면 0% 가 아니라 None 이다. 미설정과 미달성은 다르다."""
    return None if not target else round(confirmed / target * 100, 1)


def _require_manager(member: Member) -> None:
    """팀 관리는 팀장이 한다. notices._require_manager 와 같은 코드를 쓴다."""
    if member.role_code != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="manager_required")


def _member_row(target: Member, target_amount: int, confirmed_amount: int) -> TeamMemberRow:
    return TeamMemberRow(
        id=target.id,
        display_name=target.display_name,
        email=target.email,
        job_title=target.job_title,
        role_code=target.role_code,
        active=target.active,
        target_amount=target_amount,
        confirmed_amount=confirmed_amount,
        achievement_rate=_rate(confirmed_amount, target_amount),
    )


async def _locked_team_member(db: AsyncSession, member: Member, member_id: UUID) -> Member:
    """고칠 팀원 한 명을 잠가서 읽는다. 다른 팀 사람은 없는 것으로 본다."""
    target = (
        await db.execute(
            select(Member)
            .where(
                Member.id == member_id,
                Member.team_id == member.team_id,
                Member.role_code.in_(("member", "manager")),
            )
            .with_for_update(of=Member)
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member_not_found")
    return target


async def _targets_by_member(
    db: AsyncSession,
    member_ids: list[UUID],
    month_start: date,
) -> dict[UUID, int]:
    """그달의 팀원별 목표. 거래처를 가리지 않는 행만 본다."""
    if not member_ids:
        return {}
    result = await db.execute(
        select(SalesTarget.owner_member_id, SalesTarget.target_amount).where(
            SalesTarget.owner_member_id.in_(member_ids),
            SalesTarget.target_month == month_start,
            SalesTarget.customer_company_id.is_(None),
        )
    )
    return {owner_id: amount for owner_id, amount in result.all()}


async def _confirmed_by_member(
    db: AsyncSession,
    member: Member,
    month_start: date,
) -> dict[UUID, int]:
    """그달의 팀원별 확정 매출.

    딜의 접근 범위는 영업현황 화면과 같아야 하므로 sales_deals 의 조인·스코프를 그대로
    가져다 쓴다. 팀장이 부르는 자리라 담당자를 좁히지 않고 팀 전체를 본다.
    """
    result = await db.execute(
        deals_api._joined_select(
            SalesDeal.owner_member_id,
            func.sum(SalesDeal.deal_amount),
        )
        .where(
            *deals_api._scope(member),
            deals_api._stage.outcome_code == "confirmed",
            SalesDeal.contract_signed_on.is_not(None),
            SalesDeal.contract_signed_on >= month_start,
            SalesDeal.contract_signed_on < _next_month(month_start),
        )
        .group_by(SalesDeal.owner_member_id)
    )
    return {owner_id: amount or 0 for owner_id, amount in result.all()}


@router.get("/team/members", response_model=TeamOverviewRead)
async def get_team_overview(
    params: Annotated[TeamOverviewParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> TeamOverviewRead:
    _require_manager(member)
    month_start = params.target_month or _this_month()

    # 비활성 구성원도 목록에는 세운다. 팀장이 다시 살릴 수 있어야 하기 때문이다.
    members = list(
        (
            await db.execute(
                select(Member)
                .where(
                    Member.team_id == member.team_id,
                    Member.role_code.in_(("member", "manager")),
                )
                .order_by(Member.active.desc(), Member.display_name, Member.id)
            )
        )
        .scalars()
        .all()
    )
    targets = await _targets_by_member(db, [row.id for row in members], month_start)
    confirmed = await _confirmed_by_member(db, member, month_start)

    rows = [_member_row(row, targets.get(row.id, 0), confirmed.get(row.id, 0)) for row in members]
    # 팀 실적은 팀원 합이 아니라 팀 전체를 한 번에 센다. 목록에 없는 사람의 딜이 빠지면
    # 대시보드 숫자와 어긋난다.
    team_confirmed = sum(confirmed.values())
    member_target_sum = sum(row.target_amount for row in rows)
    return TeamOverviewRead(
        target_month=month_start.strftime("%Y-%m"),
        team_target=member_target_sum,
        team_confirmed=team_confirmed,
        team_rate=_rate(team_confirmed, member_target_sum),
        member_target_sum=member_target_sum,
        members=rows,
    )


@router.patch("/team/members/{member_id}", response_model=TeamMemberRow)
async def update_team_member(
    member_id: UUID,
    payload: TeamMemberPatch,
    member: CurrentMember,
    db: DbSession,
) -> TeamMemberRow:
    _require_manager(member)
    values = payload.model_dump(exclude_unset=True)
    month_start = values.pop("target_month", None) or _this_month()
    monthly_target = values.pop("monthly_target_amount", None)

    try:
        target = await _locked_team_member(db, member, member_id)

        # 팀장이 자기 역할을 내리거나 자기를 비활성으로 만들면 이 화면에 다시 들어올 수
        # 없다. 팀에 팀장이 하나뿐이라 되살려 줄 사람도 없다.
        if target.id == member.id:
            demoting = values.get("role_code", target.role_code) != "manager"
            deactivating = values.get("active", target.active) is False
            if demoting or deactivating:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="cannot_demote_self",
                )

        for field_name, value in values.items():
            setattr(target, field_name, value)

        if monthly_target is not None:
            row = (
                await db.execute(
                    select(SalesTarget)
                    .where(
                        SalesTarget.owner_member_id == target.id,
                        SalesTarget.target_month == month_start,
                        SalesTarget.customer_company_id.is_(None),
                    )
                    .with_for_update(of=SalesTarget)
                )
            ).scalar_one_or_none()
            if row is None:
                db.add(
                    SalesTarget(
                        id=uuid4(),
                        owner_member_id=target.id,
                        customer_company_id=None,
                        target_month=month_start,
                        target_amount=monthly_target,
                    )
                )
            else:
                row.target_amount = monthly_target

        await db.flush()
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        if _ONE_MANAGER_INDEX in str(getattr(error, "orig", error)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="manager_already_exists",
            ) from error
        raise
    except Exception:
        await db.rollback()
        raise

    targets = await _targets_by_member(db, [member_id], month_start)
    confirmed = await _confirmed_by_member(db, member, month_start)
    return _member_row(target, targets.get(member_id, 0), confirmed.get(member_id, 0))
