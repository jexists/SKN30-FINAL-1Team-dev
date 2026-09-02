from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    __tablename__ = "report"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "current_submission_id"],
            ["public.report_submission.report_id", "public.report_submission.id"],
            name="report_current_submission_fkey",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "report_kind IN ('meeting', 'daily', 'weekly', 'monthly')",
            name="report_kind_allowed_check",
        ),
        CheckConstraint(
            "status_code IN ('draft', 'submitted', 'approved', 'changes_requested')",
            name="report_status_allowed_check",
        ),
        CheckConstraint(
            "jsonb_typeof(structured_values) = 'object'",
            name="report_structured_values_object",
        ),
        CheckConstraint("version >= 1", name="report_version_positive"),
        CheckConstraint(
            "generation_input_version >= 1",
            name="report_generation_input_version_positive",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    author_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    recipient_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    template_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    source_activity_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.activity.id"))
    sales_deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.sales_deal.id"))
    customer_company_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.customer_company.id")
    )
    report_kind: Mapped[str]
    report_date: Mapped[date]
    period_start: Mapped[date | None]
    period_end: Mapped[date | None]
    status_code: Mapped[str]
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    title: Mapped[str | None]
    body: Mapped[str | None]
    common_body: Mapped[str | None]
    unassigned_body: Mapped[str | None]
    structured_values: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    transcript: Mapped[str | None]
    source_snapshot: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    ai_evidence: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    generation_input_version: Mapped[int] = mapped_column(BigInteger, server_default=text("1"))
    last_applied_agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "public.agent_run.id",
            name="report_last_applied_agent_run_fkey",
            ondelete="SET NULL",
            use_alter=True,
        )
    )
    current_submission_id: Mapped[UUID | None]
    note: Mapped[str | None]
    # 팀장이 반려하며 남긴 사유. note 는 작성자의 칸이라 섞지 않는다.
    review_note: Mapped[str | None]
    reviewed_by_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    reviewed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ReportDeal(Base):
    __tablename__ = "report_deal"
    __table_args__ = (
        CheckConstraint(
            "position IS NULL OR position >= 0", name="report_deal_position_nonnegative"
        ),
        CheckConstraint(
            "jsonb_typeof(structured_values) = 'object'",
            name="report_deal_structured_values_object",
        ),
    )

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.report.id", ondelete="CASCADE"), primary_key=True
    )
    sales_deal_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.sales_deal.id"), primary_key=True
    )
    deal_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    position: Mapped[int | None]
    deal_no_snapshot: Mapped[str | None]
    deal_title_snapshot: Mapped[str | None]
    title: Mapped[str | None]
    body: Mapped[str | None]
    structured_values: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # DB CHECK는 SQL NULL 또는 JSON object만 허용한다. none_as_null이 없으면
    # Python None이 JSON null로 직렬화되어 초안 저장이 실패한다.
    ai_evidence: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ReportSubmission(Base):
    """작성자가 확정한 보고서의 내용 스냅샷과 그 검토 상태."""

    __tablename__ = "report_submission"
    __table_args__ = (
        UniqueConstraint("report_id", "revision_no", name="report_submission_revision_key"),
        UniqueConstraint("report_id", "id", name="report_submission_report_id_id_key"),
        CheckConstraint("revision_no >= 1", name="report_submission_revision_positive"),
        CheckConstraint("report_version >= 1", name="report_submission_report_version_positive"),
        CheckConstraint(
            "jsonb_typeof(snapshot) = 'object'", name="report_submission_snapshot_object"
        ),
        CheckConstraint(
            "snapshot_sha256 ~ '^[0-9a-f]{64}$'", name="report_submission_sha256_check"
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'changes_requested')",
            name="report_submission_review_status_check",
        ),
        CheckConstraint(
            "(review_status = 'pending' AND reviewed_by_member_id IS NULL "
            "AND reviewed_at IS NULL AND review_note IS NULL) OR "
            "(review_status = 'approved' AND reviewed_by_member_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL) OR "
            "(review_status = 'changes_requested' AND reviewed_by_member_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL AND review_note IS NOT NULL)",
            name="report_submission_review_state_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    report_id: Mapped[UUID] = mapped_column(ForeignKey("public.report.id"))
    revision_no: Mapped[int] = mapped_column(BigInteger)
    report_version: Mapped[int] = mapped_column(BigInteger)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    submitted_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member.id"))
    snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    snapshot_sha256: Mapped[str]
    review_status: Mapped[str] = mapped_column(server_default=text("'pending'::text"))
    reviewed_by_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None]
    submitted_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class ReportSource(Base):
    """기간 보고서가 실제로 사용한 확정본 또는 활동."""

    __tablename__ = "report_source"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(source_activity_id, source_report_submission_id) = 1",
            name="report_source_exactly_one_source",
        ),
        CheckConstraint("position >= 0", name="report_source_position_nonnegative"),
    )

    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.report.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(primary_key=True)
    source_activity_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.activity.id"))
    source_report_submission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.report_submission.id")
    )


class MeetingDealAnalysis(Base):
    """한 에이전트 실행에서 만든 딜별 특성과 ML 판정."""

    __tablename__ = "meeting_deal_analysis"
    __table_args__ = (
        CheckConstraint(
            "features IS NULL OR jsonb_typeof(features) = 'object'",
            name="meeting_deal_analysis_features_object",
        ),
        CheckConstraint(
            "probability IS NULL OR probability BETWEEN 0 AND 1",
            name="meeting_deal_analysis_probability_check",
        ),
        CheckConstraint(
            "(error_code IS NULL AND features IS NOT NULL "
            "AND num_nonnulls(prediction_label, probability, model_version) = 3) OR "
            "(error_code IS NOT NULL AND prediction_label IS NULL AND probability IS NULL)",
            name="meeting_deal_analysis_result_check",
        ),
    )

    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("public.agent_run.id", ondelete="CASCADE"), primary_key=True
    )
    sales_deal_id: Mapped[UUID] = mapped_column(primary_key=True)
    # report_deal은 사용자가 다시 고를 수 있는 작업본이다. 분석 이력은 섹션 삭제와
    # 함께 지우지 않고 부모 보고서가 존재하는 동안 보존한다.
    report_id: Mapped[UUID] = mapped_column(ForeignKey("public.report.id", ondelete="CASCADE"))
    feature_schema_version: Mapped[str]
    features: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    prediction_label: Mapped[str | None]
    probability: Mapped[float | None]
    model_version: Mapped[str | None]
    error_code: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


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
    extracted_payload: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    summary_markdown: Mapped[str | None]
    summary_payload: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
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
    embedding: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
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
    before_snapshot: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    after_snapshot: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
