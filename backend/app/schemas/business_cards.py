"""명함 OCR 결과와 고객 담당자 등록 초안 스키마."""

import re
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.schemas.customers import to_digits

# 한 입력칸에는 번호 하나만 저장한다. +82 표기와 국내 유·무선 번호를 함께 찾는다.
_PHONE_NUMBER = re.compile(
    r"(?<!\d)(?:\+?82[-.\s]?)?(?:0?1[0-9]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"
)


def first_phone_digits(value: Any) -> Any:
    """여러 번호가 오면 명함에 먼저 표시된 번호 하나만 숫자로 정규화한다."""
    if not isinstance(value, str):
        return value
    match = _PHONE_NUMBER.search(value)
    if match is not None:
        return to_digits(match.group())

    # 구분자 없이 두 번호가 붙은 값은 어느 쪽인지 판별할 수 없으므로 저장하지 않는다.
    digits = to_digits(value)
    return digits if len(digits) <= 20 else ""


class BusinessCardFields(BaseModel):
    """OCR 텍스트에서 추출한 명함 후보 값. 빈 값은 확인되지 않은 정보다."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=254)
    name_en: str = Field(default="", max_length=254)
    company_name: str = Field(default="", max_length=254)
    department: str = Field(default="", max_length=254)
    job_title: str = Field(default="", max_length=254)
    email: str = Field(default="", max_length=254)
    # 한 항목에는 첫 번호 하나만 저장한다. 화면에 보일 하이픈은 프론트가 붙인다.
    phone: Annotated[str, BeforeValidator(first_phone_digits)] = Field(default="", max_length=50)
    telephone: Annotated[str, BeforeValidator(first_phone_digits)] = Field(
        default="", max_length=50
    )
    fax: Annotated[str, BeforeValidator(first_phone_digits)] = Field(default="", max_length=50)
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


class BusinessCardScanAccepted(BaseModel):
    """접수된 명함 인식. 실제 결과는 scan_id 로 조회한다."""

    model_config = ConfigDict(extra="forbid")

    scan_id: UUID
    processing_status: str


class BusinessCardScanStatus(BaseModel):
    """명함 인식 진행 상태. 완료됐을 때만 초안 값을 담는다."""

    model_config = ConfigDict(extra="forbid")

    processing_status: str
    processing_error: str | None = None
    fields: BusinessCardFields | None = None
    missing_required_fields: list[str] = Field(default_factory=list, max_length=10)
    ready_for_contact_registration: bool = False
