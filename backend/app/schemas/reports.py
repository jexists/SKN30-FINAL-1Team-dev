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

# 유스케이스의 업무 보고는 미팅·일자별·주간·월간 네 가지다.
# 업무보고서는 일정 하나에 붙고, 주간과 월간은 기간을 덮는다.
# 주간은 그 주의 일일보고서를, 월간은 그 달의 주간보고서를 자료로 쓴다.
ReportKind = Literal["meeting", "daily", "weekly", "monthly"]
# 유스케이스 RPT-004 의 검토 결과는 확인·반려·수정 요청 세 가지다.
# 팀원이 다루는 범위는 draft 와 submitted 두 개이고 검토 결과는 조회로만 나온다.
ReportStatus = Literal["draft", "submitted", "approved", "rejected", "changes_requested"]
# 제출을 시작할 수 있는 상태. 팀장이 수정 요청하면 팀원이 다시 고쳐 제출한다.
SubmittableStatus = Literal["draft", "changes_requested"]

_PERIOD_KINDS = ("weekly", "monthly")


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
        # 업무보고서는 근거 일정이 곧 보고 대상이라 반드시 있어야 합니다.
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


class ReportFilterOptions(BaseModel):
    """작성 리스트 필터의 선택지.

    목록에 실제로 있는 값만 내놓아야 고르고도 0 건이 되지 않는다. 예전에는 화면이
    받아 둔 전건에서 뽑았는데, 한 쪽만 받는 지금은 화면이 못 본 값까지 서버가 센다.
    """

    approvers: list[str]
    hospitals: list[str]


class ReportFilterOptionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_member_id: list[UUID] | None = None


class ReportPageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: SearchQuery | None = None
    report_kind: list[ReportKind] | None = None
    status_code: list[ReportStatus] | None = None
    start_date: date | None = None
    end_date: date | None = None
    author_member_id: list[UUID] | None = None
    # "이 일정으로 쓴 보고서가 이미 있는가" 를 묻는 조회에 쓴다. 목록을 통째로 받아 뒤지면
    # 페이지 밖에 있는 보고서를 못 찾고 같은 일정에 보고서를 또 만든다.
    source_activity_id: UUID | None = None
    # 보고 대상과 고객사는 컬럼이 아니라 content 안에 있다. 그래도 서버가 걸러야 한다.
    # 전건을 받아 화면에서 거르면 쪽으로 끊는 순간 첫 쪽 밖의 일치 항목을 놓친다.
    approver: list[Text] | None = None
    hospital: list[Text] | None = None
    skip: int = Field(default=0, ge=0, le=9_223_372_036_854_775_807)
    limit: int = Field(default=30, ge=1, le=30)

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("invalid_report_range")
        return self
