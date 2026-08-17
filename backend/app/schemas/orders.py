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
Quantity = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]
Money = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]
OrderStage = Literal[
    "order_received",
    "dispatch_request_completed",
    "in_production",
    "stock_received",
    "delivered",
    "cancelled",
]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrderItemWrite(_WriteModel):
    product_id: UUID
    quantity: Quantity
    unit_price: Money


OrderItems = Annotated[list[OrderItemWrite], Field(min_length=1, max_length=100)]


class OrderCreate(_WriteModel):
    contract_id: UUID | None = None
    customer_company_id: UUID
    supplier_name: Text
    stage_code: OrderStage
    ordered_on: date
    due_on: date
    expected_receipt_on: date
    memo: LongText | None = None
    items: OrderItems


class OrderPatch(_WriteModel):
    contract_id: UUID | None = None
    customer_company_id: UUID | None = None
    supplier_name: Text | None = None
    ordered_on: date | None = None
    due_on: date | None = None
    expected_receipt_on: date | None = None
    memo: LongText | None = None
    items: OrderItems | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for field_name in (
            "customer_company_id",
            "supplier_name",
            "ordered_on",
            "due_on",
            "expected_receipt_on",
            "items",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class OrderMove(_WriteModel):
    expected_stage_code: OrderStage
    stage_code: OrderStage


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
    contract_id: UUID | None
    contract_no: str | None
    customer_company_id: UUID
    customer_company_name: str
    owner_member_id: UUID
    owner_display_name: str
    supplier_name: str
    stage_code: OrderStage
    ordered_on: date
    due_on: date
    expected_receipt_on: date
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


class OrderPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    supplier_name: Text | None = None
    stage_code: list[OrderStage] | None = None
    start_date: date | None = None
    end_date: date | None = None
    owner_member_id: list[UUID] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)

    @model_validator(mode="after")
    def dates_in_order(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")
        return self
