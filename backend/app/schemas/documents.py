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


class DocumentUploaderRead(BaseModel):
    member_id: UUID
    display_name: str


class DocumentPage(BaseModel):
    items: list[DocumentRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None
    # 분류 탭 옆 건수 {분류 코드: 건수}. 고른 분류는 빼고 센 값이라 total 과 다르다.
    counts: dict[str, int] = Field(default_factory=dict)
    # 담당자 고르는 칸에 세울 사람. 최신 버전을 올린 사람 기준이고, 쪽에 담긴 문서만
    # 보면 지금 쪽에 없는 사람을 고를 수 없어서 서버가 전체에서 뽑아 준다.
    uploaders: list[DocumentUploaderRead] = Field(default_factory=list)


class DocumentPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    category_code: list[OptionCode] | None = None
    customer_company_id: UUID | None = None
    sales_deal_id: UUID | None = None
    created_by_member_id: list[UUID] | None = None
    # 아래 둘은 최신 버전 파일을 본다. 화면의 담당자·기간 필터가 "마지막으로 올린 사람과
    # 올린 날짜" 를 뜻하기 때문이다. 문서를 처음 만든 사람(created_by_member_id)과 다르다.
    latest_uploader_member_id: list[UUID] | None = None
    latest_uploaded_from: datetime | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)


class DownloadRead(BaseModel):
    """짧게 사는 다운로드 주소. 매 요청마다 권한을 다시 검사하고 발급한다."""

    url: str
    expires_in: int
    file_name: str
    media_type: str | None
    byte_size: int
