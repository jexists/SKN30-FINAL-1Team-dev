"""미팅 보고서의 입력·출력 계약과 근거·렌더링 검증."""

import hashlib
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.meeting_content import MeetingContentInput, MeetingEvidenceLedger, SegmentId
from app.schemas.reports import REPORT_BODY_MAX_LENGTH
from app.services.agent_logging import log_agent_event

COMMON_SCOPES = {"meeting_context", "company_context", "all_selected_deals"}
UNASSIGNED_SCOPES = {"unresolved", "out_of_scope"}
NO_DEAL_EVIDENCE_TEXT = "이번 미팅에서 구체적 논의 없음"


class ReportWritingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(min_length=1, max_length=50_000)
    evidence: MeetingEvidenceLedger
    crm_context: dict[str, Any] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _check_evidence(self):
        MeetingContentInput(
            transcript=self.transcript,
            selected_deal_ids=self.evidence.selected_deal_ids,
            segments=[item.segment for item in self.evidence.items],
        )
        if hashlib.sha256(self.transcript.encode()).hexdigest() != self.evidence.transcript_sha256:
            raise ValueError("report_transcript_hash_mismatch")
        return self


class ReportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=REPORT_BODY_MAX_LENGTH)
    evidence_ids: list[SegmentId] = Field(max_length=5_000)

    @model_validator(mode="after")
    def _check_body(self):
        if not self.body.strip():
            raise ValueError("report_body_empty")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("report_evidence_duplicate")
        return self


class DealReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 구버전 output_snapshot에는 title이 없다. 새 생성은 구조 검사에서 필수로 강제한다.
    sales_deal_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=254)
    body: str = Field(min_length=1, max_length=REPORT_BODY_MAX_LENGTH)
    evidence_ids: list[SegmentId] = Field(max_length=5_000)

    @model_validator(mode="after")
    def _check_body(self):
        if self.title is not None and not self.title.strip():
            raise ValueError("report_title_empty")
        ReportBody(body=self.body, evidence_ids=self.evidence_ids)
        return self


class FreeformMeetingReports(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deal_reports: list[DealReport] = Field(max_length=100)
    common_report: ReportBody | None = None
    unassigned_report: ReportBody | None = None

    @model_validator(mode="after")
    def _check_content(self):
        if not self.deal_reports and self.common_report is None and self.unassigned_report is None:
            raise ValueError("meeting_report_body_required")
        return self


def structural_issues(
    source: ReportWritingInput,
    draft: FreeformMeetingReports,
    *,
    require_titles: bool = True,
) -> list[dict[str, Any]]:
    """같은 strict 검사를 최종 제출과 수정 피드백에서 공유한다. 원문은 로그에 쓰지 않는다."""
    issues: list[dict[str, Any]] = []
    texts = {item.segment.segment_id: item.segment.text for item in source.evidence.items}

    def add(code, path, expected, actual, action, *, quote_ids=()):
        issues.append(
            {
                "code": code,
                "path": path,
                "expected_ids": sorted(expected),
                "actual_ids": sorted(actual),
                "missing_ids": sorted(expected - actual),
                "unexpected_ids": sorted(actual - expected),
                "required_raw_quotes": [
                    {"segment_id": segment_id, "text": texts[segment_id]}
                    for segment_id in sorted(quote_ids)
                    if segment_id in texts
                ],
                "repair_action": action,
            }
        )

    reports = {report.sales_deal_id: report for report in draft.deal_reports}
    if len(reports) != len(draft.deal_reports) or set(reports) != set(
        source.evidence.selected_deal_ids
    ):
        add(
            "report_selected_deals_mismatch",
            "deal_reports",
            {str(value) for value in source.evidence.selected_deal_ids},
            {str(value) for value in reports},
            "선택된 각 sales_deal_id의 보고서를 정확히 한 개씩 남겨라. 중복을 합치고 "
            "다른 딜 보고서는 제거하되 그 딜의 사실을 선택 딜에 옮기지 마라.",
        )
        issues[-1]["duplicate_ids"] = sorted(
            str(value)
            for value in reports
            if sum(report.sales_deal_id == value for report in draft.deal_reports) > 1
        )

    common = {
        item.segment.segment_id
        for item in source.evidence.items
        if item.applicability.scope in COMMON_SCOPES
    }
    unassigned = {
        item.segment.segment_id
        for item in source.evidence.items
        if item.applicability.scope in UNASSIGNED_SCOPES
    }
    covered: set[str] = set()
    for index, report in enumerate(draft.deal_reports):
        deal_id = report.sales_deal_id
        required = {
            item.segment.segment_id
            for item in source.evidence.items
            if deal_id in item.applicability.deal_ids
        }
        refs = set(report.evidence_ids)
        if require_titles and required and report.title is None:
            add(
                "report_deal_title_missing",
                f"deal_reports[{index}].title",
                set(),
                set(),
                "이번 원문의 해당 딜 핵심을 요약한 비어 있지 않은 title을 작성하라.",
            )
            issues[-1]["sales_deal_id"] = str(deal_id)
        if require_titles and not required:
            for field, value in (("title", report.title), ("body", report.body)):
                if value is not None and value.strip() == NO_DEAL_EVIDENCE_TEXT:
                    continue
                add(
                    "report_deal_no_evidence_marker_missing",
                    f"deal_reports[{index}].{field}",
                    set(),
                    set(),
                    f"현재 원문에 이 딜의 근거가 없으므로 {field}에 정확히 "
                    f"'{NO_DEAL_EVIDENCE_TEXT}'을 넣어라. 과거 이력으로 채우지 마라.",
                )
                issues[-1]["sales_deal_id"] = str(deal_id)
        if not required <= refs or not refs <= required | common:
            add(
                "report_deal_evidence_mismatch",
                f"deal_reports[{index}].evidence_ids",
                required,
                refs - common,
                "missing_ids의 내용을 이 딜 본문에 반영하고 ID를 추가하라. "
                "unexpected_ids와 그에만 의존하는 문장을 이 딜에서 제거하라. "
                "공통 근거는 선택적으로 포함할 수 있다. ID만 채우지 마라.",
                quote_ids=required - refs,
            )
            issues[-1]["sales_deal_id"] = str(deal_id)
            issues[-1]["actual_ids"] = sorted(refs)
            issues[-1]["allowed_ids"] = sorted(required | common)
        covered.update(refs)

    if common:
        refs = set(draft.common_report.evidence_ids) if draft.common_report else set()
        if refs != common:
            add(
                "report_common_evidence_mismatch",
                "common_report.evidence_ids",
                common,
                refs,
                "common_report에 expected_ids의 공통 내용을 빠짐없이 작성하라. "
                "특정 딜 본문에만 넣어 대신하지 마라. 각 딜별 보고서에는 이 공통 본문이 "
                "함께 전달된다. unexpected_ids와 그 내용은 원래 귀속 섹션에 남겨라. "
                "공통을 딜 미지정으로 표현하지 마라.",
                quote_ids=common - refs,
            )
        covered.update(refs)
    elif draft.common_report is not None:
        add(
            "report_common_without_evidence",
            "common_report",
            set(),
            set(draft.common_report.evidence_ids),
            "공통 근거가 없으므로 common_report를 null로 바꿔라.",
        )
    if unassigned:
        refs = set(draft.unassigned_report.evidence_ids) if draft.unassigned_report else set()
        if refs != unassigned:
            add(
                "report_unassigned_evidence_missing",
                "unassigned_report.evidence_ids",
                unassigned,
                refs,
                "unassigned_report를 만들거나 수정하여 expected_ids만 정확히 넣어라. "
                "UI 제목이나 내부 분류명을 본문에 반복하지 말고 required_raw_quotes를 "
                "사실 관계와 불확실성을 보존해 자연스러운 보고 문장으로 반영하라. "
                "대상을 추측하거나 "
                "common_report/딜 보고서로 이동하지 마라.",
                quote_ids=unassigned,
            )
        covered.update(refs)
    elif draft.unassigned_report is not None:
        add(
            "report_unassigned_without_evidence",
            "unassigned_report",
            set(),
            set(draft.unassigned_report.evidence_ids),
            "미지정 근거가 없으므로 unassigned_report를 null로 바꿔라.",
        )
    if covered != set(texts):
        add(
            "report_evidence_coverage_missing",
            "evidence_ids",
            set(texts),
            covered,
            "아직 반영하지 않은 근거를 원래 귀속의 보고서 본문과 evidence_ids에 함께 "
            "복원하라. 공통은 common_report에, 미지정은 "
            "unassigned_report에만 남겨라. 없는 ID는 제거하라.",
            quote_ids=set(texts) - covered,
        )
    return issues


def log_structural_issues(issues: list[dict[str, Any]], **fields) -> None:
    for issue in issues:
        log_agent_event(
            "report_writing.review_validation",
            outcome="failed",
            reason_code=issue["code"],
            validation_path=issue["path"],
            sales_deal_id=issue.get("sales_deal_id"),
            missing_evidence_ids=",".join(issue["missing_ids"]),
            unexpected_evidence_ids=",".join(issue["unexpected_ids"]),
            **fields,
        )


def validate_reports(
    source: ReportWritingInput,
    draft: FreeformMeetingReports,
    *,
    require_titles: bool = True,
) -> None:
    """딜·근거 귀속과 전체 근거 ID 사용을 검사하며 본문 원문 보존은 판단하지 않는다."""
    if issues := structural_issues(source, draft, require_titles=require_titles):
        log_structural_issues(issues)
        raise ValueError(issues[0]["code"])


def mechanical_contract_issues(
    source: ReportWritingInput, draft: FreeformMeetingReports
) -> list[dict[str, Any]]:
    """저장·렌더링에 필요한 선택 딜 1:1 대응과 새 보고서 제목만 검사한다."""
    issues = [
        issue
        for issue in structural_issues(source, draft)
        if issue["code"] == "report_selected_deals_mismatch"
    ]
    for index, report in enumerate(draft.deal_reports):
        if report.title is not None:
            continue
        issues.append(
            {
                "code": "report_deal_title_missing",
                "path": f"deal_reports[{index}].title",
                "sales_deal_id": str(report.sales_deal_id),
                "missing_ids": [],
                "unexpected_ids": [],
            }
        )
    return issues
