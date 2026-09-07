"""미팅 생성은 AgentRun 초안만 만들고 canonical 저장을 건드리지 않는다."""

import asyncio
import copy
from uuid import uuid4

import pytest
from test_agent_runs import _member
from test_report_writing_deep import draft, sample

from app.agents import meeting_analysis, meeting_content_analysis, report_writing_deep
from app.services import meeting_processing as service
from app.services.llm import LLMError


def _snapshot():
    source = sample()
    return source, {
        "source": {
            "transcript": source.transcript,
            "selected_deal_ids": [str(value) for value in source.evidence.selected_deal_ids],
            "segments": [item.segment.model_dump(mode="json") for item in source.evidence.items],
        },
        "deals": [
            {"sales_deal_id": str(value), "deal_no": str(index), "title": f"딜{index}"}
            for index, value in enumerate(source.evidence.selected_deal_ids)
        ],
        "crm_context": source.crm_context,
        "activity_id": str(uuid4()),
    }


def test_input_snapshot_freezes_request_without_a_report(monkeypatch):
    member = _member()
    activity_id = uuid4()
    deal_ids = [uuid4(), uuid4()]
    calls = []

    async def context(db, owner, source_activity_id, selected):
        calls.append((db, owner, source_activity_id, selected))
        return {
            "deals": [
                {"sales_deal_id": str(value), "deal_no": str(index), "title": f"딜{index}"}
                for index, value in enumerate(deal_ids)
            ],
            "crm_context": {"company": {"name": "합성 고객사"}},
        }

    monkeypatch.setattr(service.meeting_context, "build_context", context)
    actual = asyncio.run(
        service.input_snapshot(None, member, activity_id, deal_ids, "고객이 예산을 검토합니다.")
    )

    assert calls == [(None, member, activity_id, deal_ids)]
    assert actual["activity_id"] == str(activity_id)
    assert actual["source"]["selected_deal_ids"] == [str(value) for value in deal_ids]
    assert actual["crm_context"]["company"]["name"] == "합성 고객사"
    assert "report_versions" not in actual
    assert "assignment_overrides" not in actual


def test_no_deal_input_and_processing_keep_the_shared_report(monkeypatch):
    member = _member()
    activity_id = uuid4()
    transcript = "고객사가 신규 사업 방향을 공유했습니다."

    async def context(db, owner, source_activity_id, selected):
        assert (db, owner, source_activity_id, selected) == (
            None,
            member,
            activity_id,
            [],
        )
        return {
            "deals": [],
            "crm_context": {"company": {"name": "합성 고객사"}},
        }

    monkeypatch.setattr(service.meeting_context, "build_context", context)
    snapshot = asyncio.run(service.input_snapshot(None, member, activity_id, [], transcript))
    source = meeting_content_analysis.MeetingContentInput.model_validate(snapshot["source"])
    evidence = meeting_content_analysis.build_evidence_ledger(
        source,
        meeting_content_analysis.MeetingContentAnalysisOutput.model_validate(
            {
                "assignments": [
                    {
                        "segment_id": "S0001",
                        "applicability": {"scope": "company_context"},
                    }
                ]
            }
        ),
    )
    reports = report_writing_deep.FreeformMeetingReports(
        deal_reports=[],
        common_report=report_writing_deep.ReportBody(
            body="고객사가 신규 사업 방향을 공유했습니다.",
            evidence_ids=["S0001"],
        ),
    )

    async def analyze(value, *, on_lookup):
        assert value["deals"] == []
        return evidence

    async def write(value):
        assert value.evidence.selected_deal_ids == []
        return reports

    monkeypatch.setattr(meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(report_writing_deep, "run", write)

    actual = asyncio.run(service.run(snapshot))

    assert snapshot["source"]["selected_deal_ids"] == []
    assert actual.analyses == []
    assert actual.reports == reports
    assert actual.reports.deal_reports == []
    assert actual.evidence.selected_deal_ids == []


@pytest.mark.parametrize("report_failure", [False, True])
def test_run_shares_evidence_and_keeps_partial_results(monkeypatch, report_failure):
    source, snapshot = _snapshot()
    snapshot["crm_context"]["refinement_context"] = {"private_batch": ["tool-only"]}
    reports = report_writing_deep.FreeformMeetingReports.model_validate(draft())
    analyses = [
        meeting_analysis.DealFeatureResult(
            sales_deal_id=deal_id,
            error="deal_prediction_failed",
        )
        for deal_id in source.evidence.selected_deal_ids
    ]
    seen = []

    async def analyze(value, *, on_lookup):
        assert value["crm_context"]["refinement_context"] == {"private_batch": ["tool-only"]}
        lookup = {"kind": "trade_history", "data": {"items": []}}
        on_lookup(copy.deepcopy(lookup))
        on_lookup(copy.deepcopy(lookup))
        seen.append("content")
        return source.evidence

    async def write(value):
        assert value.evidence == source.evidence
        assert "refinement_context" not in value.crm_context
        seen.append("report")
        if report_failure:
            raise LLMError("report_agent_timeout")
        return reports

    async def features(evidence, crm, *, timeout):
        assert evidence == source.evidence
        assert "refinement_context" not in crm
        seen.append("features")
        return analyses

    monkeypatch.setattr(meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(report_writing_deep, "run", write)
    monkeypatch.setattr(meeting_analysis, "run_for_deals", features)

    actual = asyncio.run(service.run(snapshot))

    assert set(seen) == {"content", "report", "features"}
    assert actual.analyses == analyses
    assert (actual.reports is None) is report_failure
    assert bool(actual.errors) is report_failure
    assert actual.context_lookups == [{"kind": "trade_history", "data": {"items": []}}]


def test_transient_report_failure_is_not_downgraded_to_partial(monkeypatch):
    source, snapshot = _snapshot()

    async def analyze(value, *, on_lookup):
        return source.evidence

    async def write(value):
        raise LLMError("llm_provider_error:503")

    async def features(evidence, crm, *, timeout):
        return []

    monkeypatch.setattr(meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(report_writing_deep, "run", write)
    monkeypatch.setattr(meeting_analysis, "run_for_deals", features)

    with pytest.raises(LLMError, match="^llm_provider_error:503$"):
        asyncio.run(service.run(snapshot))


def test_canonical_apply_and_manual_reassignment_are_gone():
    assert not hasattr(service, "apply_output")
    assert not hasattr(service, "apply")
    assert not hasattr(service, "update_notes")
