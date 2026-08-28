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
    # 이 실행이 어느 영업 건에 관한 것인지. 딜 하나로 좁혀지지 않는 실행(예: 담당자
    # 포트폴리오 전체를 도는 contract_management_select_candidates, 회사 단위인
    # contract_management_next_meeting)은 NULL. 딜 기준 히스토리 조회(sales_deal_id 로
    # 필터링)를 컬럼으로 가능하게 하려고 둔다 — 이전에는 source_refs(JSONB) 안에만 있었다.
    sales_deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.sales_deal.id"))
    agent_code: Mapped[str]
    trigger_code: Mapped[str]
    idempotency_key: Mapped[UUID | None]
    status_code: Mapped[str]
    llm_model_name: Mapped[str]
    prompt_version: Mapped[str]
    source_refs: Mapped[Any] = mapped_column(JSONB, nullable=False)
    input_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    output_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[Any] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]


class ContractNextMeetingSuggestion(Base):
    """캘린더 "AI 추천 일정" 패널이 조회하는 상태. agent_run 은 그대로 감사로그로 둔다.

    영업 건 하나에 활성 제안은 최대 1개다(sales_deal_id UNIQUE). 날짜·시간·사유 같은 실제
    내용은 여기 복제하지 않는다 — schedule_management_run_id 로 agent_run.output_snapshot 을
    조회한다. 계약에이전트_설계.md 6장 "제안 상태 저장" 참고.
    """

    __tablename__ = "contract_next_meeting_suggestion"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("public.team.id"))
    sales_deal_id: Mapped[UUID] = mapped_column(ForeignKey("public.sales_deal.id"), unique=True)
    schedule_management_run_id: Mapped[UUID] = mapped_column(ForeignKey("public.agent_run.id"))
    status_code: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
