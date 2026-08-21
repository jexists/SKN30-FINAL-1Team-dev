from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

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
