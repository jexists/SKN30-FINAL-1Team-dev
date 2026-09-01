from datetime import datetime
from typing import Annotated, Any, Literal
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

# public.file 의 file_processing_status_check 와 같은 목록이어야 한다.
# 한 값이라도 빠지면 그 값이 든 행을 담은 목록 응답 전체가 검증에서 터진다.
ProcessingStatus = Literal["uploaded", "processing", "review_required", "completed", "failed"]


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentCreate(_WriteModel):
    category_code: OptionCode
    title: Text
    # 화면에서는 '메모' 다. 자료가 무엇인지 적는 한 칸이라 컬럼은 그대로 쓴다.
    description: LongText | None = None
    # 고객사와 발주는 새로 고를 수 없지만, 예전 자료가 들고 있어 쓰기는 열어 둔다.
    customer_company_id: UUID | None = None
    customer_contact_id: UUID | None = None
    sales_deal_id: UUID | None = None
    purchase_order_id: UUID | None = None
    product_id: UUID | None = None


class DocumentPatch(_WriteModel):
    category_code: OptionCode | None = None
    title: Text | None = None
    description: LongText | None = None
    customer_company_id: UUID | None = None
    customer_contact_id: UUID | None = None
    sales_deal_id: UUID | None = None
    purchase_order_id: UUID | None = None
    product_id: UUID | None = None


class DocumentFileRead(BaseModel):
    """storage_key 는 내부 저장소 주소라 내보내지 않는다."""

    id: UUID
    version_no: int
    file_name: str
    media_type: str | None
    byte_size: int
    processing_status: ProcessingStatus
    processing_error: str | None = None
    uploaded_by_member_id: UUID
    uploaded_by_display_name: str
    note: str | None
    uploaded_at: datetime


class DocumentProcessBatchRequest(_WriteModel):
    """자료실에서 서버 처리를 시작할 파일 목록."""

    file_ids: list[UUID] = Field(min_length=1, max_length=50)


class DocumentProcessBatchRead(BaseModel):
    """서버가 처리를 접수한 파일별 현재 상태."""

    files: list[DocumentFileRead]


class DocumentSummaryRead(BaseModel):
    file_id: UUID
    file_name: str
    processing_status: ProcessingStatus
    processing_error: str | None
    extracted_text: str | None
    extracted_markdown: str | None
    extracted_payload: dict[str, Any] | None
    summary_markdown: str | None
    summary_payload: dict[str, Any] | None
    processed_at: datetime | None


class DocumentChunkRead(BaseModel):
    chunk_id: UUID
    document_id: UUID
    file_id: UUID
    chunk_no: int
    page_start: int | None
    page_end: int | None
    section: str | None
    content: str
    score: float
    metadata: dict[str, Any]


class DocumentBriefingSourceRead(BaseModel):
    """영업·계약관리 Agent가 브리핑 근거로 사용할 RAG 검색 결과."""

    chunk_id: UUID
    document_id: UUID
    file_id: UUID
    file_name: str
    chunk_no: int
    page_start: int | None = None
    page_end: int | None = None
    section: str | None
    content: str
    score: float
    metadata: dict[str, Any]


class DocumentBriefingSummaryRead(BaseModel):
    """검색된 자료에 저장된 구조화 요약."""

    file_id: UUID
    document_id: UUID
    file_name: str
    summary_markdown: str
    summary_payload: dict[str, Any] | None


class DocumentBriefingContextRead(BaseModel):
    """브리핑 생성 Agent가 한 번에 소비할 자료요약·RAG 묶음."""

    query: str
    summaries: list[DocumentBriefingSummaryRead]
    sources: list[DocumentBriefingSourceRead]


class DocumentRead(BaseModel):
    id: UUID
    document_no: str
    category_code: str
    title: str
    description: str | None
    customer_company_id: UUID | None
    customer_company_name: str | None
    customer_contact_id: UUID | None
    sales_deal_id: UUID | None
    # 목록의 연결 칸이 id 대신 사람이 읽을 값을 보이게 이름을 함께 준다.
    sales_deal_no: str | None
    purchase_order_id: UUID | None
    product_id: UUID | None
    product_name: str | None
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
    limit: int = Field(default=30, ge=1, le=30)


class DownloadRead(BaseModel):
    """짧게 사는 다운로드 주소. 매 요청마다 권한을 다시 검사하고 발급한다."""

    url: str
    expires_in: int
    file_name: str
    media_type: str | None
    byte_size: int
