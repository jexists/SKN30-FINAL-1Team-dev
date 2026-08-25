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
CustomerSource = Literal[
    "referral",
    "exhibition",
    "website",
    "cold_call",
    "existing_customer",
]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerCompanyCreate(_WriteModel):
    name: Text
    region_code: RegionCode | None = None
    business_no: BusinessNo | None = None


class CustomerCompanyPatch(_WriteModel):
    name: Text | None = None
    region_code: RegionCode | None = None
    business_no: BusinessNo | None = None

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
    # 예전에 들어온 코드도 그대로 읽어야 하므로 목록을 고정하지 않는다. 쓰기는 CustomerSource 로 막는다.
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
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=30, ge=1, le=100)


class CustomerContactPageParams(CustomerPageParams):
    """고객 목록만 담당자를 좁힐 수 있다.

    회사 목록은 팀 공용이라 담당자가 없다. 같은 모델을 쓰면 회사 쪽이 파라미터를 받고도
    조용히 무시하게 되므로 나눠 둔다.
    """

    owner_member_id: list[UUID] | None = None
    company_id: UUID | None = None
