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
PipelineStatus = Literal["published", "archived"]
StageTone = Literal["gray", "blue", "purple", "orange", "green", "red"]
SalesPhase = Literal["sales", "quote", "contract", "order", "closed"]
SalesOutcome = Literal["in_progress", "confirmed", "cancelled"]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SalesPipelineRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    status_code: PipelineStatus
    is_default: bool
    published_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SalesPipelineStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sales_pipeline_id: UUID
    stage_code: OptionCode
    name: str
    tone: StageTone
    phase_code: SalesPhase
    outcome_code: SalesOutcome
    position: int


class SalesDealTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: OptionCode
    name: str
    position: int


ProductCategoryCode = Literal["system", "probe", "consumable"]


class ProductRead(BaseModel):
    """image_storage_key 는 내부 저장소 주소라 내보내지 않고 유무만 알린다."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    active: bool
    category_code: str
    unit_price: int
    shelf_life_months: int | None
    memo: str | None
    has_image: bool


class ProductCreate(_WriteModel):
    name: Text
    category_code: ProductCategoryCode
    unit_price: StrictInt = Field(ge=0, le=9_223_372_036_854_775_807)
    shelf_life_months: StrictInt | None = Field(default=None, gt=0, le=1_200)
    memo: LongText | None = None


class ProductImageRead(BaseModel):
    """짧게 사는 사진 주소. 매 요청마다 팀 권한을 확인한 뒤에만 발급한다."""

    url: str
    expires_in: int


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
    # 검색어가 가리키는 분류 코드. 화면은 "소모품" 처럼 분류 이름으로도 찾는데, 그 이름은
    # 화면(catalog.ts)만 알고 DB 에는 코드만 있다. 화면이 풀어서 보내고 서버는 q 와 OR 로
    # 묶는다. 이름 표를 여기에 한 벌 더 두면 두 곳이 어긋난다.
    q_category_code: list[OptionCode] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)


class SalesDealCreate(_WriteModel):
    customer_company_id: UUID
    customer_contact_id: UUID | None = None
    product_id: UUID
    sales_pipeline_id: UUID
    sales_pipeline_stage_id: UUID
    title: Text | None = None
    description: LongText | None = None
    deal_type_code: OptionCode
    deal_amount: Money
    opened_on: date
    quote_no: Text | None = None
    quote_issued_on: date | None = None
    quote_valid_until: date | None = None
    contract_no: Text | None = None
    contract_signed_on: date | None = None
    contract_ends_on: date | None = None
    warranty_terms: LongText | None = None
    expected_delivery_at: SafeDateTime | None = None
    memo: LongText | None = None

    @model_validator(mode="after")
    def validate_write(self) -> Self:
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        if self.quote_issued_on is not None and self.quote_issued_on < self.opened_on:
            raise ValueError("quote_issued_on must not be before opened_on")
        if self.quote_valid_until is not None and (
            self.quote_issued_on is None or self.quote_valid_until < self.quote_issued_on
        ):
            raise ValueError("quote_valid_until requires a non-later quote_issued_on")
        if self.contract_signed_on is not None and self.contract_signed_on < self.opened_on:
            raise ValueError("contract_signed_on must not be before opened_on")
        if self.contract_ends_on is not None and (
            self.contract_signed_on is None or self.contract_ends_on < self.contract_signed_on
        ):
            raise ValueError("contract_ends_on requires a non-later contract_signed_on")
        return self


class SalesDealPatch(_WriteModel):
    customer_company_id: UUID | None = None
    customer_contact_id: UUID | None = None
    product_id: UUID | None = None
    title: Text | None = None
    description: LongText | None = None
    deal_type_code: OptionCode | None = None
    deal_amount: Money | None = None
    opened_on: date | None = None
    quote_no: Text | None = None
    quote_issued_on: date | None = None
    quote_valid_until: date | None = None
    contract_no: Text | None = None
    contract_signed_on: date | None = None
    contract_ends_on: date | None = None
    warranty_terms: LongText | None = None
    expected_delivery_at: SafeDateTime | None = None
    memo: LongText | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for field_name in (
            "customer_company_id",
            "product_id",
            "title",
            "deal_type_code",
            "deal_amount",
            "opened_on",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class SalesDealMove(_WriteModel):
    expected_sales_pipeline_stage_id: UUID
    sales_pipeline_stage_id: UUID
    stage_position: Position


class SalesDealRead(BaseModel):
    id: UUID
    deal_no: str
    customer_company_id: UUID
    customer_company_name: str
    customer_company_region_code: str | None
    customer_contact_id: UUID | None
    customer_contact_name: str | None
    owner_member_id: UUID
    owner_display_name: str
    product_id: UUID | None
    product_name: str | None
    sales_pipeline_id: UUID
    sales_pipeline_name: str
    sales_pipeline_status_code: PipelineStatus
    sales_pipeline_is_default: bool
    sales_pipeline_stage_id: UUID
    sales_pipeline_stage_code: OptionCode
    sales_pipeline_stage_name: str
    sales_pipeline_stage_tone: StageTone
    sales_pipeline_stage_phase_code: SalesPhase
    sales_pipeline_stage_outcome_code: SalesOutcome
    sales_pipeline_stage_position: int
    sales_deal_type_id: UUID
    deal_type_code: OptionCode
    deal_type_name: str
    title: str
    description: str | None
    deal_amount: int
    opened_on: date
    closed_on: date | None
    quote_no: str | None
    quote_issued_on: date | None
    quote_valid_until: date | None
    contract_no: str | None
    contract_signed_on: date | None
    contract_ends_on: date | None
    warranty_terms: str | None
    expected_delivery_at: datetime | None
    memo: str | None
    stage_position: int
    created_at: datetime
    updated_at: datetime


class SalesDealPage(BaseModel):
    items: list[SalesDealRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None
    # 단계 탭 옆 건수 {단계 id: 건수}. 고른 단계는 빼고 센 값이라 total 과 다르다.
    counts: dict[str, int] = Field(default_factory=dict)


class SalesDealPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    start_date: date | None = None
    end_date: date | None = None
    # start_date·end_date 를 어느 날짜에 걸지. 견적 화면은 발행일로, 계약 화면은 체결일로
    # 기간을 좁힌다. 둘 다 비어 있을 수 있어 시작일로 되돌린다. 기본값은 시작일이라
    # 이미 쓰던 조회는 그대로다.
    date_basis: Literal["opened", "quote_issued", "contract_signed"] = "opened"
    owner_member_id: list[UUID] | None = None
    sales_pipeline_id: UUID | None = None
    sales_pipeline_stage_id: list[UUID] | None = None
    phase_code: list[SalesPhase] | None = None
    outcome_code: list[SalesOutcome] | None = None
    # 계약갱신 목록이 쓰는 창. start_date/end_date 가 보는 opened_on 과 다른 날짜라
    # 이름을 따로 둔다.
    contract_ends_from: date | None = None
    contract_ends_to: date | None = None
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
        if (
            self.contract_ends_from is not None
            and self.contract_ends_to is not None
            and self.contract_ends_to < self.contract_ends_from
        ):
            raise ValueError("contract_ends_to must not be before contract_ends_from")
        return self
