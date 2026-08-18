from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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

ProcessingStatus = Literal["uploaded", "processing", "completed", "failed"]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentCreate(_WriteModel):
    category_code: OptionCode
    title: Text
    description: LongText | None = None
    customer_company_id: UUID | None = None
    sales_deal_id: UUID | None = None
    purchase_order_id: UUID | None = None
    tags: list[Text] = Field(default_factory=list, max_length=20)


class DocumentPatch(_WriteModel):
    category_code: OptionCode | None = None
    title: Text | None = None
    description: LongText | None = None
    customer_company_id: UUID | None = None
    sales_deal_id: UUID | None = None
    purchase_order_id: UUID | None = None
    tags: list[Text] | None = Field(default=None, max_length=20)


class DocumentFileRead(BaseModel):
    """storage_key 는 내부 저장소 주소라 내보내지 않는다."""

    id: UUID
    version_no: int
    file_name: str
    media_type: str | None
    byte_size: int
    processing_status: ProcessingStatus
    uploaded_by_member_id: UUID
    uploaded_by_display_name: str
    note: str | None
    uploaded_at: datetime


class DocumentRead(BaseModel):
    id: UUID
    document_no: str
    category_code: str
    title: str
    description: str | None
    customer_company_id: UUID | None
    customer_company_name: str | None
    sales_deal_id: UUID | None
    purchase_order_id: UUID | None
    tags: list[str]
    created_by_member_id: UUID
    created_by_display_name: str
    created_at: datetime
    files: list[DocumentFileRead]
    latest_version_no: int | None


class DocumentPage(BaseModel):
    items: list[DocumentRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class DocumentPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    category_code: list[OptionCode] | None = None
    customer_company_id: UUID | None = None
    sales_deal_id: UUID | None = None
    created_by_member_id: list[UUID] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)


class DownloadRead(BaseModel):
    """짧게 사는 다운로드 주소. 매 요청마다 권한을 다시 검사하고 발급한다."""

    url: str
    expires_in: int
    file_name: str
    media_type: str | None
    byte_size: int
