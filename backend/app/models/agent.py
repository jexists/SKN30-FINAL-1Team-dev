from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Time, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentRun(Base):
    __tablename__ = "agent_run"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    parent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.agent_run.id"))
    requested_by_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.member.id"))
    agent_code: Mapped[str]
    trigger_code: Mapped[str]
    idempotency_key: Mapped[UUID | None]
    report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("public.report.id", ondelete="SET NULL")
    )
    status_code: Mapped[str]
    llm_model_name: Mapped[str]
    prompt_version: Mapped[str]
    request_snapshot: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    request_hash: Mapped[str | None]
    scope_key: Mapped[str | None]
    source_refs: Mapped[Any] = mapped_column(JSONB, nullable=False)
    input_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    output_snapshot: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    progress_snapshot: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    evidence: Mapped[Any] = mapped_column(JSONB(none_as_null=True), nullable=True)
    error_message: Mapped[str | None]
    error_code: Mapped[str | None]
    current_stage_code: Mapped[str] = mapped_column(server_default=text("'queued'::text"))
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    payload_expires_at: Mapped[datetime | None]
    payload_redacted_at: Mapped[datetime | None]
    lease_owner: Mapped[str | None]
    lease_expires_at: Mapped[datetime | None]
    heartbeat_at: Mapped[datetime | None]
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    input_tokens: Mapped[int | None] = mapped_column(BigInteger)
    output_tokens: Mapped[int | None] = mapped_column(BigInteger)
    total_tokens: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class ContractNextMeetingSuggestion(Base):
    """캘린더 "AI 추천 일정" 패널이 조회하는 상태. agent_run 은 그대로 감사로그로 둔다.

    영업 건 하나에 활성 제안은 최대 1개다(sales_deal_id UNIQUE). 카드가 매번 실행 로그를
    역추적하지 않아도 되도록 계약 Agent가 정한 날짜와 사용자 선택값을 함께 보관한다.
    """

    __tablename__ = "contract_next_meeting_suggestion"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    sales_deal_id: Mapped[UUID] = mapped_column(ForeignKey("public.sales_deal.id"), unique=True)
    schedule_management_run_id: Mapped[UUID] = mapped_column(ForeignKey("public.agent_run.id"))
    target_date: Mapped[date | None] = mapped_column(Date)
    target_time: Mapped[time | None] = mapped_column(Time)
    selected_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    excluded_dates: Mapped[Any] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    refresh_reason: Mapped[str | None]
    applied_activity_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.activity.id"))
    # pending 보여줄 것 / rejected 재추천 요청 / expired 만료 / accepted 반영됨
    status_code: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
