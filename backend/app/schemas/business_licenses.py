"""사업자등록증 OCR 결과와 고객사 등록 초안 스키마."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BusinessLicenseFields(BaseModel):
    """OCR 텍스트에서 확인된 사업자등록증의 핵심 값."""

    model_config = ConfigDict(extra="forbid")

    company: str = Field(default="", max_length=254)
    business_no: str = Field(default="", max_length=30)
    address: str = Field(default="", max_length=500)
    representative: str = Field(default="", max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    unresolved_fields: list[str] = Field(default_factory=list, max_length=10)


class BusinessLicenseDraft(BaseModel):
    """고객사 저장 전에 화면에서 확인하는 사업자등록증 초안."""

    model_config = ConfigDict(extra="forbid")

    fields: BusinessLicenseFields
    missing_required_fields: list[str] = Field(default_factory=list, max_length=10)
    ready_for_company_registration: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class BusinessLicenseScanAccepted(BaseModel):
    """접수된 사업자등록증 인식. 결과는 scan_id로 조회한다."""

    model_config = ConfigDict(extra="forbid")

    scan_id: UUID
    processing_status: str


class BusinessLicenseScanStatus(BaseModel):
    """사업자등록증 인식 진행 상태. 완료됐을 때만 초안을 담는다."""

    model_config = ConfigDict(extra="forbid")

    processing_status: str
    processing_error: str | None = None
    fields: BusinessLicenseFields | None = None
    missing_required_fields: list[str] = Field(default_factory=list, max_length=10)
    ready_for_company_registration: bool = False
