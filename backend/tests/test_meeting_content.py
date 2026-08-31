from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    MeetingContentInput,
    SegmentApplicability,
    SegmentAssignment,
    SourceSegment,
    build_evidence_ledger,
)


def _segment(transcript: str, text: str, number: int) -> SourceSegment:
    start = transcript.index(text)
    return SourceSegment(
        segment_id=f"S{number:04d}",
        start=start,
        end=start + len(text),
        text=text,
    )


def _source(deal_ids: list[UUID]) -> MeetingContentInput:
    transcript = "참석자를 소개했다.\n딜 A의 예산이 승인됐다.\n어느 딜인지 불명확하다."
    return MeetingContentInput(
        transcript=transcript,
        selected_deal_ids=deal_ids,
        segments=[
            _segment(transcript, "참석자를 소개했다.", 1),
            _segment(transcript, "딜 A의 예산이 승인됐다.", 2),
            _segment(transcript, "어느 딜인지 불명확하다.", 3),
        ],
    )


def test_build_evidence_ledger_keeps_exact_source_and_deal_scope():
    deal_a, deal_b = uuid4(), uuid4()
    source = _source([deal_a, deal_b])
    analysis = MeetingContentAnalysisOutput(
        assignments=[
            SegmentAssignment(
                segment_id="S0001",
                applicability=SegmentApplicability(scope="meeting_context"),
            ),
            SegmentAssignment(
                segment_id="S0002",
                applicability=SegmentApplicability(scope="deal", deal_ids=[deal_a]),
            ),
            SegmentAssignment(
                segment_id="S0003",
                applicability=SegmentApplicability(scope="unresolved"),
            ),
        ]
    )

    ledger = build_evidence_ledger(source, analysis)

    assert ledger.schema_version == "meeting_content.v1"
    assert len(ledger.transcript_sha256) == 64
    assert ledger.items[1].segment.text == "딜 A의 예산이 승인됐다."
    assert ledger.items[1].applicability.deal_ids == [deal_a]
    assert ledger.items[2].applicability.scope == "unresolved"


def test_source_rejects_segments_that_do_not_match_the_transcript():
    deal_id = uuid4()
    transcript = "실제 원문"

    with pytest.raises(ValidationError, match="source_segment_text_mismatch"):
        MeetingContentInput(
            transcript=transcript,
            selected_deal_ids=[deal_id],
            segments=[SourceSegment(segment_id="S0001", start=0, end=2, text="다른")],
        )


def test_source_allows_whitespace_gaps_but_not_unassigned_content():
    deal_id = uuid4()
    transcript = "첫 문장.\n둘째 문장."

    source = MeetingContentInput(
        transcript=transcript,
        selected_deal_ids=[deal_id],
        segments=[
            _segment(transcript, "첫 문장.", 1),
            _segment(transcript, "둘째 문장.", 2),
        ],
    )
    assert len(source.segments) == 2

    with pytest.raises(ValidationError, match="source_segment_gap"):
        MeetingContentInput(
            transcript=transcript,
            selected_deal_ids=[deal_id],
            segments=[_segment(transcript, "첫 문장.", 1)],
        )


def test_assignment_requires_deals_only_for_deal_scope():
    deal_id = uuid4()

    with pytest.raises(ValidationError, match="assignment_deal_id_required"):
        SegmentApplicability(scope="deal")
    with pytest.raises(ValidationError, match="assignment_deal_id_not_allowed"):
        SegmentApplicability(scope="unresolved", deal_ids=[deal_id])


def test_ledger_requires_every_source_segment_exactly_once():
    deal_id = uuid4()
    source = _source([deal_id])
    analysis = MeetingContentAnalysisOutput(
        assignments=[
            SegmentAssignment(
                segment_id="S0001",
                applicability=SegmentApplicability(scope="meeting_context"),
            )
        ]
    )

    with pytest.raises(ValueError, match="assignment_segments_mismatch"):
        build_evidence_ledger(source, analysis)


def test_ledger_rejects_a_deal_outside_the_selected_set():
    selected_deal_id = uuid4()
    other_deal_id = uuid4()
    source = MeetingContentInput(
        transcript="딜에 대한 요청이다.",
        selected_deal_ids=[selected_deal_id],
        segments=[SourceSegment(segment_id="S0001", start=0, end=11, text="딜에 대한 요청이다.")],
    )
    analysis = MeetingContentAnalysisOutput(
        assignments=[
            SegmentAssignment(
                segment_id="S0001",
                applicability=SegmentApplicability(scope="deal", deal_ids=[other_deal_id]),
            )
        ]
    )

    with pytest.raises(ValueError, match="assignment_deal_not_selected"):
        build_evidence_ledger(source, analysis)
