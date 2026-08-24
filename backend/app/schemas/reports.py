from datetime import date, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Text = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=254),
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=5_000),
]
Transcript = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=50_000),
]
SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=100),
]

# 유스케이스의 업무 보고는 미팅·일자별·주간 세 가지다.
# 미팅보고서는 일정 하나에 붙고, 주간은 기간을 덮는다.
# contract_status_briefing 은 일정관리 Agent 후보 승인 시 자동 생성되는 계약 현황 브리핑이다.
ReportKind = Literal["meeting", "daily", "weekly", "contract_status_briefing"]
# 유스케이스 RPT-004 의 검토 결과는 확인·반려·수정 요청 세 가지다.
# 팀원이 다루는 범위는 draft 와 submitted 두 개이고 검토 결과는 조회로만 나온다.
ReportStatus = Literal["draft", "submitted", "approved", "rejected", "changes_requested"]
# 제출을 시작할 수 있는 상태. 팀장이 수정 요청하면 팀원이 다시 고쳐 제출한다.
SubmittableStatus = Literal["draft", "changes_requested"]

_PERIOD_KINDS = ("weekly",)


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_period(kind: ReportKind, start: date | None, end: date | None) -> None:
    if kind == "meeting":
        return
    if kind in _PERIOD_KINDS and (start is None or end is None):
        raise ValueError("period_required")
    if start is not None and end is not None and end < start:
        raise ValueError("invalid_report_period")


class ReportCreate(_WriteModel):
    report_kind: ReportKind
    report_date: date
    period_start: date | None = None
    period_end: date | None = None
    source_activity_id: UUID | None = None
    recipient_member_id: UUID | None = None
    template_snapshot: dict[str, Any]
    content: dict[str, Any]
    transcript: Transcript | None = None
    note: LongText | None = None
    activity_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> Self:
        _check_period(self.report_kind, self.period_start, self.period_end)
        # 미팅보고서는 근거 일정이 곧 보고 대상이라 반드시 있어야 합니다.
        if self.report_kind == "meeting" and self.source_activity_id is None:
            raise ValueError("source_activity_required")
        if len(set(self.activity_ids)) != len(self.activity_ids):
            raise ValueError("duplicate_activity_ids")
        return self


class ReportPatch(_WriteModel):
    report_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    recipient_member_id: UUID | None = None
    template_snapshot: dict[str, Any] | None = None
    content: dict[str, Any] | None = None
    transcript: Transcript | None = None
    note: LongText | None = None
    activity_ids: list[UUID] | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.period_start is not None and self.period_end is not None:
            if self.period_end < self.period_start:
                raise ValueError("invalid_report_period")
        if self.activity_ids is not None and len(set(self.activity_ids)) != len(self.activity_ids):
            raise ValueError("duplicate_activity_ids")
        return self


class ReportSubmit(_WriteModel):
    expected_status_code: SubmittableStatus


class ReportActivityRead(BaseModel):
    activity_id: UUID
    title: str
    activity_type: str
    starts_at: datetime


class ReportRead(BaseModel):
    id: UUID
    team_id: UUID
    author_member_id: UUID
    author_display_name: str
    recipient_member_id: UUID | None
    recipient_display_name: str | None
    source_activity_id: UUID | None
    report_kind: ReportKind
    report_date: date
    period_start: date | None
    period_end: date | None
    status_code: ReportStatus
    template_snapshot: dict[str, Any]
    content: dict[str, Any]
    transcript: str | None
    source_snapshot: dict[str, Any] | None
    ai_evidence: dict[str, Any] | None
    note: str | None
    reviewed_by_member_id: UUID | None
    reviewed_at: datetime | None
    activities: list[ReportActivityRead]
    created_at: datetime
    updated_at: datetime


class ReportPage(BaseModel):
    items: list[ReportRead]
    skip: int
    limit: int
    total: int
    has_more: bool
    next_skip: int | None


class ReportPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    report_kind: list[ReportKind] | None = None
    status_code: list[ReportStatus] | None = None
    start_date: date | None = None
    end_date: date | None = None
    author_member_id: list[UUID] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=100)

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("invalid_report_range")
        return self
