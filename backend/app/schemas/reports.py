import json
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

REPORT_TITLE_MAX_LENGTH = 254
REPORT_JSON_MAX_BYTES = 256 * 1024

Text = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        min_length=1,
        max_length=REPORT_TITLE_MAX_LENGTH,
    ),
]
LongText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=5_000),
]
REPORT_BODY_MAX_LENGTH = 50_000
ReportBody = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        min_length=1,
        max_length=REPORT_BODY_MAX_LENGTH,
    ),
]
Transcript = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=50_000),
]
SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, min_length=1, max_length=100),
]
SnapshotNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, strict=True, max_length=5_000),
]

# 유스케이스의 업무 보고는 미팅·일자별·주간·월간 네 가지다.
# 업무보고서는 일정 하나에 붙고, 주간과 월간은 기간을 덮는다.
# 주간은 그 주의 일일보고서를, 월간은 그 달의 주간보고서를 자료로 쓴다.
ReportKind = Literal["meeting", "daily", "weekly", "monthly"]
# 유스케이스 RPT-004 의 검토 결과는 확인·반려·수정 요청 세 가지다.
# 팀원이 다루는 범위는 draft 와 submitted 두 개이고 검토 결과는 조회로만 나온다.
ReportStatus = Literal["draft", "submitted", "approved", "changes_requested"]
# 조회 필터만 구버전 rejected를 받아 0건으로 처리한다. 신규 저장·응답 상태에는 허용하지 않는다.
ReportFilterStatus = Literal["draft", "submitted", "approved", "changes_requested", "rejected"]
# 제출을 시작할 수 있는 상태. 팀장이 수정 요청하면 팀원이 다시 고쳐 제출한다.
SubmittableStatus = Literal["draft", "changes_requested"]
# 팀장이 검토할 수 있는 상태. 제출된 것만 본다.
ReviewableStatus = Literal["submitted"]
# 검토 결과. 반려는 rejected 가 아니라 changes_requested 로 간다. 반려한 보고서는
# 팀원이 다시 고쳐 내야 하는데, 고칠 수 있는 상태(_EDITABLE_STATUSES)가 그쪽이다.
ReviewDecision = Literal["approve", "reject"]
REVIEW_DECISION_STATUS: dict[str, str] = {
    "approve": "approved",
    "reject": "changes_requested",
}

_PERIOD_KINDS = ("weekly", "monthly")


class _WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def validate_body_template(template_snapshot: dict[str, Any]) -> None:
    fields = template_snapshot.get("fields")
    if (
        not isinstance(fields, list)
        or len(fields) != 1
        or not isinstance(fields[0], dict)
        or fields[0].get("id") != "body"
    ):
        raise ValueError("report_template_body_only")


def validate_body_values(content: dict[str, Any]) -> None:
    values = content.get("values")
    if values is None:
        return
    if not isinstance(values, dict):
        raise ValueError("report_values_invalid")
    if set(values) - {"body"}:
        raise ValueError("report_values_body_only")
    if "body" in values and not isinstance(values["body"], str):
        raise ValueError("report_body_invalid")


def validate_content_title(content: dict[str, Any]) -> None:
    if "title" not in content or content["title"] is None:
        return
    title = content["title"]
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title.strip()) > REPORT_TITLE_MAX_LENGTH
    ):
        raise ValueError("report_title_invalid")


def validate_report_json_size(**fields: Any) -> None:
    """Apply one byte limit to every client-controlled report JSON field."""
    for field_name, value in fields.items():
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(serialized) > REPORT_JSON_MAX_BYTES:
            raise ValueError(f"{field_name}_too_large")


def _check_period(kind: ReportKind, start: date | None, end: date | None) -> None:
    if kind in {"meeting", "daily"}:
        if start is not None or end is not None:
            raise ValueError("period_not_supported")
        return
    if kind in _PERIOD_KINDS and (start is None or end is None):
        raise ValueError("period_required")
    if start is not None and end is not None and end < start:
        raise ValueError("invalid_report_period")


class ReportDealSnapshot(_WriteModel):
    id: UUID
    label: Text
    note: SnapshotNote | None = None


class ReportDealWrite(_WriteModel):
    sales_deal_id: UUID
    deal_snapshot: ReportDealSnapshot
    content: dict[str, Any]
    position: int | None = Field(default=None, ge=0, le=99)
    title: Text | None = None
    body: ReportBody
    structured_values: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_snapshot_id(self) -> Self:
        if self.deal_snapshot.id != self.sales_deal_id:
            raise ValueError("deal_snapshot_id_mismatch")
        validate_body_values(self.content)
        validate_content_title(self.content)
        validate_report_json_size(content=self.content)
        if self.structured_values:
            raise ValueError("structured_values_not_supported")
        return self


class ReportDealRead(BaseModel):
    sales_deal_id: UUID
    deal_snapshot: dict[str, Any]
    content: dict[str, Any]
    position: int | None
    deal_no_snapshot: str | None
    deal_title_snapshot: str | None
    title: str | None
    body: str | None
    structured_values: dict[str, Any]
    ai_evidence: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ReportFinalize(_WriteModel):
    """사람이 승인한 최종값을 한 번에 저장하고 제출하는 요청."""

    report_kind: ReportKind
    report_date: date
    period_start: date | None = None
    period_end: date | None = None
    source_activity_id: UUID | None = None
    sales_deal_id: UUID | None = None
    deal_sections: list[ReportDealWrite] = Field(default_factory=list, max_length=100)
    recipient_member_id: UUID | None = None
    template_snapshot: dict[str, Any]
    content: dict[str, Any]
    title: Text | None = None
    body: ReportBody | None = None
    common_body: ReportBody | None = None
    unassigned_body: ReportBody | None = None
    structured_values: dict[str, Any] = Field(default_factory=dict)
    transcript: Transcript | None = None
    note: LongText | None = None
    activity_ids: list[UUID] = Field(default_factory=list)
    idempotency_key: UUID
    agent_run_id: UUID | None = None
    report_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)
    expected_status_code: SubmittableStatus | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        _check_period(self.report_kind, self.period_start, self.period_end)
        validate_body_template(self.template_snapshot)
        validate_body_values(self.content)
        validate_content_title(self.content)
        validate_report_json_size(
            template_snapshot=self.template_snapshot,
            content=self.content,
        )
        if self.structured_values:
            raise ValueError("structured_values_not_supported")
        # 업무보고서는 근거 일정이 곧 보고 대상이라 반드시 있어야 합니다.
        if self.report_kind == "meeting":
            if self.source_activity_id is None:
                raise ValueError("source_activity_required")
            if not self.deal_sections:
                raise ValueError("deal_sections_required")
            if self.sales_deal_id is not None:
                raise ValueError("sales_deal_not_supported")
            if self.body is not None:
                raise ValueError("report_body_not_supported")
            if self.activity_ids:
                raise ValueError("activity_ids_not_supported")
        else:
            if self.body is None:
                raise ValueError("report_body_required")
            if self.sales_deal_id is not None or self.deal_sections:
                raise ValueError("deal_sections_not_supported")
            if self.source_activity_id is not None:
                raise ValueError("source_activity_not_supported")
            if self.common_body is not None or self.unassigned_body is not None:
                raise ValueError("meeting_shared_not_supported")
        deal_ids = [section.sales_deal_id for section in self.deal_sections]
        if len(set(deal_ids)) != len(deal_ids):
            raise ValueError("duplicate_deal_sections")
        positions = [
            section.position if section.position is not None else index
            for index, section in enumerate(self.deal_sections)
        ]
        if len(set(positions)) != len(positions):
            raise ValueError("duplicate_deal_positions")
        if len(set(self.activity_ids)) != len(self.activity_ids):
            raise ValueError("duplicate_activity_ids")
        return self

    @model_validator(mode="after")
    def _validate_existing_revision(self) -> Self:
        expected = self.expected_version is not None or self.expected_status_code is not None
        if self.report_id is None and expected:
            raise ValueError("report_id_required")
        if self.report_id is not None and (
            self.expected_version is None or self.expected_status_code is None
        ):
            raise ValueError("report_revision_expectation_required")
        return self


class ReportReview(_WriteModel):
    """팀장의 검토 결과.

    반려에는 까닭이 있어야 한다. 무엇을 고쳐야 하는지 없이 돌려보내면 팀원이 같은 것을
    그대로 다시 낸다.
    """

    decision: ReviewDecision
    reason: LongText | None = None
    expected_status_code: ReviewableStatus
    # V2 이전 submitted 보고서는 아직 확정본 ID가 없다. 그 경우에만 null을 받아
    # 잠긴 현재 본문을 최초 확정본으로 만든 뒤 같은 요청에서 검토한다.
    expected_submission_id: UUID | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.decision == "reject" and self.reason is None:
            raise ValueError("review_reason_required")
        return self


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
    sales_deal_id: UUID | None
    deal_sections: list[ReportDealRead]
    report_kind: ReportKind
    report_date: date
    period_start: date | None
    period_end: date | None
    status_code: ReportStatus
    version: int
    generation_input_version: int
    current_submission_id: UUID | None
    template_snapshot: dict[str, Any]
    content: dict[str, Any]
    customer_company_id: UUID | None
    title: str | None
    body: str | None
    common_body: str | None
    unassigned_body: str | None
    structured_values: dict[str, Any]
    transcript: str | None
    source_snapshot: dict[str, Any] | None
    ai_evidence: dict[str, Any] | None
    note: str | None
    # 팀장이 반려하며 남긴 사유. 확정하면 비운다.
    review_note: str | None
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
    status_code: list[ReportFilterStatus] | None = None
    start_date: date | None = None
    end_date: date | None = None
    author_member_id: list[UUID] | None = None
    # "이 일정으로 쓴 보고서가 이미 있는가" 를 묻는 조회에 쓴다. 목록을 통째로 받아 뒤지면
    # 페이지 밖에 있는 보고서를 못 찾고 같은 일정에 보고서를 또 만든다.
    # 여러 개를 받는 까닭은 대시보드가 하루치 일정의 보고서 유무를 한 번에 묻기 때문이다.
    source_activity_id: list[UUID] | None = None
    sales_deal_id: UUID | None = None
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
