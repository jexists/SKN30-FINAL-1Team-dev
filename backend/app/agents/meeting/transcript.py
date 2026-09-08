"""원문 위치를 보존하는 구간 분할과 내용분석 입력 계약."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.meeting_content import MeetingContentInput, SourceSegment

_SENTENCE_ENDINGS = frozenset(".!?。！？")
_CLOSING_MARKS = frozenset("\"'”’)]}")


class DealGroundingContext(BaseModel):
    """원문의 제품명·딜명을 실제 선택 딜과 연결하기 위한 최소 CRM 정보."""

    model_config = ConfigDict(extra="forbid")

    sales_deal_id: UUID
    deal_no: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5_000)
    product_names: list[str] = Field(default_factory=list, max_length=100)
    deal_type_name: str | None = Field(default=None, max_length=200)
    pipeline_stage_name: str | None = Field(default=None, max_length=200)


class MeetingContentAgentInput(BaseModel):
    """내용 분석 에이전트의 실행 시점 입력."""

    model_config = ConfigDict(extra="forbid")

    source: MeetingContentInput
    deals: list[DealGroundingContext] = Field(max_length=100)
    crm_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_deals(self):
        deal_ids = [deal.sales_deal_id for deal in self.deals]
        if len(deal_ids) != len(set(deal_ids)):
            raise ValueError("grounding_deal_duplicate")
        if set(deal_ids) != set(self.source.selected_deal_ids):
            raise ValueError("grounding_deals_mismatch")
        return self


def _append_segment(segments: list[SourceSegment], transcript: str, start: int, end: int) -> None:
    """공백이 아닌 원문 구간 하나를 원래 위치 그대로 추가한다."""
    while end > start and transcript[end - 1].isspace():
        end -= 1
    if end <= start:
        return
    segments.append(
        SourceSegment(
            segment_id=f"S{len(segments) + 1:04d}",
            start=start,
            end=end,
            text=transcript[start:end],
        )
    )


def segment_transcript(value: object) -> list[SourceSegment]:
    """줄바꿈과 문장 종결부호를 기준으로 원문 위치를 보존해 나눈다."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("transcript_required")
    if len(value) > 50_000:
        raise ValueError("transcript_too_long")

    segments: list[SourceSegment] = []
    start: int | None = None
    index = 0
    while index < len(value):
        char = value[index]
        if start is None:
            if not char.isspace():
                start = index
            index += 1
            continue

        if char in "\r\n":
            _append_segment(segments, value, start, index)
            start = None
            index += 1
            continue

        if char in _SENTENCE_ENDINGS:
            end = index + 1
            while end < len(value) and value[end] in _CLOSING_MARKS:
                end += 1
            if end == len(value) or value[end].isspace():
                _append_segment(segments, value, start, end)
                start = None
                index = end
                continue
        index += 1

    if start is not None:
        _append_segment(segments, value, start, len(value))
    return segments


def input_snapshot(
    transcript: str,
    deals: list[DealGroundingContext | dict[str, Any]],
    *,
    crm_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """원문을 나누고 선택 딜 컨텍스트와 함께 실행 입력을 고정한다."""
    contexts = [DealGroundingContext.model_validate(deal) for deal in deals]
    source = MeetingContentInput(
        transcript=transcript,
        selected_deal_ids=[deal.sales_deal_id for deal in contexts],
        segments=segment_transcript(transcript),
    )
    return MeetingContentAgentInput(
        source=source, deals=contexts, crm_context=crm_context or {}
    ).model_dump(mode="json")


def basic_crm(agent_input: MeetingContentAgentInput) -> dict[str, Any]:
    return {
        key: agent_input.crm_context[key]
        for key in ("activity", "company", "contact", "snapshot_at", "crm_time_basis")
        if key in agent_input.crm_context
    }
