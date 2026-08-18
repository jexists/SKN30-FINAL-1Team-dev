from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# 이번 범위에서 사람이 시작할 수 있는 실행은 보고서 초안 하나다.
AgentCode = Literal["report_writing"]
AgentStatus = Literal["queued", "running", "completed", "failed"]

Guidance = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=2_000),
]


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_code: AgentCode
    report_id: UUID
    # 같은 키로 다시 보내면 새 실행을 만들지 않고 기존 실행을 돌려준다.
    idempotency_key: UUID
    guidance: Guidance | None = None


class ReportDraftField(BaseModel):
    """양식 항목 하나에 대한 제안. field_id 는 template_snapshot 의 항목 id 다."""

    model_config = ConfigDict(extra="forbid")

    field_id: str = Field(min_length=1, max_length=128)
    value: str = Field(max_length=5_000)


class ReportDraftOutput(BaseModel):
    """LLM 이 돌려줘야 하는 구조. 검증에 실패하면 실행을 failed 로 남긴다."""

    model_config = ConfigDict(extra="forbid")

    fields: list[ReportDraftField] = Field(max_length=50)
    summary: str = Field(default="", max_length=2_000)


class AgentRunRead(BaseModel):
    id: UUID
    agent_code: str
    trigger_code: str
    status_code: AgentStatus
    llm_model_name: str
    prompt_version: str
    requested_by_member_id: UUID | None
    source_refs: dict[str, Any]
    output_snapshot: dict[str, Any] | None
    evidence: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
