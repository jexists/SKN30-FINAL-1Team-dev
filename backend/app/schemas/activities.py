from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)


def _seoul_offset(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(hours=9):
        raise ValueError("datetime offset must be +09:00")
    return value


ActivityType = Literal["meeting", "task"]
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
SafeDateTime = Annotated[
    AwareDatetime,
    Field(
        ge=datetime.min.replace(tzinfo=UTC),
        le=datetime.max.replace(hour=14, tzinfo=UTC),
    ),
    AfterValidator(_seoul_offset),
]
CalendarDate = Annotated[date, Field(le=date.max - timedelta(days=1))]
Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=254),
]
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=500),
]
Note = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=5_000),
]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActivityCreate(_WriteModel):
    customer_contact_id: UUID | None = None
    product_id: UUID | None = None
    sales_deal_id: UUID | None = None
    activity_type: ActivityType
    category_code: OptionCode
    title: Title
    starts_at: SafeDateTime
    ends_at: SafeDateTime | None = None
    all_day: StrictBool = False
    location: ShortText | None = None
    action_tag: OptionCode | None = None
    note: Note | None = None

    @model_validator(mode="after")
    def ends_after_start(self) -> Self:
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class ActivityPatch(_WriteModel):
    customer_contact_id: UUID | None = None
    product_id: UUID | None = None
    sales_deal_id: UUID | None = None
    activity_type: ActivityType | None = None
    category_code: OptionCode | None = None
    title: Title | None = None
    starts_at: SafeDateTime | None = None
    ends_at: SafeDateTime | None = None
    all_day: StrictBool | None = None
    location: ShortText | None = None
    action_tag: OptionCode | None = None
    note: Note | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        for field_name in (
            "activity_type",
            "category_code",
            "title",
            "starts_at",
            "all_day",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        if (
            "starts_at" in self.model_fields_set
            and "ends_at" in self.model_fields_set
            and self.ends_at is not None
            and self.starts_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be after starts_at")
        return self


class ActivityRead(BaseModel):
    id: UUID
    owner_member_id: UUID
    owner_display_name: str
    customer_contact_id: UUID | None
    customer_contact_name: str | None
    customer_contact_department: str | None
    customer_contact_job_title: str | None
    customer_company_id: UUID | None
    customer_company_name: str | None
    product_id: UUID | None
    product_name: str | None
    sales_deal_id: UUID | None
    activity_type: ActivityType
    activity_category_id: UUID
    activity_category_name: str
    activity_category_tone: str
    category_code: OptionCode
    title: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    # 후속업무 목록이 지연과 마감을 이 값으로 읽는다. 미팅에는 대개 비어 있다.
    due_at: datetime | None
    location: str | None
    activity_action_tag_id: UUID | None
    activity_action_tag_name: str | None
    activity_action_tag_tone: str | None
    action_tag: OptionCode | None
    completed_at: datetime | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class ActivityOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: OptionCode
    name: str
    tone: str
    position: int
    activity_type: ActivityType


class ActivityPage(BaseModel):
    items: list[ActivityRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class ActivityPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 달력은 늘 범위를 주지만, 미완료 후속업무처럼 기간이 아니라 상태로 묶는 목록도 있다.
    # 그런 조회는 날짜를 비우고 아래 필터만 쓴다.
    start_date: CalendarDate | None = None
    end_date: CalendarDate | None = None
    activity_type: list[ActivityType] | None = None
    completed: bool | None = None
    owner_member_id: list[UUID] | None = None
    # 후속업무는 시작 시각이 아니라 마감이 급한 순으로 읽는다. 페이지로 끊어 받으므로
    # 서버가 정렬하지 않으면 순서가 페이지 안에서만 맞는다.
    sort: Literal["starts_at", "due_at"] = "starts_at"
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=30)

    @model_validator(mode="after")
    def dates_in_order(self) -> Self:
        if self.end_date is not None and self.start_date is None:
            raise ValueError("end_date requires start_date")
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")
        return self
