"""명함 OCR 결과와 고객 담당자 등록 초안 스키마."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessCardFields(BaseModel):
    """OCR 텍스트에서 추출한 명함 후보 값. 빈 값은 확인되지 않은 정보다."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=254)
    name_en: str = Field(default="", max_length=254)
    company_name: str = Field(default="", max_length=254)
    department: str = Field(default="", max_length=254)
    job_title: str = Field(default="", max_length=254)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=50)
    website: str = Field(default="", max_length=254)
    address: str = Field(default="", max_length=500)
    memo: str = Field(default="", max_length=5_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    unresolved_fields: list[str] = Field(default_factory=list, max_length=20)


class BusinessCardDraft(BaseModel):
    """기존 customer_contact API에 넘기기 전 사용자 확인용 초안."""

    model_config = ConfigDict(extra="forbid")

    fields: BusinessCardFields
    missing_required_fields: list[str] = Field(default_factory=list, max_length=10)
    ready_for_contact_registration: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class BusinessCardMatchRead(BaseModel):
    """명함 후보와 기존 고객 담당자의 중복 가능성. 자동 병합하지 않는다."""

    contact_id: UUID
    company_id: UUID
    company_name: str
    name: str
    phone: str
    email: str | None
    matched_by: list[str] = Field(min_length=1, max_length=3)
