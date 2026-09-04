from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


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
    schedule_candidates: list[dict[str, Any]]
    status_code: str
    created_at: datetime
    updated_at: datetime
