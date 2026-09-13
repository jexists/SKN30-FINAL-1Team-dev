"""임시 초안은 격리하고, 재접속/완료/접근 검사는 기존 실행 하나에만 연결한다."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import create_model
from test_agent_runs import _Db, _member, _Result, _SessionContext
from test_agent_runs import _run as _base_run

from app.agents.reports.harness import (
    _ACTIVE_ASSIGNMENT,
    WorkflowSpec,
    WorkUnit,
    WriterArtifact,
    _Coordinator,
    _Events,
)
from app.agents.reports.meeting import _DealDraft
from app.api import agent_runs as api
from app.services import agent_stream as stream


def _run(member, *, status_code):
    run = _base_run(member, status_code=status_code)
    run.scope_key = "daily:2026-08-17"
    run.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    return run


def test_preview_isolated_bounded_replayed_and_replaced_not_appended():
    async def check(run_id, text):
        deal_id = str(uuid4())
        with stream.progress_context(run_id):
            stream.publish_progress(
                "report_writing",
                preview={
                    "section": "deal",
                    "sales_deal_id": deal_id,
                    "body": text,
                    "revision": 1,
                },
            )
            await asyncio.sleep(0)
            assert stream.progress_snapshot(run_id)["previews"][0]["body"] == text
            stream.publish_progress("report_review", review_attempt=2, review_limit=10)
            stream.publish_progress("analysis_complete")
            assert stream.progress_snapshot(run_id)["stage"] == "report_review"
            for revision, body in ((2, "수정"), (1, "오래된 응답"), (2, "수정 중")):
                stream.publish_progress(
                    preview={
                        "section": "deal",
                        "sales_deal_id": deal_id,
                        "body": body,
                        "revision": revision,
                    }
                )
            snapshot = stream.progress_snapshot(run_id)
            assert snapshot["previews"][0]["body"] == "수정 중"
            snapshot["previews"][0]["body"] = "외부 변경"
            assert stream.progress_snapshot(run_id)["previews"][0]["body"] == "수정 중"
            stream.publish_progress(
                preview={
                    "section": "deal",
                    "sales_deal_id": "invalid",
                    "body": "차단",
                    "revision": 3,
                }
            )
            assert len(stream.progress_snapshot(run_id)["previews"]) == 1
        assert stream.progress_snapshot(run_id) is None

    async def both():
        await asyncio.gather(check(uuid4(), "보고서A"), check(uuid4(), "보고서B"))

    asyncio.run(both())
    assert not stream._states


def test_progress_flush_survives_memory_cleanup(monkeypatch):
    run_id, persisted = uuid4(), []

    async def save(state):
        persisted.append(stream._db_snapshot(state))

    monkeypatch.setattr(stream, "_persist_state", save)

    async def check():
        with stream.progress_context(run_id, lease_owner="worker-1", attempt_count=1):
            stream.publish_stream_preview(
                section="body",
                sales_deal_id=None,
                body="초안 일부",
                phase="synthesize",
                draft_version=1,
            )
            await stream.flush_progress_snapshot(run_id)
            assert persisted[-1]["previews"][0]["body"] == "초안 일부"
        assert stream.progress_snapshot(run_id) is None

    asyncio.run(check())
    assert persisted[-1]["attempt_count"] == 1


def test_preview_cache_has_hard_limit_and_cleanup(monkeypatch):
    monkeypatch.setattr(stream, "MAX_LIVE_PREVIEWS", 1)
    first, second = uuid4(), uuid4()
    with stream.progress_context(first):
        old_state = stream._current.get()
        stream.publish_progress(
            preview={
                "section": "common",
                "sales_deal_id": None,
                "body": "폐기할 미리보기",
                "revision": 1,
            }
        )
        with stream.progress_context(second):
            assert stream.progress_snapshot(first) is None
            assert stream.progress_snapshot(second)
            assert not old_state["previews"]
        stream.publish_progress(
            preview={
                "section": "common",
                "sales_deal_id": None,
                "body": "다시 쌓지 않음",
                "revision": 2,
            }
        )
        assert not old_state["previews"]
    assert not stream._states


def test_preview_character_cap_does_not_replace_previous_snapshot(monkeypatch):
    monkeypatch.setattr(stream, "MAX_PREVIEW_CHARACTERS", 5)
    run_id = uuid4()
    with stream.progress_context(run_id):
        for section, body in (("common", "12345"), ("unassigned", "6"), ("common", "123456")):
            stream.publish_progress(
                preview={
                    "section": section,
                    "sales_deal_id": None,
                    "body": body,
                    "revision": 1,
                }
            )
        previews = stream.progress_snapshot(run_id)["previews"]
        assert len(previews) == 1 and previews[0]["body"] == "12345"


def test_streaming_preview_keeps_confirmed_snapshot_and_rejects_old_revision():
    run_id, deal_id = uuid4(), uuid4()
    with stream.progress_context(run_id):
        stream.publish_stream_preview(
            section="deal",
            sales_deal_id=deal_id,
            body="v1 일부",
            phase="write_initial",
            draft_version=1,
        )
        stream.publish_stream_preview(
            section="deal",
            sales_deal_id=str(deal_id),
            body="v1 확정",
            phase="write_initial",
            draft_version=1,
            preview_state="confirmed",
        )
        stream.publish_stream_preview(
            section="deal",
            sales_deal_id=deal_id,
            body="v2 일부",
            phase="repair",
            draft_version=2,
        )
        snapshot = stream.progress_snapshot(run_id)
        assert snapshot["previews"][0]["body"] == "v2 일부"
        assert snapshot["confirmed_previews"][0]["body"] == "v1 확정"
        stream.publish_stream_preview(
            section="deal",
            sales_deal_id=deal_id,
            body="늦은 v1",
            phase="write_initial",
            draft_version=1,
        )
        assert stream.progress_snapshot(run_id)["previews"][0]["body"] == "v2 일부"
        streaming_revision = stream.progress_snapshot(run_id)["previews"][0]["revision"]
        stream.publish_stream_preview(
            section="deal",
            sales_deal_id=deal_id,
            body="v2 확정",
            phase="repair",
            draft_version=2,
            preview_state="confirmed",
        )
        stream.publish_stream_preview(
            section="deal",
            sales_deal_id=str(deal_id),
            body="늦은 v2",
            phase="repair",
            draft_version=2,
        )
        snapshot = stream.progress_snapshot(run_id)
        assert snapshot["previews"][0]["body"] == "v2 확정"
        assert snapshot["confirmed_previews"][0]["body"] == "v2 확정"
        assert snapshot["confirmed_previews"][0]["revision"] > streaming_revision


def test_coordinator_phase_counts_reset_and_track_completed_failed_units():
    unit = WorkUnit(
        "write-001",
        "common_report",
        _DealDraft,
        frozenset({"common_report.body"}),
        frozenset({"S1"}),
        "draft",
    )
    spec = WorkflowSpec(
        "meeting",
        "sales-meeting-report",
        "report_writing",
        "",
        {},
        (unit,),
        {},
        lambda values: unit.schema.model_validate({"kind": "section", "body": "x"}),
        lambda draft: None,
        lambda *args: None,
    )
    coordinator = _Coordinator(spec, object())
    second = WorkUnit(
        "write-002",
        "unassigned_report",
        _DealDraft,
        frozenset({"unassigned_report.body"}),
        frozenset({"S2"}),
        "draft",
    )
    coordinator.assignments[second.work_unit_id] = coordinator.assignments[unit.work_unit_id]
    coordinator.assignments[second.work_unit_id] = coordinator.assignments[
        second.work_unit_id
    ].__class__(
        second.work_unit_id,
        "write_initial",
        "sales-meeting-report",
        second,
        locations=second.locations,
    )
    run_id = uuid4()
    with stream.progress_context(run_id):
        coordinator._publish_phase_counts()
        coordinator.finished_assignments.add(unit.work_unit_id)
        coordinator.failed_assignments.add(second.work_unit_id)
        coordinator._publish_phase_counts()
        counts = stream.progress_snapshot(run_id)["phase_counts"]
        assert counts == {"phase": "write_initial", "total": 2, "completed": 1, "failed": 1}
        coordinator.phase = "repair"
        coordinator.assignments = {}
        coordinator._publish_phase_counts()
        assert stream.progress_snapshot(run_id)["phase_counts"] == {
            "phase": "repair",
            "total": 0,
            "completed": 0,
            "failed": 0,
        }


def test_native_agent_callback_publishes_before_model_returns():
    output_schema = create_model("WriterArtifact", __base__=WriterArtifact, draft=(_DealDraft, ...))
    release = asyncio.Event()
    continue_chunks = asyncio.Event()
    first_chunk = asyncio.Event()
    second_chunk = asyncio.Event()

    class StreamingModel(BaseChatModel):
        @property
        def _llm_type(self):
            return "test-streaming-model"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, *args, **kwargs):
            raise AssertionError("async graph should use _agenerate")

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            for args, name, ident in [
                ('{"draft":{"title":"제목","body":"한글 일부', "WriterArtifact", "c1"),
                (' 더"}}', None, None),
            ]:
                chunk = ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_call_chunks=[{"name": name, "args": args, "id": ident, "index": 0}],
                    )
                )
                await run_manager.on_llm_new_token("", chunk=chunk)
                if name == "WriterArtifact":
                    first_chunk.set()
                    await continue_chunks.wait()
                else:
                    second_chunk.set()
            await release.wait()
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "WriterArtifact",
                                    "args": {
                                        "draft": {"title": "제목", "body": "한글 일부 더"},
                                        "work_unit_id": "write-001",
                                        "base_draft_version": 0,
                                        "plan": [
                                            {"location": "body", "intent": "x", "evidence": ["e"]}
                                        ],
                                    },
                                    "id": "c1",
                                }
                            ],
                        )
                    )
                ]
            )

    async def run():
        from langchain.agents import create_agent
        from langchain.agents.structured_output import ToolStrategy

        run_id, deal_id = uuid4(), str(uuid4())
        coordinator = SimpleNamespace(spec=SimpleNamespace(report_kind="meeting"))
        assignment = SimpleNamespace(
            phase="write_initial",
            unit=SimpleNamespace(schema=_DealDraft, scope="deal_reports[0]", sales_deal_id=deal_id),
            locations=frozenset({"deal_reports[0].body"}),
        )
        events = _Events("test", model_limit=4, tool_limit=4, task_limit=4)
        token = _ACTIVE_ASSIGNMENT.set((coordinator, assignment))
        try:
            with stream.progress_context(run_id):
                task = asyncio.create_task(
                    create_agent(
                        model=StreamingModel(), response_format=ToolStrategy(output_schema)
                    ).ainvoke(
                        {"messages": [{"role": "user", "content": "write"}]},
                        config={"callbacks": [events]},
                    )
                )
                await asyncio.wait_for(first_chunk.wait(), timeout=2)
                snapshot = stream.progress_snapshot(run_id)
                assert not task.done()
                assert snapshot and snapshot["previews"][0]["body"] == "한글 일부"
                continue_chunks.set()
                await asyncio.wait_for(second_chunk.wait(), timeout=2)
                assert stream.progress_snapshot(run_id)["previews"][0]["body"] == "한글 일부 더"
                release.set()
                await asyncio.wait_for(task, timeout=2)
        finally:
            _ACTIVE_ASSIGNMENT.reset(token)

    asyncio.run(run())


def test_prepare_and_review_partial_stage_results_are_safe_and_scoped():
    run_id = uuid4()
    coordinator = SimpleNamespace(
        spec=SimpleNamespace(
            report_kind="daily",
            units=(SimpleNamespace(scope="deal_reports[0]", locations={"deal_reports[0].body"}),),
        )
    )

    async def emit(phase, args, unit, locations):
        events = _Events("test", model_limit=4, tool_limit=4, task_limit=4)
        assignment = SimpleNamespace(
            phase=phase, unit=unit, locations=frozenset(locations), work_unit_id="review-001"
        )
        token = _ACTIVE_ASSIGNMENT.set((coordinator, assignment))
        try:
            with stream.progress_context(run_id):
                chunk = SimpleNamespace(
                    message=AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {
                                "name": "ReportReview"
                                if phase == "review_initial"
                                else "WriterArtifact",
                                "args": args,
                                "index": 0,
                            }
                        ],
                    )
                )
                await events.on_llm_new_token("", chunk=chunk, run_id="llm-1")
                return stream.progress_snapshot(run_id)
        finally:
            _ACTIVE_ASSIGNMENT.reset(token)

    prepare = asyncio.run(
        emit(
            "prepare",
            '{"draft":{"source_id":"source:1","facts":[{"source_id":"source:1",'
            '"content":"핵심 사실"}],'
            '"plan":[{"evidence":"비공개"}]}}',
            SimpleNamespace(scope="source:1", locations={"source:1"}),
            {"source:1"},
        )
    )
    assert prepare and prepare["stage_results"][0]["body"] == "핵심 사실: 핵심 사실"
    wrong = asyncio.run(
        emit(
            "prepare",
            '{"draft":{"source_id":"source:2","facts":[{"source_id":"source:2",'
            '"content":"노출 금지"}]}}',
            SimpleNamespace(scope="source:1", locations={"source:1"}),
            {"source:1"},
        )
    )
    assert wrong and wrong["stage_results"] == []
    review = asyncio.run(
        emit(
            "review_initial",
            '{"issues":[{"location":"deal_reports[0].body","action":"표현 수정"},'
            '{"location":"other","action":"노출 금지"}]}',
            None,
            {"deal_reports[0].body"},
        )
    )
    assert review and [item["body"] for item in review["stage_results"]] == ["표현 수정"]


def test_stage_result_review_and_repair_same_caller_key_are_preserved():
    run_id = uuid4()
    with stream.progress_context(run_id):
        stream.publish_stage_result(stage="review_initial", key="scope:issue:x:1", body="검토")
        stream.publish_stage_result(stage="repair", key="scope:issue:x:1", body="수정 대상")
        values = stream.progress_snapshot(run_id)["stage_results"]
    assert {item["body"] for item in values} == {"검토", "수정 대상"}


@pytest.mark.parametrize(
    ("report_kind", "phase", "scope", "locations", "draft", "expected_section", "expected_version"),
    [
        (
            "meeting",
            "write_initial",
            "deal_reports[0]",
            {"deal_reports[0].body"},
            {"body": "딜 본문"},
            "deal",
            1,
        ),
        (
            "meeting",
            "repair",
            "common_report",
            {"common_report.body"},
            {"body": "공통 수정"},
            "common",
            2,
        ),
        (
            "meeting",
            "repair",
            "unassigned_report",
            {"unassigned_report.body"},
            {"body": "미지정 수정"},
            "unassigned",
            2,
        ),
        (
            "daily",
            "synthesize",
            "body",
            {"fields[0].value"},
            {"fields": [{"field_id": "body", "value": "기간 본문"}]},
            "body",
            1,
        ),
        (
            "weekly",
            "repair",
            "body",
            {"fields[0].value"},
            {"fields": [{"field_id": "body", "value": "주간 수정"}]},
            "body",
            2,
        ),
    ],
)
def test_writer_artifact_body_stream_scope_and_phase(
    report_kind,
    phase,
    scope,
    locations,
    draft,
    expected_section,
    expected_version,
):
    async def run():
        run_id, deal_id = (
            uuid4(),
            str(uuid4()) if report_kind == "meeting" and scope.startswith("deal") else None,
        )
        coordinator = SimpleNamespace(spec=SimpleNamespace(report_kind=report_kind))
        assignment = SimpleNamespace(
            phase=phase,
            unit=SimpleNamespace(schema=_DealDraft, scope=scope, sales_deal_id=deal_id),
            locations=frozenset(locations),
        )
        events = _Events("test", model_limit=4, tool_limit=4, task_limit=4)
        token = _ACTIVE_ASSIGNMENT.set((coordinator, assignment))
        try:
            with stream.progress_context(run_id):
                chunk = ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="무시할 plaintext",
                        tool_call_chunks=[
                            {
                                "name": "OtherTool",
                                "args": '{"draft":{"body":"금지"}}',
                                "id": "x",
                                "index": 1,
                            },
                            {
                                "name": "WriterArtifact",
                                "args": json.dumps({"draft": draft}, ensure_ascii=False),
                                "id": "w",
                                "index": 0,
                            },
                        ],
                    )
                )
                await events.on_llm_new_token("무시할 plaintext", chunk=chunk, run_id=run_id)
                snapshot = stream.progress_snapshot(run_id)
                assert snapshot and len(snapshot["previews"]) == 1
                preview = snapshot["previews"][0]
                expected_body = draft.get("body") or draft["fields"][0]["value"]
                assert preview["section"] == expected_section
                assert preview["body"] == expected_body
                assert preview["draft_version"] == expected_version
        finally:
            _ACTIVE_ASSIGNMENT.reset(token)

    asyncio.run(run())


@pytest.mark.parametrize(
    "phase,draft",
    [
        ("prepare", {"body": "차단"}),
        ("review_initial", {"body": "차단"}),
        ("repair", {"title": "제목만"}),
    ],
)
def test_writer_artifact_body_stream_requires_write_location(phase, draft):
    async def run():
        run_id = uuid4()
        coordinator = SimpleNamespace(spec=SimpleNamespace(report_kind="meeting"))
        assignment = SimpleNamespace(
            phase=phase,
            unit=SimpleNamespace(
                schema=_DealDraft, scope="deal_reports[0]", sales_deal_id=str(uuid4())
            ),
            locations=frozenset(
                {"deal_reports[0].title" if phase == "repair" else "deal_reports[0].body"}
            ),
        )
        events = _Events("test", model_limit=4, tool_limit=4, task_limit=4)
        token = _ACTIVE_ASSIGNMENT.set((coordinator, assignment))
        try:
            with stream.progress_context(run_id):
                chunk = ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="plaintext",
                        tool_call_chunks=[
                            {
                                "name": "WriterArtifact",
                                "args": json.dumps({"draft": draft}),
                                "id": "w",
                                "index": 0,
                            }
                        ],
                    )
                )
                await events.on_llm_new_token("plaintext", chunk=chunk, run_id=run_id)
                assert stream.progress_snapshot(run_id)["previews"] == []
        finally:
            _ACTIVE_ASSIGNMENT.reset(token)

    asyncio.run(run())


def test_events_replay_current_preview_recheck_access_release_db_and_end(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")
    initial = _Db(_Result(scalar=run))
    finished = _run(member, status_code="completed")
    finished.id = run.id
    finished.output_snapshot = {"result": "validated"}
    later = _Db(_Result(scalar=finished))
    checks = []

    async def authenticated(request, db):
        checks.append(db)
        return member

    async def connected():
        return False

    monkeypatch.setattr(api, "get_current_member", authenticated)
    monkeypatch.setattr(api, "get_sessionmaker", lambda: lambda: _SessionContext(later))
    monkeypatch.setattr(api, "RETRY_AFTER_SECONDS", 0.01)

    async def read():
        with stream.progress_context(run.id):
            stream.publish_progress(
                "report_review",
                review_attempt=1,
                review_limit=10,
                report_kind="meeting",
                phase_counts={"phase": "review_initial", "total": 1, "completed": 0, "failed": 0},
                preview={
                    "section": "unassigned",
                    "sales_deal_id": None,
                    "body": "미지정 원문",
                    "revision": 1,
                },
            )
            run.progress_snapshot = stream.progress_snapshot(run.id)
            response = await api.stream_agent_run(
                run.id,
                SimpleNamespace(is_disconnected=connected),
                member,
                initial,
            )
            assert initial.rollback_count == 1
            return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert checks == [later]
    events = [part for part in chunks if part.startswith("event:")]
    assert events[0].startswith("event: progress")
    assert "미지정 원문" in events[0]
    progress_data = json.loads(events[0].split("data: ", 1)[1])
    assert progress_data["report_kind"] == "meeting"
    assert progress_data["phase_counts"]["total"] == 1
    assert progress_data["sequence"] >= 1
    assert progress_data["confirmed_previews"] == []
    done = json.loads(events[-1].split("data: ", 1)[1])
    assert done["id"] == str(run.id) and done["output_snapshot"] == {"result": "validated"}
    assert initial.added == later.added == []  # 스트림은 실행/저장 작업을 시작하지 않는다.


def test_events_refuse_unknown_or_unauthorized_run_before_preview():
    async def read():
        with pytest.raises(HTTPException) as caught:
            await api.stream_agent_run(
                uuid4(), SimpleNamespace(), _member(), _Db(_Result(scalar=None))
            )
        assert caught.value.status_code == 404

    asyncio.run(read())


@pytest.mark.parametrize("viewer", ["manager", "expired"])
def test_report_preview_is_requester_only_and_expires_before_stream(viewer):
    owner = _member()
    run = _run(owner, status_code="running")
    member = owner
    if viewer == "manager":
        member = _member(role="manager", team_id=owner.team_id)
    else:
        run.payload_expires_at = datetime.now(UTC) - timedelta(seconds=1)

    async def read():
        with stream.progress_context(run.id):
            stream.publish_progress(
                preview={
                    "section": "common",
                    "sales_deal_id": None,
                    "body": "노출되면 안 되는 본문",
                    "revision": 1,
                }
            )
            with pytest.raises(HTTPException) as caught:
                await api.stream_agent_run(
                    run.id,
                    SimpleNamespace(),
                    member,
                    _Db(_Result(scalar=run)),
                )
            assert caught.value.status_code == 404

    asyncio.run(read())


def test_stream_stops_before_preview_when_payload_expires(monkeypatch):
    member = _member()
    run = SimpleNamespace(id=uuid4(), status_code="running")
    checks = iter((True, False))

    async def get(*_args):
        return run

    async def connected():
        return False

    monkeypatch.setattr(api.agent_run_service, "get", get)
    monkeypatch.setattr(
        api.agent_run_service,
        "generation_payload_visible",
        lambda *_args: next(checks),
    )

    async def read():
        response = await api.stream_agent_run(
            run.id,
            SimpleNamespace(is_disconnected=connected),
            member,
            _Db(),
        )
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert len(chunks) == 1
    assert json.loads(chunks[0].split("data: ", 1)[1]) == {"detail": "agent_run_not_found"}


def test_terminal_reconnect_uses_db_without_cached_preview():
    member = _member()
    run = _run(member, status_code="failed")
    run.error_message = "report_agent_timeout"

    async def connected():
        return False

    async def read():
        response = await api.stream_agent_run(
            run.id,
            SimpleNamespace(is_disconnected=connected),
            member,
            _Db(_Result(scalar=run)),
        )
        return [chunk async for chunk in response.body_iterator]

    events = asyncio.run(read())
    assert len(events) == 1 and events[0].startswith("event: done")
    assert "report_agent_timeout" in events[0]


def test_stream_stops_when_current_access_is_revoked(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")

    async def denied(request, session):
        raise HTTPException(403, "member_not_linked")

    async def connected():
        return False

    monkeypatch.setattr(api, "get_current_member", denied)
    monkeypatch.setattr(api, "get_sessionmaker", lambda: lambda: _SessionContext(_Db()))
    monkeypatch.setattr(api, "RETRY_AFTER_SECONDS", 0)

    async def read():
        with stream.progress_context(run.id):
            stream.publish_progress(
                preview={
                    "section": "common",
                    "sales_deal_id": None,
                    "body": "권한 회수 뒤에는 노출 금지",
                    "revision": 1,
                }
            )
            response = await api.stream_agent_run(
                run.id,
                SimpleNamespace(is_disconnected=connected),
                member,
                _Db(_Result(scalar=run)),
            )
            return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert chunks[-1].startswith("event: error") and "member_not_linked" in chunks[-1]
    assert not any(chunk.startswith(("event: progress", "event: done")) for chunk in chunks)


@pytest.mark.parametrize("timed_out", [False, True], ids=["recheck-unavailable", "deadline"])
def test_stream_failure_or_deadline_ends_without_done(monkeypatch, timed_out):
    member = _member()
    run = _run(member, status_code="running")
    errors = []

    async def broken(request, session):
        raise RuntimeError("db_gone")

    async def connected():
        return False

    ticks = iter([0, 0, 25 * 60 + 1])
    monkeypatch.setattr(api, "monotonic", lambda: next(ticks) if timed_out else 0)
    monkeypatch.setattr(api, "get_current_member", broken)
    monkeypatch.setattr(api, "get_sessionmaker", lambda: lambda: _SessionContext(_Db()))
    monkeypatch.setattr(api, "RETRY_AFTER_SECONDS", 0)
    monkeypatch.setattr(
        api, "log_agent_error", lambda error, **fields: errors.append((error, fields))
    )

    async def read():
        response = await api.stream_agent_run(
            run.id,
            SimpleNamespace(is_disconnected=connected),
            member,
            _Db(_Result(scalar=run)),
        )
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    expected = "agent_stream_timeout" if timed_out else "agent_stream_unavailable"
    assert chunks[-1].startswith("event: error")
    assert json.loads(chunks[-1].split("data: ", 1)[1]) == {"detail": expected}
    assert not any(chunk.startswith("event: done") for chunk in chunks)
    if timed_out:
        assert not errors
    else:
        assert len(errors) == 1 and isinstance(errors[0][0], RuntimeError)
        assert errors[0][1] == {
            "stage": "agent_stream",
            "run_id": str(run.id),
            "error_code": expected,
        }
