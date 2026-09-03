from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.reports import (
    REPORT_JSON_MAX_BYTES,
    ReportKind,
    Transcript,
    validate_body_template,
    validate_body_values,
    validate_content_title,
    validate_report_json_size,
)

AgentCode = Literal[
    "report_writing",
    "meeting_processing",
    "contract_management_select_candidates",
    "contract_management_next_meeting",
    "contract_management_briefing",
    "schedule_management",
]
QueuedAgentCode = Literal[
    "contract_management_select_candidates",
    "contract_management_next_meeting",
    "contract_management_briefing",
    "schedule_management",
]
# queued -> running -> completed 또는 failed 로만 움직인다.
AgentStatus = Literal["queued", "running", "completed", "partial", "failed", "cancelled"]

# 사람이 덧붙이는 지시문. 그대로 프롬프트에 들어가므로 길이를 잘라둔다.
Guidance = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=2_000),
]

REPORT_GENERATION_JSON_MAX_BYTES = REPORT_JSON_MAX_BYTES

# agent_code 별로 허용되는 식별 필드만 채울 수 있다. 나머지는 반드시 비워야 한다.
# 값이 dict 형태면 그 필드가 필수라는 뜻이고, "optional" 이면 있어도 없어도 된다.
_REQUIRED_FIELDS: dict[str, set[str]] = {
    # 로그인한 담당자의 전체 포트폴리오를 대상으로 돈다 — 특정 대상을 지정하지 않는다.
    "contract_management_select_candidates": set(),
    "contract_management_next_meeting": {"customer_company_id"},
    "contract_management_briefing": {"activity_id"},
    "schedule_management": {"sales_deal_id"},
}
_OPTIONAL_FIELDS: dict[str, set[str]] = {
    # AI 제안(일정관리 실행)을 승인해서 만든 일정만 부모를 기록한다. 캘린더 직접 입력이나
    # 팀장 대리 입력처럼 AI 제안을 거치지 않은 일정은 부모 없이 activity_id만으로 만든다.
    "contract_management_briefing": {"parent_run_id"},
    "schedule_management": {
        "parent_run_id",
        "preferred_starts_at",
        "preferred_ends_at",
        "duration_minutes",
    },
}
_IDENTIFYING_FIELDS = {
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

    agent_code: QueuedAgentCode
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


class ReportGenerationInput(BaseModel):
    """재접속 때 작성 화면을 복구할 수 있는 사용자 생성 입력."""

    model_config = ConfigDict(extra="forbid")

    report_kind: ReportKind
    report_date: date
    period_start: date | None = None
    period_end: date | None = None
    source_activity_id: UUID | None = None
    sales_deal_ids: list[UUID] = Field(default_factory=list, max_length=100)
    template_snapshot: dict[str, Any]
    content: dict[str, Any]
    transcript: Transcript | None = None
    guidance: Guidance | None = None

    @model_validator(mode="after")
    def _validate_scope(self):
        if self.report_kind == "meeting":
            if self.source_activity_id is None:
                raise ValueError("source_activity_required")
            if not self.sales_deal_ids:
                raise ValueError("sales_deal_ids_required")
            if self.transcript is None:
                raise ValueError("transcript_required")
            if self.period_start is not None or self.period_end is not None:
                raise ValueError("period_not_supported")
            if self.guidance is not None:
                raise ValueError("guidance_not_supported")
        else:
            if self.source_activity_id is not None or self.sales_deal_ids or self.transcript:
                raise ValueError("meeting_input_not_supported")
            if self.report_kind == "daily":
                if self.period_start is not None or self.period_end is not None:
                    raise ValueError("period_not_supported")
            elif self.period_start is None or self.period_end is None:
                raise ValueError("period_required")
            elif self.period_end < self.period_start:
                raise ValueError("invalid_report_period")
        if len(set(self.sales_deal_ids)) != len(self.sales_deal_ids):
            raise ValueError("sales_deal_ids_duplicate")
        return self


class ReportGenerationCreate(ReportGenerationInput):
    """Canonical 보고서를 만들지 않고 실행 시점에 고정하는 생성 요청."""

    idempotency_key: UUID

    @model_validator(mode="after")
    def _validate_body_contract(self):
        validate_body_template(self.template_snapshot)
        validate_body_values(self.content)
        validate_content_title(self.content)
        return self

    @model_validator(mode="after")
    def _validate_json_size(self):
        validate_report_json_size(
            template_snapshot=self.template_snapshot,
            content=self.content,
        )
        return self


class ReportGenerationScope(BaseModel):
    """화면 재진입 시 같은 생성 범위를 계산하는 조회 입력."""

    model_config = ConfigDict(extra="forbid")

    report_kind: ReportKind
    source_activity_id: UUID | None = None
    report_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None

    @model_validator(mode="after")
    def _validate_scope(self):
        if self.report_kind == "meeting":
            if self.source_activity_id is None:
                raise ValueError("source_activity_required")
            if any((self.report_date, self.period_start, self.period_end)):
                raise ValueError("report_scope_not_supported")
        elif self.report_kind == "daily":
            if self.report_date is None:
                raise ValueError("report_date_required")
            if any((self.source_activity_id, self.period_start, self.period_end)):
                raise ValueError("report_scope_not_supported")
        else:
            if self.period_start is None or self.period_end is None:
                raise ValueError("period_required")
            if self.period_end < self.period_start:
                raise ValueError("invalid_report_period")
            if self.source_activity_id is not None or self.report_date is not None:
                raise ValueError("report_scope_not_supported")
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
    report_id: UUID | None
    # 이 실행이 무엇을 참조했는지 (예: report_id)
    source_refs: dict[str, Any]
    # 생성 요청자 본인에게만, 24시간 보존 기간 안에서 돌려주는 화면 복구 입력이다.
    generation_input: ReportGenerationInput | None
    # 완료 전에는 없다. 보고서에 자동 반영되지 않는 "제안" 초안이다.
    output_snapshot: dict[str, Any] | None
    # 결과 검토에 필요한 프롬프트 버전과 요약을 남긴다.
    evidence: dict[str, Any] | None
    # 실패했을 때만 채워진다.
    error_message: str | None
    error_code: str | None
    current_stage_code: str | None
    attempt_count: int
    payload_expires_at: datetime | None
    payload_redacted_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    # 이 API 에서는 서울 시간으로 변환해서 내보낸다.
    created_at: datetime | None
    heartbeat_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
