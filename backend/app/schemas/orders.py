from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=254),
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=5_000),
]
SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=100),
]
OptionCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$",
    ),
]
Quantity = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]
Money = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]
OrderOutcome = Literal["in_progress", "completed", "cancelled"]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PurchaseOrderStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: OptionCode
    name: str
    tone: str
    outcome_code: OrderOutcome
    position: int


class OrderItemWrite(_WriteModel):
    product_id: UUID
    quantity: Quantity
    unit_price: Money


OrderItems = Annotated[list[OrderItemWrite], Field(min_length=1, max_length=100)]


class OrderCreate(_WriteModel):
    sales_deal_id: UUID
    supplier_name: Text
    stage_code: OptionCode
    ordered_on: date
    due_on: date
    expected_receipt_on: date
    request_department: Text | None = None
    cooperation_department: Text | None = None
    expected_customer_company_id: UUID | None = None
    memo: LongText | None = None
    items: OrderItems

    @model_validator(mode="after")
    def dates_in_order(self) -> Self:
        if self.due_on < self.ordered_on or self.expected_receipt_on < self.ordered_on:
            raise ValueError("order dates must not be before ordered_on")
        return self


class OrderPatch(_WriteModel):
    sales_deal_id: UUID | None = None
    supplier_name: Text | None = None
    ordered_on: date | None = None
    due_on: date | None = None
    expected_receipt_on: date | None = None
    request_department: Text | None = None
    cooperation_department: Text | None = None
    expected_customer_company_id: UUID | None = None
    memo: LongText | None = None
    items: OrderItems | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for field_name in (
            "sales_deal_id",
            "supplier_name",
            "ordered_on",
            "due_on",
            "expected_receipt_on",
            "request_department",
            "cooperation_department",
            "expected_customer_company_id",
            "items",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class OrderMove(_WriteModel):
    expected_stage_code: OptionCode
    stage_code: OptionCode


class OrderItemRead(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    unit_price: int
    position: int


class OrderRead(BaseModel):
    id: UUID
    order_no: str
    sales_deal_id: UUID
    deal_no: str
    customer_company_id: UUID
    customer_company_name: str
    owner_member_id: UUID
    owner_display_name: str
    supplier_name: str
    purchase_order_status_id: UUID
    stage_code: OptionCode
    stage_name: str
    stage_tone: str
    stage_outcome_code: OrderOutcome
    stage_position: int
    ordered_on: date
    due_on: date
    expected_receipt_on: date
    request_department: str
    cooperation_department: str
    created_by_member_id: UUID
    created_by_display_name: str
    expected_customer_company_id: UUID
    expected_customer_company_name: str
    memo: str | None
    items: list[OrderItemRead]
    created_at: datetime
    updated_at: datetime


class OrderPage(BaseModel):
    items: list[OrderRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None
    # 탭 옆 건수 {상태 코드: 건수}. 고른 상태는 빼고 센 값이라 total 과 다르다.
    counts: dict[str, int] = Field(default_factory=dict)
    # 공급처 고르는 칸에 세울 이름. 쪽에 담긴 발주만 보면 지금 쪽에 없는 공급처를
    # 고를 수 없어서 서버가 전체에서 뽑아 준다.
    suppliers: list[str] = Field(default_factory=list)


class OrderPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    # 발주 번호로 한 건만 집어 오는 조회에 쓴다. q 는 여러 열을 훑는 부분 일치라 번호를
    # 아는 조회에는 맞지 않는다. 상세 화면이 주소의 번호로 바로 들어올 때 쓴다.
    order_no: Text | None = None
    supplier_name: Text | None = None
    stage_code: list[OptionCode] | None = None
    sales_deal_id: list[UUID] | None = None
    start_date: date | None = None
    end_date: date | None = None
    owner_member_id: list[UUID] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=30)

    @model_validator(mode="after")
    def dates_in_order(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")
        return self
