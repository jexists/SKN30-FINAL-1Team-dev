from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints

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
SupportStatus = Literal["in_progress", "completed"]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupportRequestCreate(_WriteModel):
    customer_contact_id: UUID
    title: Text
    body: LongText
    is_urgent: StrictBool
    status_code: SupportStatus


class SupportTransition(_WriteModel):
    expected_status_code: SupportStatus
    status_code: SupportStatus


class SupportResponseCreate(_WriteModel):
    body: LongText


class SupportResponseRead(BaseModel):
    id: UUID
    support_request_id: UUID
    responder_member_id: UUID
    responder_display_name: str
    body: str
    responded_at: datetime


class SupportRequestRead(BaseModel):
    id: UUID
    customer_contact_id: UUID
    customer_contact_name: str
    customer_company_id: UUID
    customer_company_name: str
    assignee_member_id: UUID
    assignee_display_name: str
    title: str
    body: str
    is_urgent: bool
    status_code: SupportStatus
    registered_at: datetime
    responses: list[SupportResponseRead]


class SupportRequestPage(BaseModel):
    items: list[SupportRequestRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class SupportRequestPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    status_code: list[SupportStatus] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)
