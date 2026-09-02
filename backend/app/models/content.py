from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    __tablename__ = "report"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    author_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    recipient_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    template_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    source_activity_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.activity.id"))
    sales_deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.sales_deal.id"))
    report_kind: Mapped[str]
    report_date: Mapped[date]
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    status_code: Mapped[str]
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    transcript: Mapped[str | None]
    # DB CHECK 는 SQL NULL 또는 JSON object 만 허용한다. 기본 JSONB 는 Python None 을
    # JSON null 로 직렬화하므로 none_as_null 을 켜야 보고서를 새로 만들 수 있다.
    source_snapshot: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    ai_evidence: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    note: Mapped[str | None]
    # 팀장이 반려하며 남긴 사유. note 는 작성자의 칸이라 섞지 않는다.
    review_note: Mapped[str | None]
    reviewed_by_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    reviewed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ReportDeal(Base):
    __tablename__ = "report_deal"

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.report.id", ondelete="CASCADE"), primary_key=True
    )
    sales_deal_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.sales_deal.id"), primary_key=True
    )
    deal_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    # DB CHECK 는 SQL NULL 또는 JSON object 만 허용한다. 기본 JSONB 는 Python None 을
    # JSON null 로 직렬화하므로 none_as_null 을 켜야 초안 딜을 저장할 수 있다.
    ai_evidence: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ReportActivity(Base):
    __tablename__ = "report_activity"

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.report.id", ondelete="CASCADE"), primary_key=True
    )
    activity_id: Mapped[UUID] = mapped_column(ForeignKey("public.activity.id"), primary_key=True)


class Document(Base):
    __tablename__ = "document"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    created_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    document_no: Mapped[str]
    category_code: Mapped[str]
    title: Mapped[str]
    description: Mapped[str | None]
    customer_company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.customer_company.id")
    )
    customer_contact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.customer_contact.id", ondelete="SET NULL")
    )
    sales_deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.sales_deal.id"))
    purchase_order_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.purchase_order.id"))
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.product.id"))
    tags: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class File(Base):
    __tablename__ = "file"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    report_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.report.id"))
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.document.id"))
    version_no: Mapped[int | None]
    file_name: Mapped[str]
    storage_key: Mapped[str]
    media_type: Mapped[str | None]
    byte_size: Mapped[int] = mapped_column(BigInteger)
    processing_status: Mapped[str]
    extracted_text: Mapped[str | None]
    extracted_markdown: Mapped[str | None]
    extracted_payload: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    summary_markdown: Mapped[str | None]
    summary_payload: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    processing_error: Mapped[str | None]
    processed_at: Mapped[datetime | None]
    review_expires_at: Mapped[datetime | None]
    unapproved_expires_at: Mapped[datetime | None]
    approved_by_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    approved_at: Mapped[datetime | None]
    uploaded_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    note: Mapped[str | None]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class DocumentChunk(Base):
    """자료요약 Agent가 RAG에 넣는 출처 보존 청크."""

    __tablename__ = "document_chunk"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("public.document.id", ondelete="CASCADE"))
    file_id: Mapped[UUID] = mapped_column(ForeignKey("public.file.id", ondelete="CASCADE"))
    chunk_no: Mapped[int]
    page_start: Mapped[int | None]
    page_end: Mapped[int | None]
    section: Mapped[str | None]
    content: Mapped[str]
    metadata_json: Mapped[Any] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    embedding: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class DocumentFileAudit(Base):
    """자료 파일의 업로드·재처리·승인 이력. 원문 대신 변경된 구조화 값만 보관한다."""

    __tablename__ = "document_file_audit"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("public.document.id", ondelete="CASCADE"))
    file_id: Mapped[UUID] = mapped_column(ForeignKey("public.file.id", ondelete="CASCADE"))
    action_code: Mapped[str]
    actor_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    before_snapshot: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    after_snapshot: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
