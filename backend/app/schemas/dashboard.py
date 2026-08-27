from datetime import date as Date
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.activities import ActivityRead
from app.schemas.notices import NoticeTargetRead, NoticeType


class NoticeBrief(BaseModel):
    """티커에 세우는 한 줄. 본문과 이미지는 눌렀을 때 /api/notices/{id} 가 준다."""

    id: UUID
    type: NoticeType
    tag: str | None
    author_display_name: str
    title: str
    # 지시의 수신자. 팀장이 남에게 간 지시를 볼 때 누구에게 간 것인지 밝힌다.
    # 공지(NOTICE)는 수신자가 없어 빈 목록이다.
    targets: list[NoticeTargetRead]
    published_at: datetime
    due_at: datetime | None
    due_text: str | None


class NoticeSummary(BaseModel):
    """전체 수와 첫 화면에 보여줄 최근 항목. 나머지는 /api/notices 로 더 불러온다."""

    total: int
    items: list[NoticeBrief]


class CountCard(BaseModel):
    count: int


class SupportCard(BaseModel):
    total: int
    in_progress: int
    urgent: int


class RenewalCard(BaseModel):
    # 유스케이스가 갱신 기준 일수를 정하지 않는다. 요청이 준 값을 그대로 되돌려 주고,
    # 주지 않으면 기준일 이후 만료 예정 전체를 센다.
    within_days: int | None
    count: int
    # "새봄정형외과 외 1곳" 은 프론트가 이 이름과 count 로 만든다. 목록 전체는
    # 카드를 눌렀을 때 /api/sales-deals 가 같은 조건으로 준다.
    lead_company_name: str | None


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
    activity_count: int
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
    # 오늘 목록은 진입하자마자 화면에 선다. 눌러야 열리는 드로어 목록들과 달리
    # 여기 담아 첫 응답 한 번으로 끝낸다.
    today_activities: list[ActivityRead]
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
    # 주간 밴드 시작일. 화면이 "오늘을 셋째 칸에" 같은 자기 기준으로 7일을 세우므로
    # 요청이 정한다. 생략하면 기준일이 속한 주의 일요일부터 7일이다.
    weekly_start_date: Date | None = None
