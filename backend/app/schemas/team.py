"""팀 관리 화면(팀장 전용)이 쓰는 모델.

여기의 목표 금액은 sales_target 에서 거래처를 가리지 않는 행(customer_company_id IS NULL)
하나를 말한다. 분기·연간 목표는 따로 저장하지 않고 화면이 월 목표에서 환산한다.
"""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

JobTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=254),
]
RoleCode = Literal["member", "manager"]

# bigint 로 들어가는 금액. 음수 목표는 없다.
TargetAmount = Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)]


class TeamMemberRow(BaseModel):
    """팀원 한 명의 인사 정보와 그달 실적."""

    id: UUID
    display_name: str
    email: str | None
    job_title: str | None
    role_code: RoleCode
    active: bool
    target_amount: int
    confirmed_amount: int
    # 목표가 없으면 0% 가 아니라 null 이다. "미설정" 과 "미달성" 은 다르다.
    achievement_rate: float | None


class TeamOverviewRead(BaseModel):
    """팀 관리 화면 한 장.

    team_target 은 팀원 목표의 합이다. 팀 목표를 따로 두지 않으므로 두 값이 같지만,
    화면이 둘을 나눠 보여 주므로 이름을 나눠 둔다.
    """

    target_month: str
    team_target: int
    team_confirmed: int
    team_rate: float | None
    member_target_sum: int
    members: list[TeamMemberRow]


class TeamMemberPatch(BaseModel):
    """보낸 항목만 바꾼다."""

    model_config = ConfigDict(extra="forbid")

    job_title: JobTitle | None = None
    role_code: RoleCode | None = None
    active: bool | None = None
    monthly_target_amount: TargetAmount | None = None
    # 어느 달의 목표를 고치는지. 주지 않으면 라우터가 이번 달로 채운다.
    target_month: date | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for field_name in ("job_title", "role_code", "active", "monthly_target_amount"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if self.target_month is not None and self.target_month.day != 1:
            raise ValueError("target_month_must_be_first_day")
        return self


class TeamOverviewParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 그달 1일. 주지 않으면 이번 달(Asia/Seoul)이다.
    target_month: date | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.target_month is not None and self.target_month.day != 1:
            raise ValueError("target_month_must_be_first_day")
        return self
