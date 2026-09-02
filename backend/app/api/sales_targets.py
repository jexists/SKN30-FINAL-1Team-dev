"""매출 목표 조회. 매출 분석 화면이 실적 옆에 목표선을 세우는 데 쓴다.

대시보드의 월 목표 카드는 이 달 합계 하나만 필요해 dashboard._sales_target_card 가
직접 센다. 여기는 회사·지역까지 갈라 봐야 하므로 행을 그대로 준다. 담당자 범위를
가르는 기준은 두 곳이 같아야 한다 — 팀원은 자기 목표만, 팀장은 고른 범위만.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentMember, DbSession, owner_scope
from app.models.crm import CustomerCompany
from app.models.sales import SalesTarget
from app.models.workspace import Member
from app.schemas.sales_targets import SalesTargetParams, SalesTargetRead

router = APIRouter(tags=["sales-targets"])


@router.get("/sales-targets", response_model=list[SalesTargetRead])
async def list_sales_targets(
    params: Annotated[SalesTargetParams, Query()],
    member: CurrentMember,
    db: DbSession,
) -> list[dict[str, Any]]:
    owner_ids = await owner_scope(db, member, params.owner_member_id)
    # 팀원은 남의 목표를 볼 수 없다. dashboard._sales_target_card 와 같은 기준이다.
    owners = [member.id] if member.role_code == "member" else owner_ids

    conditions = [
        Member.team_id == member.team_id,
        Member.active.is_(True),
        CustomerCompany.team_id == member.team_id,
        # 목표는 달 단위라 구간과 겹치기만 하면 들어온다. 시작일이 달 중간이어도
        # 그 달의 목표를 빼면 화면에서 목표선이 통째로 사라진다.
        SalesTarget.target_month <= params.date_to,
        SalesTarget.target_month >= params.date_from.replace(day=1),
    ]
    if owners is not None:
        conditions.append(SalesTarget.owner_member_id.in_(owners))

    rows = (
        await db.execute(
            select(
                SalesTarget.owner_member_id,
                SalesTarget.customer_company_id,
                CustomerCompany.name.label("customer_company_name"),
                CustomerCompany.region_code.label("customer_company_region_code"),
                SalesTarget.target_month,
                SalesTarget.target_amount,
            )
            .join(Member, SalesTarget.owner_member_id == Member.id)
            .join(CustomerCompany, SalesTarget.customer_company_id == CustomerCompany.id)
            .where(*conditions)
            .order_by(SalesTarget.target_month, CustomerCompany.name, SalesTarget.id)
        )
    ).all()
    return [dict(row._mapping) for row in rows]
