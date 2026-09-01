"""미팅 원문을 딜별 근거로 나누기 위한 공통 데이터 계약."""

import hashlib
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SegmentId = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^S\d{4,6}$"),
]
SegmentScope = Literal[
    "meeting_context",
    "company_context",
    "all_selected_deals",
    "deal",
    "unresolved",
    "out_of_scope",
]


class SourceSegment(BaseModel):
    """서버가 원문에서 잘라 낸 변경 불가능한 근거 구간."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    segment_id: SegmentId
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(strict=True, min_length=1, max_length=50_000)

    @model_validator(mode="after")
    def _check_range(self):
        if self.end <= self.start:
            raise ValueError("segment_range_invalid")
        return self


class SegmentApplicability(BaseModel):
    """원문 구간이 적용되는 미팅 또는 딜 범위."""

    model_config = ConfigDict(extra="forbid")

    scope: SegmentScope
    deal_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _check_deal_ids(self):
        if len(self.deal_ids) != len(set(self.deal_ids)):
            raise ValueError("assignment_deal_id_duplicate")
        if self.scope == "deal" and not self.deal_ids:
            raise ValueError("assignment_deal_id_required")
        if self.scope != "deal" and self.deal_ids:
            raise ValueError("assignment_deal_id_not_allowed")
        return self


class SegmentAssignment(BaseModel):
    """내용 분석 에이전트가 반환하는 원문 구간 하나의 귀속."""

    model_config = ConfigDict(extra="forbid")

    segment_id: SegmentId
    applicability: SegmentApplicability


class MeetingContentAnalysisOutput(BaseModel):
    """LLM 구조화 출력. 원문을 복사하지 않고 서버가 만든 ID만 분류한다."""

    model_config = ConfigDict(extra="forbid")

    assignments: list[SegmentAssignment] = Field(min_length=1, max_length=5_000)

    @model_validator(mode="after")
    def _check_unique_segments(self):
        segment_ids = [item.segment_id for item in self.assignments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("assignment_segment_duplicate")
        return self


class MeetingContentInput(BaseModel):
    """원문과 서버가 만든 구간, 이번 미팅에서 선택한 딜 목록."""

    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(strict=True, min_length=1, max_length=50_000)
    selected_deal_ids: list[UUID] = Field(min_length=1, max_length=100)
    segments: list[SourceSegment] = Field(min_length=1, max_length=5_000)

    @model_validator(mode="after")
    def _check_source(self):
        if not self.transcript.strip():
            raise ValueError("transcript_required")
        if len(self.selected_deal_ids) != len(set(self.selected_deal_ids)):
            raise ValueError("selected_deal_id_duplicate")

        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("source_segment_duplicate")

        previous_end = 0
        for segment in self.segments:
            if segment.start < previous_end:
                raise ValueError("source_segment_order_invalid")
            if self.transcript[previous_end : segment.start].strip():
                raise ValueError("source_segment_gap")
            if segment.end > len(self.transcript):
                raise ValueError("source_segment_out_of_bounds")
            if self.transcript[segment.start : segment.end] != segment.text:
                raise ValueError("source_segment_text_mismatch")
            previous_end = segment.end
        if self.transcript[previous_end:].strip():
            raise ValueError("source_segment_gap")
        return self


class MeetingEvidenceItem(BaseModel):
    """검증된 원문 구간과 적용 범위를 합친 후속 작업용 근거."""

    model_config = ConfigDict(extra="forbid")

    segment: SourceSegment
    applicability: SegmentApplicability


class MeetingEvidenceLedger(BaseModel):
    """특성 생성기와 보고서 에이전트가 함께 사용하는 미팅 근거 장부."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["meeting_content.v1"] = "meeting_content.v1"
    transcript_sha256: Annotated[
        str,
        StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
    ]
    selected_deal_ids: list[UUID] = Field(min_length=1, max_length=100)
    items: list[MeetingEvidenceItem] = Field(min_length=1, max_length=5_000)

    @model_validator(mode="after")
    def _check_ledger(self):
        selected = set(self.selected_deal_ids)
        if len(selected) != len(self.selected_deal_ids):
            raise ValueError("selected_deal_id_duplicate")

        segment_ids = [item.segment.segment_id for item in self.items]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("evidence_segment_duplicate")
        if any(not set(item.applicability.deal_ids) <= selected for item in self.items):
            raise ValueError("assignment_deal_not_selected")
        return self


def build_evidence_ledger(
    source: MeetingContentInput,
    analysis: MeetingContentAnalysisOutput,
) -> MeetingEvidenceLedger:
    """원문 전체가 정확히 한 번 귀속됐는지 확인하고 근거 장부를 만든다."""
    source_ids = {segment.segment_id for segment in source.segments}
    assignments = {item.segment_id: item.applicability for item in analysis.assignments}
    if source_ids != assignments.keys():
        raise ValueError("assignment_segments_mismatch")

    selected = set(source.selected_deal_ids)
    if any(not set(item.deal_ids) <= selected for item in assignments.values()):
        raise ValueError("assignment_deal_not_selected")

    return MeetingEvidenceLedger(
        transcript_sha256=hashlib.sha256(source.transcript.encode("utf-8")).hexdigest(),
        selected_deal_ids=source.selected_deal_ids,
        items=[
            MeetingEvidenceItem(
                segment=segment,
                applicability=assignments[segment.segment_id],
            )
            for segment in source.segments
        ],
    )
