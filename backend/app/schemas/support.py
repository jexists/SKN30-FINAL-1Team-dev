from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

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
# 접수 → 원인파악 → 처리중 → 처리완료. DB 의 support_request_status_code_check 와 같다.
SupportStatus = Literal["received", "diagnosing", "in_progress", "completed"]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupportRequestCreate(_WriteModel):
    customer_company_id: UUID
    # 불만이 걸린 계약건. 이 딜의 고객사가 customer_company_id 와 같아야 한다.
    sales_deal_id: UUID
    title: Text
    body: LongText
    is_urgent: StrictBool
    status_code: SupportStatus
    # 불만이 일어난 시각. 화면이 기본값으로 지금 시각을 넣는다.
    occurred_at: datetime


class SupportRequestPatch(_WriteModel):
    """고객불만 본문 수정. 보낸 칸만 바꾼다.

    회사·딜은 담기지 않는다. 둘은 복합 외래키로 묶인 구조값이라 바꾸는 것은 다른 건을 만드는
    일에 가깝다. 상태도 담기지 않는다. transition 이 expected_status_code 로 낙관적 잠금을
    걸어 두었는데 여기서도 바꿀 수 있으면 그 보호가 무의미해진다.
    """

    title: Text | None = None
    body: LongText | None = None
    is_urgent: StrictBool | None = None
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "SupportRequestPatch":
        # 여기서 None 은 "안 보냈다" 는 뜻이다. 비울 수 있는 칸이 하나도 없으므로 명시적인
        # null 도 지우라는 뜻이 될 수 없다. 바꿀 것이 없는 요청은 조용히 200 을 주지 않는다.
        if all(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("no_fields_to_update")
        return self


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
    customer_company_id: UUID
    customer_company_name: str
    sales_deal_id: UUID
    deal_no: str
    contract_no: str | None
    deal_title: str
    # 관련 제품과 워런티는 딜이 들고 있는 값이다. 불만이 따로 저장하지 않는다.
    product_name: str | None
    warranty_terms: str | None
    assignee_member_id: UUID
    assignee_display_name: str
    title: str
    body: str
    is_urgent: bool
    status_code: SupportStatus
    occurred_at: datetime
    registered_at: datetime
    # 한 번도 고치지 않았으면 None. 화면은 이 값이 있을 때만 "수정일시" 줄을 세운다.
    updated_at: datetime | None
    responses: list[SupportResponseRead]


class SupportRequestPage(BaseModel):
    items: list[SupportRequestRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None
    # 탭 옆 건수 {상태 코드: 건수}. 고른 상태는 빼고 센 값이라 total 과 다르다.
    # 상태까지 적용해 세면 고른 탭만 숫자가 남고 나머지가 0 이 된다.
    counts: dict[str, int] = Field(default_factory=dict)


class SupportRequestPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    status_code: list[SupportStatus] | None = None
    assignee_member_id: list[UUID] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=30)
