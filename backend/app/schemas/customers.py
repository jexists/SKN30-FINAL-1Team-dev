from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=254),
]
RegionCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=64),
]
Phone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=50),
]
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
    ),
]
Memo = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=5_000),
]
SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=100),
]
BusinessNo = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, pattern=r"^[0-9]{10}$"),
]
Postcode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, pattern=r"^[0-9]{5}$"),
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
# 엑셀 한 번에 받는 최대 줄 수. 프론트도 같은 수로 미리 막는다.
BULK_MAX_ROWS = 1_000

CustomerSource = Literal[
    "referral",
    "event",
    "online_form",
    "joint_past",
    "media",
    "other",
]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerCompanyCreate(_WriteModel):
    name: Text
    region_code: RegionCode | None = None
    business_no: BusinessNo | None = None
    postcode: Postcode | None = None
    address: Text | None = None
    address_detail: Text | None = None


class CustomerCompanyPatch(_WriteModel):
    name: Text | None = None
    region_code: RegionCode | None = None
    business_no: BusinessNo | None = None
    postcode: Postcode | None = None
    address: Text | None = None
    address_detail: Text | None = None

    @model_validator(mode="after")
    def name_cannot_be_null(self) -> Self:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class CustomerCompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    name: str
    region_code: str | None
    business_no: str | None
    postcode: str | None
    address: str | None
    address_detail: str | None
    created_at: datetime


class CustomerCompanyPage(BaseModel):
    items: list[CustomerCompanyRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class CustomerContactCreate(_WriteModel):
    company_id: UUID
    name: Text
    department: Text | None = None
    job_title: Text | None = None
    email: Email | None = None
    phone: Phone
    status_code: OptionCode | None = None
    source_code: CustomerSource | None = None
    memo: Memo | None = None
    # 아직 만나기 전이므로 미방문에서 시작한다.
    visited: bool = False
    # 담당자. 비우면 등록한 사람 혼자가 담당자가 된다. 첫 번째가 대표 담당자다.
    assignee_member_ids: list[UUID] | None = None


class CustomerContactPatch(_WriteModel):
    company_id: UUID | None = None
    name: Text | None = None
    department: Text | None = None
    job_title: Text | None = None
    email: Email | None = None
    phone: Phone | None = None
    status_code: OptionCode | None = None
    source_code: CustomerSource | None = None
    memo: Memo | None = None
    visited: bool | None = None
    # 보내면 담당자 전체를 이 목록으로 바꾼다. 등록한 사람은 바뀌지 않는다.
    assignee_member_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> Self:
        for field_name in ("company_id", "name", "phone", "visited", "assignee_member_ids"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class ContactAssigneeRead(BaseModel):
    id: UUID
    display_name: str


class CustomerContactRead(BaseModel):
    id: UUID
    company_id: UUID
    # 대표 담당자. assignees 의 첫 번째와 같다.
    owner_member_id: UUID
    name: str
    department: str | None
    job_title: str | None
    email: str | None
    phone: str
    customer_contact_status_id: UUID | None
    customer_contact_status_name: str | None
    customer_contact_status_tone: str | None
    status_code: OptionCode | None
    # 예전에 들어온 코드도 그대로 읽어야 하므로 목록을 고정하지 않는다.
    # 쓰기는 CustomerSource 로 막는다.
    source_code: OptionCode | None
    memo: str | None
    visited: bool
    registered_at: datetime
    company_name: str
    company_region_code: str | None
    owner_display_name: str
    created_by_member_id: UUID
    created_by_display_name: str
    assignees: list[ContactAssigneeRead]


class CustomerContactStatusOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: OptionCode
    name: str
    tone: str
    position: int


class CustomerContactPage(BaseModel):
    items: list[CustomerContactRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class CustomerPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=30)


class CustomerContactPageParams(CustomerPageParams):
    """고객 목록만 담당자를 좁힐 수 있다.

    회사 목록은 팀 공용이라 담당자가 없다. 같은 모델을 쓰면 회사 쪽이 파라미터를 받고도
    조용히 무시하게 되므로 나눠 둔다.
    """

    owner_member_id: list[UUID] | None = None
    company_id: UUID | None = None


class CustomerDuplicateProbe(_WriteModel):
    """중복인지 물어볼 값. 등록 방식 넷이 모두 이 모양으로 묻는다.

    아직 저장할 값이 아니라 비교할 값이므로 형식을 강제하지 않는다. 형식이 틀린 이메일도
    "겹치는 사람이 없다" 는 답을 받아야 폼의 검증 문구가 그대로 보인다.
    """

    company_name: str = Field(default="", max_length=254)
    name: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=50)
    email: str = Field(default="", max_length=254)


class CustomerDuplicateRead(BaseModel):
    """겹친 기존 고객. 화면이 "이 정보로 고칠까요" 를 물으려면 전 필드가 필요하다."""

    contact_id: UUID
    company_id: UUID
    company_name: str
    name: str
    department: str | None
    job_title: str | None
    email: str | None
    phone: str
    memo: str | None
    visited: bool
    matched_by: list[str] = Field(min_length=1, max_length=3)


class CustomerContactBulkItem(BaseModel):
    """엑셀 한 줄. 형식 검증을 Pydantic 에 맡기지 않는다.

    한 줄의 이메일이 틀렸다고 요청 전체가 422 로 떨어지면 나머지 정상 줄까지 등록되지
    않는다. 길이만 막고, 필수값·이메일·사업자등록번호 형식은 서버가 줄마다 따로 본다.
    """

    model_config = ConfigDict(extra="forbid")

    # 엑셀에서 몇 번째 줄이었는지. 결과를 그 줄에 도로 붙이는 데만 쓴다.
    row: int = Field(ge=1, le=1_000_000)
    company_name: str = Field(default="", max_length=1_000)
    business_no: str = Field(default="", max_length=50)
    name: str = Field(default="", max_length=1_000)
    department: str = Field(default="", max_length=1_000)
    job_title: str = Field(default="", max_length=1_000)
    email: str = Field(default="", max_length=1_000)
    phone: str = Field(default="", max_length=1_000)
    visited: str = Field(default="", max_length=50)
    memo: str = Field(default="", max_length=10_000)


class CustomerContactBulkCreate(_WriteModel):
    items: list[CustomerContactBulkItem] = Field(max_length=BULK_MAX_ROWS)


class CustomerContactBulkRowResult(BaseModel):
    row: int
    # success 등록함 / duplicate 이미 있는 사람 / invalid 값이 틀림 / failed 등록하다 실패
    status: Literal["success", "duplicate", "invalid", "failed"]
    name: str
    company_name: str
    # 왜 그렇게 됐는지. api-conventions 10절대로 코드만 보내고 문구는 프론트가 정한다.
    reason_code: str | None = None
    # 등록했거나, 겹친 기존 고객의 id.
    contact_id: UUID | None = None


class CustomerContactBulkResult(BaseModel):
    total: int
    success: int
    duplicate: int
    invalid: int
    failed: int
    results: list[CustomerContactBulkRowResult]
