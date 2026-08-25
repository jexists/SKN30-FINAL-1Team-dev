from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

AgentCode = Literal[
    "report_writing",
    "meeting_analysis",
    "contract_management_select_candidates",
    "contract_management_next_meeting",
    "contract_management_briefing",
    "schedule_management",
]
# queued -> running -> completed 또는 failed 로만 움직인다.
AgentStatus = Literal["queued", "running", "completed", "failed"]

# 사람이 덧붙이는 지시문. 그대로 프롬프트에 들어가므로 길이를 잘라둔다.
Guidance = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=2_000),
]

# agent_code 별로 허용되는 식별 필드만 채울 수 있다. 나머지는 반드시 비워야 한다.
# 값이 dict 형태면 그 필드가 필수라는 뜻이고, "optional" 이면 있어도 없어도 된다.
_REQUIRED_FIELDS: dict[str, set[str]] = {
    "report_writing": {"report_id"},
    "meeting_analysis": {"report_id"},
    # 로그인한 담당자의 전체 포트폴리오를 대상으로 돈다 — 특정 대상을 지정하지 않는다.
    "contract_management_select_candidates": set(),
    "contract_management_next_meeting": {"customer_company_id"},
    "contract_management_briefing": {"activity_id", "parent_run_id"},
    "schedule_management": {"sales_deal_id"},
}
_OPTIONAL_FIELDS: dict[str, set[str]] = {
    "schedule_management": {
        "parent_run_id",
        "preferred_starts_at",
        "preferred_ends_at",
        "duration_minutes",
    },
}
_IDENTIFYING_FIELDS = {
    "report_id",
    "customer_company_id",
    "sales_deal_id",
    "activity_id",
    "parent_run_id",
    "preferred_starts_at",
    "preferred_ends_at",
    "duration_minutes",
}


class AgentRunCreate(BaseModel):
    # 오타난 필드가 조용히 무시되지 않도록 막는다.
    model_config = ConfigDict(extra="forbid")

    agent_code: AgentCode
    # 실행 원문을 가진 보고서. report_writing/meeting_analysis 에서만 쓴다.
    report_id: UUID | None = None
    # 회사 단위로 실행하는 계약관리 에이전트가 쓴다.
    customer_company_id: UUID | None = None
    # 딜 단위로 실행하는 일정관리 에이전트가 쓴다.
    sales_deal_id: UUID | None = None
    # 브리핑을 연결할 확정 미팅 일정. contract_management_briefing 에서만 쓴다.
    activity_id: UUID | None = None
    # 앞선 실행 결과를 이어받을 때만 쓴다 (일정 등록을 만든 일정관리 실행 등).
    parent_run_id: UUID | None = None
    # parent_run_id 가 없는 일정관리 실행에서 직접 지정하는 선호 시간대.
    preferred_starts_at: str | None = None
    preferred_ends_at: str | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    # 같은 키로 다시 보내면 새 실행을 만들지 않고 기존 실행을 돌려준다.
    idempotency_key: UUID
    guidance: Guidance | None = None

    @model_validator(mode="after")
    def _check_guidance(self):
        if self.agent_code != "report_writing" and self.guidance is not None:
            raise ValueError("guidance_not_supported")
        return self

    @model_validator(mode="after")
    def _check_identifying_fields(self):
        required = _REQUIRED_FIELDS[self.agent_code]
        optional = _OPTIONAL_FIELDS.get(self.agent_code, set())
        allowed = required | optional

        for name in required:
            if getattr(self, name) is None:
                raise ValueError(f"{name}_required")
        for name in _IDENTIFYING_FIELDS - allowed:
            if getattr(self, name) is not None:
                raise ValueError(f"{name}_not_supported")

        if self.agent_code == "schedule_management" and self.parent_run_id is None:
            # 계약관리 제안이 없으면 선호 시간대를 직접 받아야 한다.
            missing = {"preferred_starts_at", "preferred_ends_at", "duration_minutes"} - {
                name for name in optional if getattr(self, name) is not None
            }
            if missing:
                raise ValueError("preferred_schedule_required_without_parent_run")
        if self.agent_code == "schedule_management" and self.parent_run_id is not None:
            if (
                self.preferred_starts_at is not None
                or self.preferred_ends_at is not None
                or self.duration_minutes is not None
            ):
                raise ValueError("preferred_schedule_not_supported_with_parent_run")
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
