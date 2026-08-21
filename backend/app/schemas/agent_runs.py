from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

AgentCode = Literal["report_writing", "meeting_analysis"]
# queued -> running -> completed 또는 failed 로만 움직인다.
AgentStatus = Literal["queued", "running", "completed", "failed"]

# 사람이 덧붙이는 지시문. 그대로 프롬프트에 들어가므로 길이를 잘라둔다.
Guidance = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=2_000),
]


class AgentRunCreate(BaseModel):
    # 오타난 필드가 조용히 무시되지 않도록 막는다.
    model_config = ConfigDict(extra="forbid")

    agent_code: AgentCode
    # 실행 원문을 가진 보고서. 작성 중(draft)인 것만 허용된다.
    report_id: UUID
    # 같은 키로 다시 보내면 새 실행을 만들지 않고 기존 실행을 돌려준다.
    idempotency_key: UUID
    guidance: Guidance | None = None

    @model_validator(mode="after")
    def _check_guidance(self):
        if self.agent_code != "report_writing" and self.guidance is not None:
            raise ValueError("guidance_not_supported")
        return self


class AgentRunRead(BaseModel):
    """실행 이력 응답. 어떤 모델·프롬프트로 돌렸는지까지 함께 남긴다."""

    id: UUID
    agent_code: str
    trigger_code: str
    status_code: AgentStatus
    llm_model_name: str
    prompt_version: str
    requested_by_member_id: UUID | None
    # 이 실행이 무엇을 참조했는지 (예: report_id)
    source_refs: dict[str, Any]
    # 완료 전에는 없다. 보고서에 자동 반영되지 않는 "제안" 초안이다.
    output_snapshot: dict[str, Any] | None
    # 결과 검토에 필요한 프롬프트 버전과 요약을 남긴다.
    evidence: dict[str, Any] | None
    # 실패했을 때만 채워진다.
    error_message: str | None
    # 이 API 에서는 서울 시간으로 변환해서 내보낸다.
    started_at: datetime | None
    finished_at: datetime | None
