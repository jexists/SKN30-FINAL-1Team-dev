from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ScheduledCompanyVisit(BaseModel):
    """이 회사에 딜 없이 잡아 둔 가장 이른 방문.

    딜이 붙은 일정은 추천 계산이 이미 보고 있어 추천 자체가 올라오지 않는다. 딜이 없는
    일정은 그 계산에 잡히지 않으므로, 막는 대신 카드에 알려 사람이 판단하게 한다.
    """

    starts_at: datetime
    title: str


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
    # 이 회사에 딜 없이 잡아 둔 방문이 있으면 그 한 건. 추천을 막지는 않는다.
    scheduled_company_visit: ScheduledCompanyVisit | None
    status_code: str
    created_at: datetime
    updated_at: datetime
