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
    report_kind: Mapped[str]
    report_date: Mapped[date]
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    status_code: Mapped[str]
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    transcript: Mapped[str | None]
    source_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=True)
    ai_evidence: Mapped[Any] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None]
    reviewed_by_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    reviewed_at: Mapped[datetime | None]
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
    contract_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.contract.id"))
    order_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.purchase_order.id"))
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
    uploaded_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    note: Mapped[str | None]
    uploaded_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
