from datetime import date as Date
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class SalesTargetRead(BaseModel):
    """담당자 한 명이 고객사 한 곳에 세운 한 달치 매출 목표.

    회사 이름과 지역을 함께 담는다. 매출 분석이 목표를 회사별·지역별로 접는데,
    화면이 그 두 가지를 붙이려고 고객사 목록을 따로 부르게 하면 요청이 두 번이 된다.
    """

    model_config = ConfigDict(from_attributes=True)

    owner_member_id: UUID
    customer_company_id: UUID
    customer_company_name: str
    customer_company_region_code: str | None
    target_month: Date
    target_amount: int


class SalesTargetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 조회 구간. 이 구간과 겹치는 달의 목표를 모두 돌려준다.
    date_from: Date
    date_to: Date
    owner_member_id: list[UUID] | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.date_to < self.date_from:
            raise ValueError("invalid_sales_target_range")
        return self
