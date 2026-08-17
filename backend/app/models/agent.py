from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey
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
    status_code: Mapped[str]
    model_name: Mapped[str]
    prompt_version: Mapped[str]
    source_refs: Mapped[Any] = mapped_column(JSONB, nullable=False)
    input_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    output_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[Any] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
