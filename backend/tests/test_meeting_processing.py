"""합성 입력/모의 DB로 공통 실행과 저장 경계를 검사한다. 골든셋 품질 평가는 아니다."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_agent_runs import NOW, _Db, _member, _report, _Result, _run, _SessionContext
from test_report_writing_deep import draft, sample

from app.agents import meeting_analysis, meeting_content_analysis, report_writing_deep
from app.api import reports as reports_api
from app.models.content import MeetingDealAnalysis, ReportDeal
from app.schemas.agent_runs import AgentRunCreate
from app.schemas.meeting_content import SegmentAssignment
from app.services import agent_runs
from app.services import meeting_processing as service
from app.services.agent_logging import log_agent_event
from app.services.llm import LLMError


def test_processing_version_tracks_executive_report_contract():
    assert service.PROMPT_VERSION == "meeting_processing.v10"
    assert meeting_content_analysis.PROMPT_VERSION == "meeting_content_analysis.v5"
    assert report_writing_deep.PROMPT_VERSION == "report_writing.deep.v8"


def case():
    source = sample()
    member = _member()
    activity_id = uuid4()
    report = _report(member, transcript=source.transcript)
    report.report_kind = "meeting"
    report.source_activity_id = activity_id
    report.sales_deal_id = None
    report.template_snapshot = {"fields": [{"id": "body", "label": "본문"}]}
    report.title = "합성 미팅"
    report.content = {"title": "합성 미팅", "attachments": []}
    sections = []
    for deal_id in source.evidence.selected_deal_ids:
        sections.append(
            ReportDeal(
                report_id=report.id,
                sales_deal_id=deal_id,
                deal_snapshot={"id": str(deal_id), "label": "합성 딜"},
                content={"title": "합성 미팅", "values": {"body": ""}},
                title="합성 미팅",
                ai_evidence=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    snapshot = {
        "source": {
            "transcript": source.transcript,
            "selected_deal_ids": [str(value) for value in source.evidence.selected_deal_ids],
            "segments": [item.segment.model_dump(mode="json") for item in source.evidence.items],
        },
        "deals": [
            {"sales_deal_id": str(section.sales_deal_id), "deal_no": str(i), "title": f"딜{i}"}
            for i, section in enumerate(sections)
        ],
        "crm_context": source.crm_context,
        "activity_id": str(activity_id),
        "team_id": str(member.team_id),
        "assignment_overrides": [],
        "report_versions": [{"id": str(report.id), "updated_at": report.updated_at.isoformat()}],
        "deal_versions": [
            {
                "sales_deal_id": str(section.sales_deal_id),
                "updated_at": section.updated_at.isoformat(),
            }
            for section in sections
        ],
    }
    result = service.MeetingProcessingOutput(
        reports=report_writing_deep.FreeformMeetingReports.model_validate(draft()),
        analyses=[
            meeting_analysis.DealFeatureResult(
                sales_deal_id=section.sales_deal_id, error="deal_prediction_failed"
            )
            for section in sections
        ],
        evidence=source.evidence,
        errors={},
    )
    run = _run(member, status_code="completed")
    run.agent_code = "meeting_processing"
    run.prompt_version = service.PROMPT_VERSION
    run.input_snapshot = snapshot
    run.output_snapshot = result.model_dump(mode="json")
    run.test_report = report
    return member, sections, run, result


def test_new_run_contract_requires_unique_reports_and_versioned_overrides():
    base = {"agent_code": "meeting_processing", "idempotency_key": uuid4()}
    good = AgentRunCreate(**base, report_id=uuid4())
    assert good.report_id is not None
    for values in (
        {},
        {"report_ids": []},
        {"report_ids": [UUID(int=1)] * 2},
        {"report_ids": [uuid4(), uuid4()]},
        {"report_id": uuid4(), "parent_run_id": uuid4()},
    ):
        with pytest.raises(ValidationError):
            AgentRunCreate(**base, **values)
    override = {"segment_id": "S0003", "applicability": {"scope": "deal", "deal_ids": [uuid4()]}}
    with pytest.raises(ValidationError):
        AgentRunCreate(**base, report_id=uuid4(), assignment_overrides=[override])


def test_snapshot_builds_crm_once_and_checks_group_and_manual_assignment(monkeypatch):
    member, sections, parent, result = case()
    calls = []
    parent.input_snapshot["deals"][0]["title"] = "부모 실행 딜"
    parent.input_snapshot["crm_context"] = {
        "snapshot_at": "2026-08-20T09:00:00+00:00",
        "company": {"name": "부모 실행 회사"},
    }
    parent_lookup = {
        "kind": "product_details",
        "sales_deal_id": str(sections[0].sales_deal_id),
        "data": {"items": [{"name": "부모 실행 상품"}]},
    }
    parent.output_snapshot["context_lookups"] = [parent_lookup]
    current_deals = copy.deepcopy(parent.input_snapshot["deals"])
    current_deals[0]["title"] = "현재 CRM 딜"

    async def context(db, owner, activity_id, selected):
        calls.append(selected)
        return {
            "deals": copy.deepcopy(current_deals),
            "crm_context": {
                "snapshot_at": "2026-09-01T09:00:00+00:00",
                "company": {"name": "현재 CRM 회사"},
            },
        }

    monkeypatch.setattr(service.meeting_context, "build_context", context)
    monkeypatch.setattr(service, "_report_deals", AsyncMock(return_value=sections))
    snapshot = asyncio.run(service.input_snapshot(None, member, parent.test_report))
    assert len(calls) == 1 and len(snapshot["source"]["selected_deal_ids"]) == 2
    assert snapshot["deals"][0]["title"] == "현재 CRM 딜"
    assert snapshot["crm_context"]["company"]["name"] == "현재 CRM 회사"
    parent.test_report.source_snapshot = {"meeting_run_id": str(parent.id)}
    override = SegmentAssignment.model_validate(
        {
            "segment_id": "S0003",
            "applicability": {"scope": "deal", "deal_ids": [sections[1].sales_deal_id]},
        }
    )
    updated = asyncio.run(
        service.input_snapshot(None, member, parent.test_report, parent, [override])
    )
    assert len(calls) == 2  # 현재 권한·연결 검사는 재수행한다.
    assert updated["deals"] == parent.input_snapshot["deals"]
    assert updated["crm_context"] == parent.input_snapshot["crm_context"]
    assert updated["parent_context_lookups"] == [parent_lookup]
    assert updated["parent_evidence"] == result.evidence.model_dump(mode="json")
    updated["deals"][0]["title"] = "자식 변경"
    updated["crm_context"]["company"]["name"] = "자식 변경"
    updated["parent_context_lookups"][0]["data"]["items"][0]["name"] = "자식 변경"
    assert parent.input_snapshot["deals"][0]["title"] == "부모 실행 딜"
    assert parent.input_snapshot["crm_context"]["company"]["name"] == "부모 실행 회사"
    assert parent.output_snapshot["context_lookups"] == [parent_lookup]
    parent.test_report.source_snapshot = {"meeting_run_id": str(uuid4())}
    with pytest.raises(HTTPException, match="meeting_assignment_stale"):
        asyncio.run(service.input_snapshot(None, member, parent.test_report, parent, [override]))
    parent.test_report.source_snapshot = {"meeting_run_id": str(parent.id)}
    override.segment_id = "S0002"
    with pytest.raises(HTTPException, match="meeting_assignment_not_unresolved"):
        asyncio.run(service.input_snapshot(None, member, parent.test_report, parent, [override]))
    parent.test_report.report_kind = "daily"
    with pytest.raises(HTTPException, match="meeting_reports_mismatch"):
        asyncio.run(service.input_snapshot(None, member, parent.test_report))


@pytest.mark.parametrize("report_failure", [False, True])
def test_workflow_shares_one_analysis_and_keeps_partial_results(monkeypatch, report_failure):
    member, _, run, expected = case()
    run.input_snapshot["crm_context"]["refinement_context"] = {"private_batch": ["tool-only"]}
    seen = []

    async def analyze(snapshot, *, on_lookup):
        assert snapshot["crm_context"]["refinement_context"] == {"private_batch": ["tool-only"]}
        seen.append("content")
        return expected.evidence

    async def write(source):
        assert source.evidence == expected.evidence
        assert "refinement_context" not in source.crm_context
        seen.append("report")
        if report_failure:
            raise LLMError("report_agent_timeout")
        return expected.reports

    async def features(evidence, crm, *, timeout=None):
        assert evidence == expected.evidence
        assert "refinement_context" not in crm
        seen.append("features")
        return expected.analyses

    monkeypatch.setattr(service.meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(service.meeting_analysis, "run_for_deals", features)
    actual = asyncio.run(service.run(run.input_snapshot, member.id))
    assert seen.count("content") == 1 and set(seen) == {"content", "report", "features"}
    assert actual.analyses == expected.analyses
    assert (actual.reports is None) is report_failure
    assert bool(actual.errors) is report_failure


@pytest.mark.parametrize("request_history", [False, True])
def test_previous_reports_are_writer_context_and_grounding_looks_up_only_when_needed(
    monkeypatch, request_history
):
    member, reports, run, expected = case()
    histories = [
        {
            "kind": "previous_reports",
            "sales_deal_id": str(report.sales_deal_id),
            "items": [{"report_id": str(uuid4()), "values": {"body": "이전 미팅 전용 내용"}}]
            if index == 0
            else [],
        }
        for index, report in enumerate(reports)
    ]
    run.input_snapshot["crm_context"]["previous_reports"] = copy.deepcopy(histories)

    async def analyze(snapshot, *, on_lookup):
        agent_input = meeting_content_analysis.MeetingContentAgentInput.model_validate(snapshot)
        prompt = meeting_content_analysis._prompt_input(agent_input)
        assert "이전 미팅 전용 내용" not in prompt
        assert "previous_reports" not in prompt
        if request_history:
            for report, history in zip(reports, histories, strict=True):
                on_lookup(
                    {
                        "kind": "previous_reports",
                        "sales_deal_id": str(report.sales_deal_id),
                        "data": copy.deepcopy(history),
                    }
                )
        return expected.evidence

    async def write(source):
        assert source.crm_context["previous_reports"] == histories
        return expected.reports

    async def features(evidence, crm, *, timeout):
        for report in reports:
            filtered = meeting_analysis._deal_crm_context(crm, report.sales_deal_id)
            assert "previous_reports" not in filtered
            if not request_history:
                assert filtered["additional_context"] == []
        return expected.analyses

    monkeypatch.setattr(service.meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(service.meeting_analysis, "run_for_deals", features)

    actual = asyncio.run(service.run(run.input_snapshot, member.id))

    assert actual.reports == expected.reports
    assert run.input_snapshot["crm_context"]["previous_reports"] == histories
    assert len(actual.context_lookups) == (2 if request_history else 0)


def test_company_trade_history_is_recorded_once_and_promoted_without_duplicate_context(
    monkeypatch,
):
    member, _, run, expected = case()
    history = {
        "kind": "trade_history",
        "items": [{"sales_deal_id": str(uuid4()), "title": "이전 확정 거래"}],
        "limit": 50,
        "truncated": False,
    }

    async def analyze(snapshot, *, on_lookup):
        value = {"kind": "trade_history", "data": copy.deepcopy(history)}
        on_lookup(value)
        on_lookup(value)
        return expected.evidence

    async def write(source):
        assert source.crm_context["trade_history"] == history["items"]
        assert all(
            item.get("kind") != "trade_history" for item in source.crm_context["additional_context"]
        )
        return expected.reports

    async def features(evidence, crm, *, timeout):
        assert crm["trade_history"] == history["items"]
        return expected.analyses

    monkeypatch.setattr(service.meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(service.meeting_analysis, "run_for_deals", features)

    actual = asyncio.run(service.run(run.input_snapshot, member.id))

    assert actual.context_lookups == [{"kind": "trade_history", "data": history}]


def test_manual_reassignment_keeps_other_segments_without_another_classification(monkeypatch):
    member, reports, run, expected = case()
    run.input_snapshot["parent_evidence"] = expected.evidence.model_dump(mode="json")
    run.input_snapshot["assignment_overrides"] = [
        {
            "segment_id": "S0003",
            "applicability": {"scope": "deal", "deal_ids": [str(reports[1].sales_deal_id)]},
        }
    ]

    async def not_called(*args, **kwargs):
        pytest.fail("사람 재배정을 다시 LLM으로 분류하면 안 된다")

    async def write(source):
        return None

    async def features(evidence, crm, *, timeout=None):
        return expected.analyses

    monkeypatch.setattr(service.meeting_content_analysis, "run", not_called)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(service.meeting_analysis, "run_for_deals", features)
    actual = asyncio.run(service.run(run.input_snapshot, member.id))
    assert actual.evidence.items[2].applicability.deal_ids == [reports[1].sales_deal_id]
    assert actual.evidence.items[:2] == expected.evidence.items[:2]
    assert actual.evidence.items[3] == expected.evidence.items[3]


def storage(monkeypatch, *, report_failure=False):
    member, sections, run, output = case()
    if report_failure:
        output.reports = None
        output.errors = {"report_writing": "report_agent_failed"}
        run.output_snapshot = output.model_dump(mode="json")
    db = _Db()

    async def locked_run(*args):
        return run

    async def locked_report_and_deals(*args):
        return run.test_report, sections

    async def commit(db, member, report):
        await db.commit()
        return report

    monkeypatch.setattr(service, "_locked_run", locked_run)
    monkeypatch.setattr(service, "_locked_report_and_deals", locked_report_and_deals)
    monkeypatch.setattr(service, "_commit_report", commit)
    return member, sections, run, db


def test_apply_is_atomic_idempotent_and_does_not_overwrite_human_text(monkeypatch):
    member, sections, run, db = storage(monkeypatch)
    sections[1].content["values"]["body"] = "사람이 쓴 보고서"
    sections[1].title = "사람이 정한 제목"
    sections[1].content["title"] = "사람이 정한 제목"
    asyncio.run(service.apply(db, member, run.id))
    assert "보안 승인" in sections[0].content["values"]["body"]
    assert sections[0].title == "보안 승인 후 예산 검토"
    assert sections[0].content["title"] == sections[0].title
    assert sections[1].content["values"]["body"] == "사람이 쓴 보고서"
    assert sections[1].title == sections[1].content["title"] == "사람이 정한 제목"
    assert sections[1].content["ai_values"]["body"] != "사람이 쓴 보고서"
    shared = run.test_report.content["meeting_shared"]
    assert shared["common_report"]["body"] == "구매팀과 미팅을 진행했다."
    for section in sections:
        assert "meeting_shared" not in section.content
        assert "구매팀과 미팅을 진행했다." not in section.content["values"]["body"]
    assert "그거 다시 보내달래" in shared["unassigned_report"]["body"]
    assert sections[0].ai_evidence["analysis_error"] == "deal_prediction_failed"
    assert run.test_report.source_snapshot["evidence"]["transcript_sha256"]
    assert run.test_report.status_code == "draft"
    sections[0].content["values"]["body"] = "저장 후 다시 편집"
    asyncio.run(service.apply(db, member, run.id))
    assert sections[0].content["values"]["body"] == "저장 후 다시 편집"


def test_apply_updates_previous_ai_title_but_preserves_later_human_title(monkeypatch):
    member, sections, run, db = storage(monkeypatch)
    asyncio.run(service.apply(db, member, run.id))
    previous = service.MeetingProcessingOutput.model_validate(run.output_snapshot)
    monkeypatch.setattr(service, "_previous_result", AsyncMock(return_value=previous))
    sections[1].title = "사람 수정 제목"
    sections[1].content["title"] = sections[1].title
    result = service.MeetingProcessingOutput.model_validate(run.output_snapshot)
    result.reports.deal_reports[0].title = "예산 검토 후속 미팅"
    result.reports.deal_reports[1].title = report_writing_deep.NO_DEAL_EVIDENCE_TEXT
    run.output_snapshot = result.model_dump(mode="json")
    run.id = uuid4()
    run.input_snapshot["report_versions"][0]["updated_at"] = run.test_report.updated_at.isoformat()
    for version, section in zip(run.input_snapshot["deal_versions"], sections, strict=True):
        version["updated_at"] = section.updated_at.isoformat()

    asyncio.run(service.apply(db, member, run.id))

    assert sections[0].title == sections[0].content["title"] == "예산 검토 후속 미팅"
    assert sections[1].title == sections[1].content["title"] == "사람 수정 제목"


def test_legacy_output_without_titles_deserializes_and_keeps_existing_titles(monkeypatch):
    member, sections, run, db = storage(monkeypatch)
    run.prompt_version = "meeting_processing.v6"
    for item in run.output_snapshot["reports"]["deal_reports"]:
        item.pop("title")
    run.output_snapshot["reports"]["deal_reports"][1]["body"] = (
        "이번 미팅에서 B의 구체적인 논의는 확인되지 않았다."
    )

    restored = service.MeetingProcessingOutput.model_validate(run.output_snapshot)
    assert all(item.title is None for item in restored.reports.deal_reports)
    asyncio.run(service.apply(db, member, run.id))

    assert [section.title for section in sections] == ["합성 미팅", "합성 미팅"]
    assert all(section.content["title"] == "합성 미팅" for section in sections)


def test_apply_preserves_all_unknown_features_without_prediction(monkeypatch):
    member, sections, run, db = storage(monkeypatch)
    unknown = {name: "Unknown" for name in meeting_analysis.deal_baseline.FEATURE_NAMES}
    output = service.MeetingProcessingOutput.model_validate(run.output_snapshot)
    output.reports = None
    output.analyses = [
        meeting_analysis.DealFeatureResult(
            sales_deal_id=section.sales_deal_id,
            features=unknown,
            error="deal_prediction_insufficient_features",
        )
        for section in sections
    ]
    run.output_snapshot = output.model_dump(mode="json")

    asyncio.run(service.apply(db, member, run.id))

    history = [item for item in db.added if isinstance(item, MeetingDealAnalysis)]
    assert len(history) == len(sections)
    for section, item in zip(sections, history, strict=True):
        assert section.ai_evidence["features"] == unknown
        assert section.ai_evidence["deal_assessment"] is None
        assert section.ai_evidence["analysis_error"] == "deal_prediction_insufficient_features"
        assert item.features == unknown
        assert item.prediction_label is None and item.probability is None
        assert item.model_version is None
        assert item.error_code == "deal_prediction_insufficient_features"


@pytest.mark.parametrize("malformed_values", [None, [], "잘못된 값"])
def test_apply_replaces_malformed_values_with_generated_mapping(monkeypatch, malformed_values):
    member, sections, run, db = storage(monkeypatch)
    sections[0].content["values"] = malformed_values

    asyncio.run(service.apply(db, member, run.id))

    assert isinstance(sections[0].content["values"], dict)
    assert "보안 승인" in sections[0].content["values"]["body"]


@pytest.mark.parametrize(
    "fields,expected_field",
    [
        ([{"id": "reaction", "type": "textarea"}, {"id": "body"}], "body"),
        (
            [
                {"id": "attendees", "type": "text", "aiFilled": True},
                {"id": "reaction", "type": "textarea", "aiFilled": True},
                {"id": "decision", "type": "textarea", "aiFilled": True},
                {"id": "next", "type": "textarea", "aiFilled": True},
                {"id": "note", "type": "textarea", "aiFilled": False},
            ],
            "reaction",
        ),
        (
            [
                {"id": "summary", "type": "text", "aiFilled": True},
                {"id": "note", "type": "text", "aiFilled": False},
            ],
            "summary",
        ),
        ([{"id": "note", "type": "text", "aiFilled": False}], None),
        ([{"id": "note", "type": "textarea", "aiFilled": False}], None),
        ([], None),
    ],
)
def test_apply_selects_suitable_field_or_keeps_draft_as_suggestion(
    monkeypatch, fields, expected_field
):
    member, sections, run, db = storage(monkeypatch)
    run.test_report.template_snapshot = {"fields": fields}
    for section in sections:
        section.content["values"] = {field["id"]: "" for field in fields}
    sections[1].content["values"] = {"note": "사람이 작성한 내용"}
    original_values = [copy.deepcopy(section.content["values"]) for section in sections]

    asyncio.run(service.apply(db, member, run.id))

    for index, section in enumerate(sections):
        expected_draft = next(
            item
            for item in run.output_snapshot["reports"]["deal_reports"]
            if item["sales_deal_id"] == str(section.sales_deal_id)
        )
        generated = {expected_field or "body": expected_draft["body"]}
        expected_values = original_values[index]
        if expected_field is not None:
            expected_values[expected_field] = expected_draft["body"]
        assert section.content["values"] == expected_values
        assert section.content["ai_values"] == generated
        assert section.content["ai_evidence"] == " · ".join(expected_draft["evidence_ids"])
        assert section.content["ai_generated_at"]
        assert run.test_report.source_snapshot["meeting_run_id"] == str(run.id)
        assert run.test_report.source_snapshot["evidence"] == run.output_snapshot["evidence"]


def test_apply_rejects_concurrent_edits_before_any_report_write(monkeypatch):
    member, sections, run, db = storage(monkeypatch)
    original = copy.deepcopy(sections[0].content)
    sections[1].updated_at = NOW.replace(day=18)
    with pytest.raises(HTTPException, match="meeting_report_changed"):
        asyncio.run(service.apply(db, member, run.id))
    assert sections[0].content == original
    assert db.commit_count == 0 and db.rollback_count == 1


def test_failed_writer_still_saves_unassigned_original_and_analysis_state(monkeypatch):
    member, sections, run, db = storage(monkeypatch, report_failure=True)
    asyncio.run(service.apply(db, member, run.id))
    assert sections[0].content["values"] == {"body": ""}
    shared = run.test_report.content["meeting_shared"]
    assert shared["unassigned_report"]["evidence_ids"] == ["S0003", "S0004"]
    assert "기타 메모 ???" in shared["unassigned_report"]["body"]
    assert sections[0].ai_evidence["report_error"] == "report_agent_failed"


def test_notes_sync_without_changing_original_evidence(monkeypatch):
    member, sections, run, db = storage(monkeypatch)
    asyncio.run(service.apply(db, member, run.id))
    evidence = copy.deepcopy(run.test_report.source_snapshot)
    revision = UUID(run.test_report.content["meeting_shared"]["revision"])
    version = run.test_report.version
    generation_input_version = run.test_report.generation_input_version
    asyncio.run(
        service.update_notes(db, member, run.id, "공통 수정", "미지정 원문 확인 필요", revision)
    )
    assert run.test_report.source_snapshot == evidence
    assert run.test_report.version == version + 1
    assert run.test_report.generation_input_version == generation_input_version
    assert run.test_report.common_body == "공통 수정"
    assert run.test_report.unassigned_body == "미지정 원문 확인 필요"
    with pytest.raises(HTTPException, match="meeting_notes_changed"):
        asyncio.run(
            service.update_notes(db, member, run.id, "오래된 탭 수정", "확인 필요", revision)
        )
    assert run.test_report.content["meeting_shared"]["common_report"]["body"] == "공통 수정"
    revision = UUID(run.test_report.content["meeting_shared"]["revision"])
    run.test_report.source_snapshot = {"meeting_run_id": str(uuid4())}
    with pytest.raises(HTTPException, match="meeting_notes_stale"):
        asyncio.run(service.update_notes(db, member, run.id, "다시 수정", "확인 필요", revision))


def test_regeneration_preserves_edited_shared_notes_as_well_as_deal_bodies(monkeypatch):
    member, sections, run, db = storage(monkeypatch)
    asyncio.run(service.apply(db, member, run.id))
    previous = service.MeetingProcessingOutput.model_validate(run.output_snapshot)
    monkeypatch.setattr(service, "_previous_result", AsyncMock(return_value=previous))
    revision = UUID(run.test_report.content["meeting_shared"]["revision"])
    asyncio.run(
        service.update_notes(db, member, run.id, "사람이 확정한 공통 정정", "미지정 수정", revision)
    )
    run.id = uuid4()
    run.input_snapshot["report_versions"][0]["updated_at"] = run.test_report.updated_at.isoformat()
    for version, section in zip(run.input_snapshot["deal_versions"], sections, strict=True):
        version["updated_at"] = section.updated_at.isoformat()
    asyncio.run(service.apply(db, member, run.id))
    shared = run.test_report.content["meeting_shared"]
    assert shared["common_report"]["body"] == "사람이 확정한 공통 정정"
    assert shared["common_report"]["ai_body"] != shared["common_report"]["body"]
    assert shared["unassigned_report"]["body"] == "미지정 수정"
    assert shared["revision"] != str(revision)


def test_background_dispatch_serializes_uuid_results(monkeypatch):
    member, _, run, output = case()
    run.status_code = "queued"
    run.output_snapshot = None
    run.apply_status = "pending"
    claim = _Db(_Result(scalar=run))
    persist = _Db(_Result(scalar=run))
    apply = _Db(_Result(scalar=run))
    sessions = iter([claim, persist, apply])
    monkeypatch.setattr(
        agent_runs, "get_sessionmaker", lambda: lambda: _SessionContext(next(sessions))
    )

    async def execute(snapshot, member_id):
        assert member_id == member.id
        return output

    async def apply_output(db, current):
        assert db is apply and current is run
        return "applied"

    monkeypatch.setattr(service, "run", execute)
    monkeypatch.setattr(service, "apply_output", apply_output)
    asyncio.run(agent_runs.execute(run.id))
    assert run.status_code == "completed"
    assert run.apply_status == "applied"
    assert json.loads(json.dumps(run.output_snapshot))["analyses"][0]["sales_deal_id"]
    assert run.evidence["unresolved_count"] == 2


def test_worker_does_not_count_tokens_twice_when_apply_fails(monkeypatch):
    member, _, run, output = case()
    run.status_code = "queued"
    run.output_snapshot = None
    run.apply_status = "pending"
    sessions = iter(
        [
            _Db(_Result(scalar=run)),
            _Db(_Result(scalar=run)),
            _Db(_Result(scalar=run)),
            _Db(_Result(scalar=run)),
        ]
    )
    monkeypatch.setattr(
        agent_runs, "get_sessionmaker", lambda: lambda: _SessionContext(next(sessions))
    )

    async def execute(_snapshot, _member_id):
        log_agent_event(
            "meeting_processing.model",
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
        )
        return output

    async def fail_apply(_db, _current):
        raise ValueError("meeting_apply_status_invalid")

    monkeypatch.setattr(service, "run", execute)
    monkeypatch.setattr(service, "apply_output", fail_apply)

    asyncio.run(agent_runs.execute(run.id))

    assert run.status_code == "failed"
    assert (run.input_tokens, run.output_tokens, run.total_tokens) == (20, 10, 30)


def test_run_and_report_locks_enforce_scope_and_source(monkeypatch):
    member, sections, run, _ = case()
    db = _Db(_Result(scalar=None))
    with pytest.raises(HTTPException, match="agent_run_not_found"):
        asyncio.run(service._locked_run(db, member, run.id))
    sql = str(db.statements[0])
    assert "team_id" in sql and "requested_by_member_id" in sql and "FOR UPDATE" in sql

    async def locked(db, member, report_id):
        assert report_id == run.test_report.id
        return run.test_report

    monkeypatch.setattr(reports_api, "_locked_report", locked)
    section_db = _Db(SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: sections)))
    report, locked_sections = asyncio.run(service._locked_report_and_deals(section_db, member, run))
    assert report is run.test_report and locked_sections == sections
    run.test_report.transcript = "원문이 바뀜"
    with pytest.raises(HTTPException, match="meeting_source_changed"):
        asyncio.run(service._locked_report_and_deals(_Db(), member, run))


@pytest.mark.anyio
@pytest.mark.parametrize("slow_writer,slow_deal", [(False, True), (True, False), (True, True)])
async def test_workflow_deadline_preserves_completed_report_and_deal_results(
    monkeypatch, slow_writer, slow_deal
):
    member, reports, run, expected = case()
    cancelled = set()
    previous_tasks = asyncio.all_tasks()
    writer_started, deals_started = asyncio.Event(), asyncio.Event()
    started_deals = set()
    timeout_contexts = []
    real_timeout_at, real_wait = asyncio.timeout_at, asyncio.wait

    def record_timeout(deadline):
        context = real_timeout_at(deadline)
        timeout_contexts.append(context)
        return context

    async def expire_after_branches_start(tasks, *, timeout):
        await asyncio.wait_for(
            asyncio.gather(writer_started.wait(), deals_started.wait()), timeout=5
        )
        assert len(timeout_contexts) == 2
        assert timeout_contexts[0].when() == timeout_contexts[1].when()
        assert 0 < timeout < service.RUN_TIMEOUT_SECONDS
        if slow_writer:
            # 실제 Timeout 취소를 쓰되, 빠른 분기 완료 후 만료시켜 CI 속도에 의존하지 않는다.
            timeout_contexts[1].reschedule(asyncio.get_running_loop().time())
        return await real_wait(tasks, timeout=0)

    async def analyze(snapshot, *, on_lookup):
        return expected.evidence

    async def write(source):
        writer_started.set()
        if slow_writer:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add("report")
        return expected.reports

    async def generate(**kwargs):
        deal_id = next(
            report.sales_deal_id
            for report in reports
            if str(report.sales_deal_id) in kwargs["input_text"]
        )
        started_deals.add(deal_id)
        if len(started_deals) == len(reports):
            deals_started.set()
        if slow_deal and deal_id == reports[1].sales_deal_id:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.add("deal")
        return meeting_analysis.MeetingFeatureOutput(
            features={
                **{name: "Unknown" for name in meeting_analysis.deal_baseline.FEATURE_NAMES},
                "Authority": "Low",
            }
        )

    async def predict_in_thread(function, features):
        return meeting_analysis.deal_baseline.DealPrediction(
            label="watch", high_probability=0.3, model_version="mock"
        )

    monkeypatch.setattr(service, "RUN_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(service.asyncio, "timeout_at", record_timeout)
    monkeypatch.setattr(meeting_analysis.asyncio, "wait", expire_after_branches_start)
    monkeypatch.setattr(service.meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    monkeypatch.setattr(meeting_analysis.asyncio, "to_thread", predict_in_thread)
    result = await service.run(run.input_snapshot, member.id)

    assert result.evidence == expected.evidence
    assert result.analyses[0].assessment is not None and result.analyses[0].error is None
    if slow_writer:
        assert result.reports is None
        assert result.errors == {"report_writing": "report_agent_timeout"}
    else:
        assert result.reports == expected.reports and result.errors == {}
    if slow_deal:
        assert result.analyses[1].features is None
        assert result.analyses[1].error == "deal_analysis_timeout"
    else:
        assert all(item.assessment is not None and item.error is None for item in result.analyses)
    assert cancelled == ({"report"} if slow_writer else set()) | ({"deal"} if slow_deal else set())
    assert asyncio.all_tasks() <= previous_tasks


@pytest.mark.anyio
async def test_workflow_passes_only_remaining_total_budget_to_deal_analysis(monkeypatch):
    member, _, run, expected = case()
    remaining = []

    async def analyze(snapshot, *, on_lookup):
        await asyncio.sleep(0)
        return expected.evidence

    async def write(source):
        return expected.reports

    async def features(evidence, crm, *, timeout):
        remaining.append(timeout)
        return expected.analyses

    monkeypatch.setattr(service, "RUN_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(service.meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(service.meeting_analysis, "run_for_deals", features)
    result = await service.run(run.input_snapshot, member.id)

    assert result.reports == expected.reports
    assert len(remaining) == 1 and 0 < remaining[0] < service.RUN_TIMEOUT_SECONDS


@pytest.mark.anyio
async def test_workflow_cancellation_cleans_both_downstream_branches(monkeypatch):
    member, _, run, expected = case()
    started, cancelled = set(), set()
    ready = asyncio.Event()
    previous_tasks = asyncio.all_tasks()

    async def analyze(snapshot, *, on_lookup):
        return expected.evidence

    async def block(kind):
        started.add(kind)
        if started == {"report", "deal"}:
            ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.add(kind)

    async def write(source):
        await block("report")

    async def generate(**kwargs):
        await block("deal")

    monkeypatch.setattr(service.meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(meeting_analysis, "generate_structured", generate)
    task = asyncio.create_task(service.run(run.input_snapshot, member.id))
    await asyncio.wait_for(ready.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert cancelled == {"report", "deal"}
    assert asyncio.all_tasks() <= previous_tasks
