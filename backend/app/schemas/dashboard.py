from datetime import date as Date
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.notices import NoticeRead


class NoticeSummary(BaseModel):
    """전체 수와 첫 화면에 보여줄 최근 항목. 나머지는 /api/notices 로 더 불러온다."""

    total: int
    items: list[NoticeRead]


class CountCard(BaseModel):
    count: int


class FollowUpCard(BaseModel):
    total: int
    overdue: int
    due_within_7_days: int


class SupportCard(BaseModel):
    total: int
    in_progress: int
    urgent: int


class RenewalItem(BaseModel):
    """유스케이스 12행: 계약 건과 종료일, 계약서 번호를 함께 본다."""

    sales_deal_id: UUID
    deal_no: str
    title: str
    customer_company_name: str
    contract_no: str | None
    contract_ends_on: Date


class RenewalCard(BaseModel):
    # 유스케이스가 갱신 기준 일수를 정하지 않는다. 요청이 준 값을 그대로 되돌려 주고,
    # 주지 않으면 기준일 이후 만료 예정 전체를 센다.
    within_days: int | None
    count: int
    # "새봄정형외과 외 1곳" 같은 문장은 프론트가 items 로 만든다.
    items: list[RenewalItem]


class SalesTargetCard(BaseModel):
    """유스케이스 13행: 계약 상태를 구분해 진행률을 본다.

    달성률은 확정 금액 기준이고, 진행 중 금액은 따로 준다.
    """

    target_month: str
    target_amount: int | None
    confirmed_amount: int
    in_progress_amount: int
    # 목표가 없으면 null 로 두어 0% 와 구분한다.
    achievement_rate: float | None


class WeeklyDay(BaseModel):
    date: Date
    meeting_count: int
    task_count: int
    due_count: int


class WeeklyBand(BaseModel):
    start_date: Date
    end_date: Date
    days: list[WeeklyDay]


class DashboardRead(BaseModel):
    as_of: datetime
    date: Date
    notices: NoticeSummary
    directives: NoticeSummary
    visited_companies: CountCard
    activities: CountCard
    follow_ups: FollowUpCard
    support_requests: SupportCard
    contract_renewals: RenewalCard
    sales_target: SalesTargetCard
    weekly: WeeklyBand


class DashboardParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: Date | None = None
    owner_member_id: list[UUID] | None = None
    notice_limit: int = Field(default=3, ge=1, le=30)
    # 계약갱신 조회 창. 생략하면 기준일 이후 만료 예정 전체를 본다.
    renewal_within_days: int | None = Field(default=None, ge=1, le=365)
