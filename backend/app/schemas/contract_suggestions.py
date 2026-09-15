from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContractNextMeetingSuggestionRead(BaseModel):
    """캘린더 "AI 추천 일정" 패널이 그대로 그리는 값. LLM을 다시 부르지 않고 저장된 값만 담는다."""

    id: UUID
    sales_deal_id: UUID
    customer_company_id: UUID
    customer_company_name: str
    customer_contact_id: UUID | None
    customer_contact_name: str | None
    owner_member_id: UUID
    owner_display_name: str
    sales_deal_title: str
    reason: str
    risks: list[dict[str, Any]]
    schedule_management_run_id: UUID
    target_date: date
    target_time: time | None
    selected_duration_minutes: int | None
    duration_options: tuple[int, int, int] = (30, 60, 90)
    refresh_reason: str | None
    status_code: str
    created_at: datetime
    updated_at: datetime


class ContractNextMeetingSuggestionApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_minutes: Literal[30, 60, 90]
    target_date: date | None = None


class ContractNextMeetingSuggestionApplyRead(BaseModel):
    sales_deal_id: UUID
    target_date: date
    duration_minutes: int
    status_code: str


class ContractNextMeetingSuggestionRefreshRead(BaseModel):
    checked_count: int
    replaced_count: int


class ContractNextMeetingGenerationStatusRead(BaseModel):
    generating: bool
    latest_report_pending: bool
    sales_deal_ids: list[UUID]
