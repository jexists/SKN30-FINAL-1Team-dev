from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)


def _seoul_offset(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(hours=9):
        raise ValueError("datetime offset must be +09:00")
    return value


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
Money = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]
Position = Annotated[StrictInt, Field(ge=0, le=2_147_483_647)]
SafeDateTime = Annotated[
    AwareDatetime,
    Field(
        ge=datetime.min.replace(tzinfo=UTC),
        le=datetime.max.replace(hour=14, tzinfo=UTC),
    ),
    AfterValidator(_seoul_offset),
]
ContractType = Literal[
    "new_installation",
    "expansion",
    "renewal",
    "maintenance",
    "consumables_supply",
]
StageTone = Literal["gray", "blue", "purple", "orange", "green", "red"]
StageOutcome = Literal["in_progress", "confirmed", "cancelled"]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PipelineStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    tone: StageTone
    outcome_code: StageOutcome
    position: int


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    active: bool


class ProductPage(BaseModel):
    items: list[ProductRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class ProductPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)


class PipelineStageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContractCreate(_WriteModel):
    customer_company_id: UUID
    contact_id: UUID | None = None
    product_id: UUID
    stage_id: UUID
    title: Text | None = None
    description: LongText | None = None
    contract_type: ContractType
    amount: Money
    contract_date: date
    ends_on: date | None = None
    warranty_terms: LongText | None = None
    expected_delivery_at: SafeDateTime | None = None
    memo: LongText | None = None

    @model_validator(mode="after")
    def title_cannot_be_null(self) -> Self:
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


class ContractPatch(_WriteModel):
    customer_company_id: UUID | None = None
    contact_id: UUID | None = None
    product_id: UUID | None = None
    title: Text | None = None
    description: LongText | None = None
    contract_type: ContractType | None = None
    amount: Money | None = None
    contract_date: date | None = None
    ends_on: date | None = None
    warranty_terms: LongText | None = None
    expected_delivery_at: SafeDateTime | None = None
    memo: LongText | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for field_name in (
            "customer_company_id",
            "product_id",
            "title",
            "contract_type",
            "amount",
            "contract_date",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class ContractMove(_WriteModel):
    expected_stage_id: UUID
    stage_id: UUID
    position: Position


class ContractRead(BaseModel):
    id: UUID
    contract_no: str
    customer_company_id: UUID
    customer_company_name: str
    customer_company_region_code: str | None
    contact_id: UUID | None
    contact_name: str | None
    owner_member_id: UUID
    owner_display_name: str
    product_id: UUID | None
    product_name: str | None
    stage_id: UUID
    stage_name: str
    stage_tone: StageTone
    stage_outcome_code: StageOutcome
    stage_position: int
    title: str
    description: str | None
    contract_type: ContractType
    amount: int
    contract_date: date
    ends_on: date | None
    warranty_terms: str | None
    expected_delivery_at: datetime | None
    memo: str | None
    position: int
    created_at: datetime
    updated_at: datetime


class ContractPage(BaseModel):
    items: list[ContractRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class ContractPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    start_date: date | None = None
    end_date: date | None = None
    owner_member_id: list[UUID] | None = None
    stage_id: list[UUID] | None = None
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
