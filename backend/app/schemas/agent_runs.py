from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.activities import Note, OptionCode, SafeDateTime, Title

AgentCode = Literal[
    "report_writing",
    "meeting_analysis",
    "contract_management",
    "schedule_management",
]
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
    report_id: UUID | None = None
    customer_company_id: UUID | None = None
    sales_deal_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=100)
    parent_run_id: UUID | None = None
    sales_deal_id: UUID | None = None
    owner_member_id: UUID | None = None
    companion_member_ids: list[UUID] = Field(default_factory=list, max_length=20)
    preferred_starts_at: datetime | None = None
    preferred_ends_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    activity_type: Literal["meeting", "task"] | None = None
    # 같은 키로 다시 보내면 새 실행을 만들지 않고 기존 실행을 돌려준다.
    idempotency_key: UUID
    guidance: Guidance | None = None

    @model_validator(mode="after")
    def _check_agent_input(self):
        if self.agent_code != "report_writing" and self.guidance is not None:
            raise ValueError("guidance_not_supported")
        if self.agent_code in {"report_writing", "meeting_analysis"}:
            if self.report_id is None:
                raise ValueError("report_id_required")
        elif self.agent_code == "contract_management":
            if self.customer_company_id is None:
                raise ValueError("customer_company_id_required")
        else:
            required = {
                "sales_deal_id": self.sales_deal_id,
                "owner_member_id": self.owner_member_id,
                "preferred_starts_at": self.preferred_starts_at,
                "preferred_ends_at": self.preferred_ends_at,
                "duration_minutes": self.duration_minutes,
                "activity_type": self.activity_type,
            }
            if missing := [name for name, value in required.items() if value is None]:
                raise ValueError(f"schedule_input_required:{','.join(missing)}")
            assert self.preferred_starts_at is not None
            assert self.preferred_ends_at is not None
            if (
                self.preferred_starts_at.utcoffset() is None
                or self.preferred_ends_at.utcoffset() is None
            ):
                raise ValueError("timezone_offset_required")
            if self.preferred_starts_at >= self.preferred_ends_at:
                raise ValueError("preferred_date_range_invalid")

        allowed = {
            "report_writing": {"report_id", "guidance"},
            "meeting_analysis": {"report_id"},
            "contract_management": {"customer_company_id", "sales_deal_ids"},
            "schedule_management": {
                "parent_run_id",
                "sales_deal_id",
                "owner_member_id",
                "companion_member_ids",
                "preferred_starts_at",
                "preferred_ends_at",
                "duration_minutes",
                "activity_type",
            },
        }[self.agent_code]
        optional_values = self.model_dump(exclude={"agent_code", "idempotency_key"})
        supplied = {
            name for name, value in optional_values.items() if value is not None and value != []
        }
        if unexpected := supplied - allowed:
            raise ValueError(f"agent_input_not_supported:{','.join(sorted(unexpected))}")
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


class AgentApprovalCreate(BaseModel):
    """일정 후보 승인 요청. 서버가 최종 값을 다시 검증하며, candidate_id 는 신뢰하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: UUID
    title: Title
    category_code: OptionCode
    action_tag: OptionCode | None = None
    starts_at: SafeDateTime
    ends_at: SafeDateTime
    # 생략하면 원 실행 요청의 owner/companions 를 그대로 쓴다.
    owner_member_id: UUID | None = None
    companion_member_ids: list[UUID] | None = None
    note: Note | None = None

    @model_validator(mode="after")
    def _check_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class AgentApprovalRead(BaseModel):
    id: UUID
    agent_run_id: UUID
    activity_id: UUID
    report_id: UUID
    created_at: datetime
