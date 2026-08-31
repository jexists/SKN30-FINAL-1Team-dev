"""합성 입력/모의 DB로 공통 실행과 저장 경계를 검사한다. 골든셋 품질 평가는 아니다."""

import asyncio
import copy
import json
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_agent_runs import NOW, _Db, _member, _report, _Result, _run, _SessionContext
from test_report_writing_deep import draft, sample

from app.agents import meeting_analysis, meeting_content_analysis, report_writing_deep
from app.api import reports as reports_api
from app.schemas.agent_runs import AgentRunCreate
from app.schemas.meeting_content import SegmentAssignment
from app.services import agent_runs
from app.services import meeting_processing as service
from app.services.llm import LLMError


def case():
    source = sample()
    member = _member()
    activity_id = uuid4()
    reports = []
    for deal_id in source.evidence.selected_deal_ids:
        report = _report(member, transcript=source.transcript)
        report.report_kind = "meeting"
        report.source_activity_id = activity_id
        report.sales_deal_id = deal_id
        report.template_snapshot = {"fields": [{"id": "body", "label": "본문"}]}
        report.content = {"title": "합성 미팅", "values": {"body": ""}, "attachments": []}
        reports.append(report)
    snapshot = {
        "source": {
            "transcript": source.transcript,
            "selected_deal_ids": [str(value) for value in source.evidence.selected_deal_ids],
            "segments": [item.segment.model_dump(mode="json") for item in source.evidence.items],
        },
        "deals": [
            {"sales_deal_id": str(report.sales_deal_id), "deal_no": str(i), "title": f"딜{i}"}
            for i, report in enumerate(reports)
        ],
        "crm_context": source.crm_context,
        "activity_id": str(activity_id),
        "team_id": str(member.team_id),
        "assignment_overrides": [],
        "report_versions": [
            {
                "id": str(report.id),
                "sales_deal_id": str(report.sales_deal_id),
                "updated_at": report.updated_at.isoformat(),
            }
            for report in reports
        ],
    }
    result = service.MeetingProcessingOutput(
        reports=report_writing_deep.FreeformMeetingReports.model_validate(draft()),
        analyses=[
            meeting_analysis.DealFeatureResult(
                sales_deal_id=report.sales_deal_id, error="deal_prediction_failed"
            )
            for report in reports
        ],
        evidence=source.evidence,
        errors={},
    )
    run = _run(member, status_code="completed")
    run.agent_code = "meeting_processing"
    run.input_snapshot = snapshot
    run.output_snapshot = result.model_dump(mode="json")
    return member, reports, run, result


def test_new_run_contract_requires_unique_reports_and_versioned_overrides():
    base = {"agent_code": "meeting_processing", "idempotency_key": uuid4()}
    good = AgentRunCreate(**base, report_ids=[uuid4(), uuid4()])
    assert len(good.report_ids) == 2
    for values in (
        {},
        {"report_ids": []},
        {"report_ids": [UUID(int=1)] * 2},
        {"report_ids": [uuid4()], "parent_run_id": uuid4()},
    ):
        with pytest.raises(ValidationError):
            AgentRunCreate(**base, **values)
    override = {"segment_id": "S0003", "applicability": {"scope": "deal", "deal_ids": [uuid4()]}}
    with pytest.raises(ValidationError):
        AgentRunCreate(**base, report_ids=[uuid4()], assignment_overrides=[override])


def test_snapshot_builds_crm_once_and_checks_group_and_manual_assignment(monkeypatch):
    member, reports, parent, result = case()
    calls = []

    async def context(db, owner, activity_id, selected):
        calls.append(selected)
        return {"deals": parent.input_snapshot["deals"], "crm_context": {"contact": {}}}

    monkeypatch.setattr(service.meeting_context, "build_context", context)
    snapshot = asyncio.run(service.input_snapshot(None, member, reports))
    assert len(calls) == 1 and len(snapshot["source"]["selected_deal_ids"]) == 2
    for report in reports:
        report.source_snapshot = {"meeting_run_id": str(parent.id)}
    override = SegmentAssignment.model_validate(
        {
            "segment_id": "S0003",
            "applicability": {"scope": "deal", "deal_ids": [reports[1].sales_deal_id]},
        }
    )
    updated = asyncio.run(service.input_snapshot(None, member, reports, parent, [override]))
    assert updated["parent_evidence"] == result.evidence.model_dump(mode="json")
    reports[0].source_snapshot = {"meeting_run_id": str(uuid4())}
    with pytest.raises(HTTPException, match="meeting_assignment_stale"):
        asyncio.run(service.input_snapshot(None, member, reports, parent, [override]))
    reports[0].source_snapshot = {"meeting_run_id": str(parent.id)}
    override.segment_id = "S0002"
    with pytest.raises(HTTPException, match="meeting_assignment_not_unresolved"):
        asyncio.run(service.input_snapshot(None, member, reports, parent, [override]))
    reports[1].transcript = "다른 원문"
    with pytest.raises(HTTPException, match="meeting_reports_mismatch"):
        asyncio.run(service.input_snapshot(None, member, reports))


@pytest.mark.parametrize("report_failure", [False, True])
def test_workflow_shares_one_analysis_and_keeps_partial_results(monkeypatch, report_failure):
    member, _, run, expected = case()
    seen = []

    async def analyze(snapshot, *, lookup):
        seen.append("content")
        return expected.evidence

    async def write(source):
        assert source.evidence == expected.evidence
        seen.append("report")
        if report_failure:
            raise LLMError("report_agent_timeout")
        return expected.reports

    async def features(evidence, crm, *, timeout=None):
        assert evidence == expected.evidence
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

    def no_database():
        pytest.fail("기본 스냅샷의 이전 보고서를 다시 조회하면 안 된다")

    async def analyze(snapshot, *, lookup):
        agent_input = meeting_content_analysis.MeetingContentAgentInput.model_validate(snapshot)
        prompt = meeting_content_analysis._prompt_input(agent_input)
        assert "이전 미팅 전용 내용" not in prompt
        assert "previous_reports" not in prompt
        if request_history:
            for report, history in zip(reports, histories, strict=True):
                first = await lookup("previous_reports", report.sales_deal_id)
                assert first == history
                first["items"].append({"values": {"body": "도구 응답 변형"}})
                assert await lookup("previous_reports", report.sales_deal_id) == history
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

    monkeypatch.setattr(service, "get_sessionmaker", no_database)
    monkeypatch.setattr(service.meeting_content_analysis, "run", analyze)
    monkeypatch.setattr(service.report_writing_deep, "run", write)
    monkeypatch.setattr(service.meeting_analysis, "run_for_deals", features)

    actual = asyncio.run(service.run(run.input_snapshot, member.id))

    assert actual.reports == expected.reports
    assert run.input_snapshot["crm_context"]["previous_reports"] == histories
    assert len(actual.context_lookups) == (2 if request_history else 0)


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
    member, reports, run, output = case()
    if report_failure:
        output.reports = None
        output.errors = {"report_writing": "report_agent_failed"}
        run.output_snapshot = output.model_dump(mode="json")
    db = _Db()

    async def locked_run(*args):
        return run

    async def locked_reports(*args):
        return reports

    async def commit(db, member, reports):
        await db.commit()
        return reports

    monkeypatch.setattr(service, "_locked_run", locked_run)
    monkeypatch.setattr(service, "_locked_reports", locked_reports)
    monkeypatch.setattr(service, "_commit_reports", commit)
    return member, reports, run, db


def test_apply_is_atomic_idempotent_and_does_not_overwrite_human_text(monkeypatch):
    member, reports, run, db = storage(monkeypatch)
    reports[1].content["values"]["body"] = "사람이 쓴 보고서"
    asyncio.run(service.apply(db, member, run.id))
    assert "보안 승인" in reports[0].content["values"]["body"]
    assert reports[1].content["values"]["body"] == "사람이 쓴 보고서"
    assert reports[1].content["ai_values"]["body"] != "사람이 쓴 보고서"
    assert reports[0].content["meeting_shared"] == reports[1].content["meeting_shared"]
    for report in reports:
        assert (
            report.content["meeting_shared"]["common_report"]["body"] == "구매팀과 미팅을 진행했다."
        )
        assert "구매팀과 미팅을 진행했다." not in report.content["values"]["body"]
    assert "그거 다시 보내달래" in reports[0].content["meeting_shared"]["unassigned_report"]["body"]
    assert reports[0].ai_evidence["analysis_error"] == "deal_prediction_failed"
    assert reports[0].source_snapshot["evidence"]["transcript_sha256"]
    reports[0].content["values"]["body"] = "저장 후 다시 편집"
    asyncio.run(service.apply(db, member, run.id))
    assert reports[0].content["values"]["body"] == "저장 후 다시 편집"


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
    member, reports, run, db = storage(monkeypatch)
    for report in reports:
        report.template_snapshot = {"fields": fields}
        report.content["values"] = {field["id"]: "" for field in fields}
    reports[1].content["values"] = {"note": "사람이 작성한 내용"}
    original_values = [copy.deepcopy(report.content["values"]) for report in reports]

    asyncio.run(service.apply(db, member, run.id))

    for index, report in enumerate(reports):
        expected_draft = next(
            item
            for item in run.output_snapshot["reports"]["deal_reports"]
            if item["sales_deal_id"] == str(report.sales_deal_id)
        )
        generated = {expected_field or "body": expected_draft["body"]}
        assert report.content["values"] == (
            generated if index == 0 and expected_field is not None else original_values[index]
        )
        assert report.content["ai_values"] == generated
        assert report.content["ai_evidence"] == " · ".join(expected_draft["evidence_ids"])
        assert report.content["ai_generated_at"]
        assert report.source_snapshot["meeting_run_id"] == str(run.id)
        assert report.source_snapshot["evidence"] == run.output_snapshot["evidence"]


def test_apply_rejects_concurrent_edits_before_any_report_write(monkeypatch):
    member, reports, run, db = storage(monkeypatch)
    original = copy.deepcopy(reports[0].content)
    reports[1].updated_at = NOW.replace(day=18)
    with pytest.raises(HTTPException, match="meeting_report_changed"):
        asyncio.run(service.apply(db, member, run.id))
    assert reports[0].content == original
    assert db.commit_count == 0 and db.rollback_count == 1


def test_failed_writer_still_saves_unassigned_original_and_analysis_state(monkeypatch):
    member, reports, run, db = storage(monkeypatch, report_failure=True)
    asyncio.run(service.apply(db, member, run.id))
    assert reports[0].content["values"] == {"body": ""}
    shared = reports[0].content["meeting_shared"]
    assert shared["unassigned_report"]["evidence_ids"] == ["S0003", "S0004"]
    assert "기타 메모 ???" in shared["unassigned_report"]["body"]
    assert reports[0].ai_evidence["report_error"] == "report_agent_failed"


def test_notes_sync_without_changing_original_evidence(monkeypatch):
    member, reports, run, db = storage(monkeypatch)
    asyncio.run(service.apply(db, member, run.id))
    evidence = copy.deepcopy(reports[0].source_snapshot)
    revision = UUID(reports[0].content["meeting_shared"]["revision"])
    asyncio.run(
        service.update_notes(db, member, run.id, "공통 수정", "미지정 원문 확인 필요", revision)
    )
    assert reports[0].content["meeting_shared"] == reports[1].content["meeting_shared"]
    assert reports[0].source_snapshot == evidence
    with pytest.raises(HTTPException, match="meeting_notes_changed"):
        asyncio.run(
            service.update_notes(db, member, run.id, "오래된 탭 수정", "확인 필요", revision)
        )
    assert reports[0].content["meeting_shared"]["common_report"]["body"] == "공통 수정"
    revision = UUID(reports[0].content["meeting_shared"]["revision"])
    reports[1].source_snapshot = {"meeting_run_id": str(uuid4())}
    with pytest.raises(HTTPException, match="meeting_notes_stale"):
        asyncio.run(service.update_notes(db, member, run.id, "다시 수정", "확인 필요", revision))


def test_regeneration_preserves_edited_shared_notes_as_well_as_deal_bodies(monkeypatch):
    member, reports, run, db = storage(monkeypatch)
    asyncio.run(service.apply(db, member, run.id))
    revision = UUID(reports[0].content["meeting_shared"]["revision"])
    asyncio.run(
        service.update_notes(db, member, run.id, "사람이 확정한 공통 정정", "미지정 수정", revision)
    )
    run.id = uuid4()
    for version, report in zip(run.input_snapshot["report_versions"], reports, strict=True):
        version["updated_at"] = report.updated_at.isoformat()
    asyncio.run(service.apply(db, member, run.id))
    shared = reports[0].content["meeting_shared"]
    assert shared["common_report"]["body"] == "사람이 확정한 공통 정정"
    assert shared["common_report"]["ai_body"] != shared["common_report"]["body"]
    assert shared["unassigned_report"]["body"] == "미지정 수정"
    assert shared["revision"] != str(revision)


def test_background_dispatch_serializes_uuid_results(monkeypatch):
    member, _, run, output = case()
    run.status_code = "queued"
    first = _Db(_Result(scalar=run))
    last = _Db(_Result(scalar=run))
    sessions = iter([first, last])
    monkeypatch.setattr(
        agent_runs, "get_sessionmaker", lambda: lambda: _SessionContext(next(sessions))
    )

    async def execute(snapshot, member_id):
        assert member_id == member.id
        return output

    monkeypatch.setattr(service, "run", execute)
    asyncio.run(agent_runs.execute(run.id))
    assert run.status_code == "completed"
    assert json.loads(json.dumps(run.output_snapshot))["analyses"][0]["sales_deal_id"]
    assert run.evidence["unresolved_count"] == 2


def test_run_and_report_locks_enforce_scope_and_source(monkeypatch):
    member, reports, run, _ = case()
    db = _Db(_Result(scalar=None))
    with pytest.raises(HTTPException, match="agent_run_not_found"):
        asyncio.run(service._locked_run(db, member, run.id))
    sql = str(db.statements[0])
    assert "team_id" in sql and "requested_by_member_id" in sql and "FOR UPDATE" in sql

    async def locked(db, member, report_id):
        return next(report for report in reports if report.id == report_id)

    monkeypatch.setattr(reports_api, "_locked_report", locked)
    assert len(asyncio.run(service._locked_reports(None, member, run))) == 2
    reports[1].transcript = "원문이 바뀜"
    with pytest.raises(HTTPException, match="meeting_reports_mismatch"):
        asyncio.run(service._locked_reports(None, member, run))


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

    async def analyze(snapshot, *, lookup):
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
            features={name: "Unknown" for name in meeting_analysis.deal_baseline.FEATURE_NAMES}
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

    async def analyze(snapshot, *, lookup):
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

    async def analyze(snapshot, *, lookup):
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
