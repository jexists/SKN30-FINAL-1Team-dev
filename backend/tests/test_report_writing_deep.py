"""실제 Deep Agents/LangGraph 실행. 모델 응답만 합성해 외부 통신 없이 검사한다."""

import asyncio
import json
from itertools import count
from uuid import UUID, uuid4

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, LLMResult
from openai import APITimeoutError
from pydantic import PrivateAttr

from app.agents import report_writing_deep as writer
from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    MeetingContentInput,
    build_evidence_ledger,
)
from app.services.agent_logging import agent_log_context
from app.services.llm import LLMError

DEAL_A = UUID(int=1)
DEAL_B = UUID(int=2)


class ScriptedModel(FakeMessagesListChatModel):
    _seen: list = PrivateAttr(default_factory=list)
    _tool_sets: list = PrivateAttr(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        self._tool_sets.append(
            {tool.name if hasattr(tool, "name") else tool["function"]["name"] for tool in tools}
        )
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._seen.append(messages)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(uuid4())}])


def sample():
    texts = [
        "구매팀과 만났다.",
        "A는 보안 승인 후 예산 검토 예정이다.",
        "그거 다시 보내달래.",
        "기타 메모 ???",
    ]
    transcript = "\n".join(texts)
    start = 0
    segments = []
    for i, text in enumerate(texts, 1):
        segments.append(
            {"segment_id": f"S{i:04}", "start": start, "end": start + len(text), "text": text}
        )
        start += len(text) + 1
    source = MeetingContentInput(
        transcript=transcript,
        selected_deal_ids=[DEAL_A, DEAL_B],
        segments=segments,
    )
    analysis = MeetingContentAnalysisOutput(
        assignments=[
            {"segment_id": "S0001", "applicability": {"scope": "meeting_context"}},
            {"segment_id": "S0002", "applicability": {"scope": "deal", "deal_ids": [DEAL_A]}},
            {"segment_id": "S0003", "applicability": {"scope": "unresolved"}},
            {"segment_id": "S0004", "applicability": {"scope": "out_of_scope"}},
        ]
    )
    return writer.ReportWritingInput(
        transcript=transcript,
        evidence=build_evidence_ledger(source, analysis),
        crm_context={"company": {"name": "합성회사"}},
    )


def draft():
    return {
        "deal_reports": [
            {
                "sales_deal_id": str(DEAL_A),
                "body": "A는 보안 승인을 받은 뒤 예산을 검토할 예정이다.",
                "evidence_ids": ["S0002"],
            },
            {
                "sales_deal_id": str(DEAL_B),
                "body": "이번 미팅에서 B의 구체적인 논의는 확인되지 않았다.",
                "evidence_ids": [],
            },
        ],
        "common_report": {"body": "구매팀과 미팅을 진행했다.", "evidence_ids": ["S0001"]},
        "unassigned_report": {
            "body": "딜 미지정 · 확인 필요: ‘그거 다시 보내달래.’, ‘기타 메모 ???’. "
            "대상 딜과 의미를 확인해야 한다.",
            "evidence_ids": ["S0003", "S0004"],
        },
    }


def test_actual_graph_reads_skill_delegates_and_revises_after_review(monkeypatch):
    import deepagents.middleware.subagents

    subagent_middlewares = []
    original = deepagents.middleware.subagents.create_sub_agent

    def record_subagent(spec, **kwargs):
        subagent_middlewares.extend(item.name for item in spec.get("middleware", []))
        return original(spec, **kwargs)

    monkeypatch.setattr(deepagents.middleware.subagents, "create_sub_agent", record_subagent)
    good = draft()
    bad = draft()
    bad["deal_reports"][0]["body"] = "A의 예산은 승인됐다."
    model = ScriptedModel(
        responses=[
            call("read_file", file_path="/skills/sales-meeting-report/SKILL.md"),
            call("read_meeting_evidence"),
            call("write_todos", todos=[{"content": "딜별 작성 후 검토", "status": "in_progress"}]),
            call("task", subagent_type="general-purpose", description=f"딜 {DEAL_A}의 보고서 작성"),
            call("read_meeting_evidence", sales_deal_id=str(DEAL_A)),
            AIMessage(content="A는 보안 승인 후 예산 검토 예정이다. 근거 S0002."),
            call("review_report", draft=bad),
            call(
                "ReportReview",
                issues=["예산 승인 사실 없음. 보안 승인 후 검토 예정이라는 조건을 복원하라."],
            ),
            call("review_report", draft=good),
            call("ReportReview", issues=[]),
            call("FreeformMeetingReports", **good),
        ]
    )

    result = asyncio.run(writer.run(sample(), model=model))

    assert result.model_dump(mode="json") == good
    assert any("예산 승인 사실 없음" in str(messages) for messages in model._seen)
    assert "관심, 자료 요청, 검토 의향, 구매 합의, 발주를 구별한다" in model._seen[1][-1].content
    writer_turn = model._seen[5]
    evidence = next(message for message in writer_turn if message.type == "tool")
    assert "S0001" in evidence.content and "S0002" in evidence.content
    assert "S0003" not in evidence.content and "S0004" not in evidence.content
    assert all(not {"execute", "web_search"} & names for names in model._tool_sets)
    assert len(model._seen) == 10  # 수정/위임은 정상 수행하고 통과 뒤 최종 재호출은 생략한다.
    assert subagent_middlewares and "finish_accepted_report" not in subagent_middlewares


@pytest.mark.parametrize("deal_id", [DEAL_A, DEAL_B])
def test_history_is_shared_with_reviewer_but_scoped_for_deal_writer(deal_id):
    source = sample()
    histories = [
        {
            "kind": "previous_reports",
            "sales_deal_id": str(deal),
            "before": "2026-08-31T09:00:00+09:00",
            "limit": 5,
            "truncated": False,
            "text_limit_per_report": 8_000,
            "items": [
                {
                    "report_id": str(uuid4()),
                    "sales_deal_id": str(deal),
                    "report_date": "2026-08-20",
                    "meeting_at": "2026-08-20T09:00:00+09:00",
                    "status_code": "approved",
                    "values": {"body": f"딜 {deal}의 이전 미팅에서 비교표를 요청했다."},
                    "values_truncated": False,
                }
            ],
        }
        for deal in (DEAL_A, DEAL_B)
    ]
    other_context = {"kind": "product_details", "items": []}
    additional = [
        {"kind": "previous_reports", "sales_deal_id": item["sales_deal_id"], "data": item}
        for item in histories
    ]
    source.crm_context.update(
        previous_reports=histories,
        additional_context=[*additional, other_context],
    )
    original = source.model_dump(mode="json")
    model = ScriptedModel(
        responses=[
            call("read_meeting_evidence"),
            call("task", subagent_type="general-purpose", description=f"딜 {deal_id} 초안"),
            call("read_meeting_evidence", sales_deal_id=str(deal_id)),
            AIMessage(content="이번 원문에 근거가 있는 내용만 작성한다."),
            call("review_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    result = asyncio.run(writer.run(source, model=model))
    assert result.model_dump(mode="json") == draft()
    shared = json.loads(model._seen[1][-1].content)
    scoped = json.loads(model._seen[3][-1].content)
    expected = [item for item in histories if item["sales_deal_id"] == str(deal_id)]
    assert shared["crm_context"] == original["crm_context"]
    assert scoped["crm_context"]["previous_reports"] == expected
    assert scoped["crm_context"]["additional_context"] == [
        *[item for item in additional if item["sales_deal_id"] == str(deal_id)],
        other_context,
    ]
    assert scoped["crm_context"]["company"] == source.crm_context["company"]
    reviewer_source = json.loads(model._seen[5][-1].content)["source"]
    assert reviewer_source["crm_context"]["previous_reports"] == histories
    assert source.model_dump(mode="json") == original
    history_rule = "이전 약속의 이행 여부와 고객 입장·조건의 변경은 이번 원문에 근거가 있을 때만"
    for turn in (model._seen[0], model._seen[2], model._seen[5]):
        assert history_rule in str(turn[0].content)
    assert "관련 없는 과거 이력을 생략한 것은 누락 오류가 아니다" in model._seen[5][0].content


@pytest.mark.parametrize("scenario", ["skipped_review", "review_limit"])
def test_actual_graph_rejects_unreviewed_or_exhausted_output(scenario):
    good = draft()
    if scenario == "skipped_review":
        responses = [call("FreeformMeetingReports", **good)]
        error = "report_agent_unreviewed_output"
    else:
        good["unassigned_report"] = None
        responses = [call("review_report", draft=good) for _ in range(writer.MAX_REVIEWS + 1)]
        error = "report_agent_review_limit"
    with pytest.raises(LLMError, match=error):
        asyncio.run(writer.run(sample(), model=ScriptedModel(responses=responses)))


def test_accepted_draft_stops_before_any_parent_rewrite_or_final_model_call():
    changed = draft()
    changed["deal_reports"][0]["body"] = "A의 예산이 확정되었다."
    model = ScriptedModel(
        responses=[
            call("review_report", draft=draft()),
            call("ReportReview", issues=[]),
            call("FreeformMeetingReports", **changed),
        ]
    )
    result = asyncio.run(writer.run(sample(), model=model))
    assert result.model_dump(mode="json") == draft()
    assert len(model._seen) == 2  # 주 작성자 1회 + 검토자 1회. 세 번째 호출은 실행하지 않는다.
    writer.validate_reports(sample(), result)


@pytest.mark.parametrize("result_shape", ["dict", "none", "changed_dict"])
def test_final_graph_result_is_normalized_and_still_matches_reviewed_draft(
    monkeypatch,
    caplog,
    result_shape,
):
    original = writer.create_deep_agent

    class GraphResultAdapter:
        def __init__(self, graph):
            self.graph = graph

        async def ainvoke(self, *args, **kwargs):
            result = await self.graph.ainvoke(*args, **kwargs)
            body = result["structured_response"].model_dump(mode="json")
            if result_shape == "changed_dict":
                body["deal_reports"][0]["body"] = "A의 예산은 확정됐다."
            result["structured_response"] = None if result_shape == "none" else body
            return result

    monkeypatch.setattr(
        writer,
        "create_deep_agent",
        lambda *args, **kwargs: GraphResultAdapter(original(*args, **kwargs)),
    )
    model = ScriptedModel(
        responses=[call("review_report", draft=draft()), call("ReportReview", issues=[])]
    )
    if result_shape == "dict":
        assert asyncio.run(writer.run(sample(), model=model)).model_dump(mode="json") == draft()
    else:
        code = "report_agent_failed" if result_shape == "none" else "report_agent_unreviewed_output"
        with pytest.raises(LLMError, match=f"^{code}$"):
            asyncio.run(writer.run(sample(), model=model))
        errors = [
            json.loads(record.getMessage().removeprefix("agent_error "))
            for record in caplog.records
            if record.getMessage().startswith("agent_error ")
        ]
        final_error = next(
            item for item in errors if item["stage"] == "report_writing.final_validation"
        )
        assert final_error["exceptions"][0]["type"] == (
            "ValidationError" if result_shape == "none" else "LLMError"
        )
    assert len(model._seen) == 2


def test_virtual_files_are_read_only_assets_and_isolated_per_run():
    path = "/skills/sales-meeting-report/SKILL.md"
    model = ScriptedModel(
        responses=[
            call(
                "edit_file",
                file_path=path,
                old_string="sales-meeting-report",
                new_string="malicious",
            ),
            call("write_file", file_path="/scratch/note.md", content="temporary note"),
            call("read_file", file_path=path),
            call("read_file", file_path="/scratch/note.md"),
            call("read_file", file_path="/etc/passwd"),
            call("FreeformMeetingReports", **draft()),
        ]
    )
    with pytest.raises(LLMError, match="report_agent_unreviewed_output"):
        asyncio.run(writer.run(sample(), model=model))
    tool_messages = [m for m in model._seen[-1] if m.type == "tool"]
    assert "denied" in tool_messages[0].content.lower()
    assert "sales-meeting-report" in tool_messages[2].content
    assert "malicious" not in tool_messages[2].content
    assert "temporary note" in tool_messages[3].content
    assert "not found" in tool_messages[4].content.lower()

    other = ScriptedModel(
        responses=[
            call("read_file", file_path="/scratch/note.md"),
            call("FreeformMeetingReports", **draft()),
        ]
    )
    with pytest.raises(LLMError, match="report_agent_unreviewed_output"):
        asyncio.run(writer.run(sample(), model=other))
    assert "not found" in other._seen[-1][-1].content.lower()


def test_run_timeout_and_provider_error_do_not_leak(monkeypatch):
    class SlowModel(ScriptedModel):
        async def _agenerate(self, messages, **kwargs):
            await asyncio.sleep(1)
            return self._generate(messages, **kwargs)

    monkeypatch.setattr(writer, "RUN_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(LLMError, match="^report_agent_timeout$"):
        asyncio.run(writer.run(sample(), model=SlowModel(responses=[AIMessage(content="wait")])))

    class BrokenModel(ScriptedModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("provider secret and private transcript")

    monkeypatch.setattr(writer, "RUN_TIMEOUT_SECONDS", 180)
    with pytest.raises(LLMError, match="^report_agent_failed$") as error:
        asyncio.run(
            writer.run(sample(), model=BrokenModel(responses=[AIMessage(content="unused")]))
        )
    assert error.value.__suppress_context__


def test_provider_timeout_keeps_original_diagnostic_without_changing_public_error(caplog):
    class TimedOutModel(ScriptedModel):
        def _generate(self, *args, **kwargs):
            raise APITimeoutError(
                request=httpx.Request("POST", "https://private.invalid/secret-key")
            )

    run_id = str(uuid4())
    with agent_log_context(run_id=run_id):
        with pytest.raises(LLMError, match="^report_agent_failed$"):
            asyncio.run(
                writer.run(sample(), model=TimedOutModel(responses=[AIMessage(content="unused")]))
            )
    logs = [
        json.loads(record.getMessage().removeprefix("agent_error "))
        for record in caplog.records
        if record.name == "app.services.agent_logging"
        and record.getMessage().startswith("agent_error ")
    ]
    generated = next(item for item in logs if item["stage"] == "report_writing.generate")
    assert generated["run_id"] == run_id
    assert generated["exceptions"][0]["type"] == "APITimeoutError"
    assert generated["exceptions"][0]["frames"]
    assert "private.invalid" not in caplog.text and "secret-key" not in caplog.text


def test_budget_is_shared_with_subagent_and_reviewer(monkeypatch):
    # 주 에이전트 1회 + 작성자 1회 + 주 에이전트 1회까지 허용. 검토자부터 차단.
    monkeypatch.setattr(writer, "MAX_MODEL_CALLS", 3)
    model = ScriptedModel(
        responses=[
            call("task", subagent_type="general-purpose", description=f"딜 {DEAL_A} 초안"),
            AIMessage(content="작성 초안"),
            call("review_report", draft=draft()),
            call("ReportReview", issues=[]),
        ]
    )
    with pytest.raises(LLMError, match="^report_agent_model_call_limit$"):
        asyncio.run(writer.run(sample(), model=model))
    assert len(model._seen) == 3


def test_initialization_error_is_sanitized(monkeypatch, tmp_path):
    monkeypatch.setattr(writer, "SKILL_DIR", tmp_path / "missing-private-path")
    with pytest.raises(LLMError, match="^report_agent_failed$"):
        asyncio.run(
            writer.run(sample(), model=ScriptedModel(responses=[AIMessage(content="unused")]))
        )


def test_sdk_automatic_summary_also_consumes_shared_budget(monkeypatch):
    import deepagents.graph
    from deepagents.middleware.summarization import SummarizationMiddleware

    # 실제 SDK 요약만 짧은 대화에서도 발생시키고, 실행 경로는 그대로 둔다.
    monkeypatch.setattr(
        deepagents.graph,
        "create_summarization_middleware",
        lambda model, backend: SummarizationMiddleware(
            model, backend=backend, trigger=("messages", 4), keep=("messages", 2)
        ),
    )
    monkeypatch.setattr(writer, "MAX_MODEL_CALLS", 3)
    model = ScriptedModel(
        responses=[
            call("read_meeting_evidence"),
            call("read_meeting_evidence"),
            AIMessage(content="근거 조회 완료. 보고서를 작성해야 한다."),
            call("FreeformMeetingReports", **draft()),
        ]
    )
    with pytest.raises(LLMError, match="^report_agent_model_call_limit$"):
        asyncio.run(writer.run(sample(), model=model))
    assert len(model._seen) == 3
    assert "Context Extraction Assistant" in str(model._seen[-1])


def test_structural_feedback_can_repair_after_three_reviews_and_accept_source_absence(caplog):
    bad = draft()
    bad["unassigned_report"] = None
    bad["deal_reports"][0]["evidence_ids"] = []
    model = ScriptedModel(
        responses=[
            *[call("review_report", draft=bad) for _ in range(4)],
            call("review_report", draft=draft()),
            call("ReportReview", issues=[]),
            call("FreeformMeetingReports", **draft()),
        ]
    )
    result = asyncio.run(writer.run(sample(), model=model))
    assert result.model_dump(mode="json") == draft()
    feedback = json.loads(
        next(
            message.content
            for message in model._seen[1]
            if message.type == "tool" and message.name == "review_report"
        )
    )
    assert feedback["review_kind"] == "structural"
    assert feedback["remaining_reviews"] == 9
    assert {issue["code"] for issue in feedback["issues"]} >= {
        "report_deal_evidence_mismatch",
        "report_unassigned_evidence_missing",
    }
    unassigned = next(
        issue
        for issue in feedback["issues"]
        if issue["code"] == "report_unassigned_evidence_missing"
    )
    assert unassigned["missing_ids"] == ["S0003", "S0004"]
    assert unassigned["path"] == "unassigned_report.evidence_ids"
    assert unassigned["required_raw_quotes"][0]["text"] == "그거 다시 보내달래."
    assert "정보가 없거나 불확실한데 그 상태를 정확히 남겼다면" in str(model._seen[5])
    progress = [
        json.loads(record.getMessage().removeprefix("agent_progress "))
        for record in caplog.records
        if record.getMessage().startswith("agent_progress ")
    ]
    accepted = next(item for item in progress if item.get("reason_code") == "review_passed")
    assert accepted["review_attempt"] == accepted["validation_attempt"] == 5
    assert accepted["semantic_review_count"] == 1
    summary = next(item for item in progress if item["stage"] == "report_writing.summary")
    assert summary["call_count"] == 6
    assert summary["review_attempt"] == 5 and summary["semantic_review_count"] == 1
    assert summary["timeout_seconds"] == 900 and summary["outcome"] == "completed"
    assert "그거 다시 보내달래" not in caplog.text


def test_partial_tool_preview_is_filtered_and_routed_by_identity_with_monotonic_revisions(
    monkeypatch,
):
    events = []
    ticks = count()
    monkeypatch.setattr(writer, "perf_counter", lambda: next(ticks) * 0.1)
    monkeypatch.setattr(
        writer, "publish_progress", lambda stage=None, **kwargs: events.append(kwargs)
    )
    budget = writer._RunBudget([DEAL_A, DEAL_B])

    async def emit(run_id, name, value):
        await budget.on_llm_new_token(
            "SECRET reasoning",
            run_id=run_id,
            chunk=ChatGenerationChunk(message=AIMessageChunk(content="SECRET reasoning")),
        )
        args = json.dumps(value, ensure_ascii=True)
        for index in range(0, len(args), 11):
            await budget.on_llm_new_token(
                "",
                run_id=run_id,
                chunk=ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        tool_call_chunks=[
                            {
                                "index": 2,
                                "name": name if index == 0 else None,
                                "id": str(uuid4()) if index == 0 else None,
                                "args": args[index : index + 11],
                            }
                        ],
                    ),
                ),
            )
        budget._finish(run_id)

    async def exercise():
        reordered = {
            "deal_reports": [
                {"sales_deal_id": str(DEAL_B), "body": 'B 초안\n"인용"'},
                {"sales_deal_id": str(UUID(int=99)), "body": "선택 안 된 딜 누출"},
                {"body": "ID 없는 누출"},
                {"sales_deal_id": str(DEAL_A), "body": "A 초안"},
            ],
            "unassigned_report": {"body": "딜 미지정 원문"},
        }
        await emit(uuid4(), "task", {"draft": reordered})
        await emit(uuid4(), "ReportReview", {"issues": ["SECRET reviewer"]})
        assert events == []
        await emit(uuid4(), "review_report", {"draft": reordered})
        await emit(
            uuid4(),
            "FreeformMeetingReports",
            {
                "deal_reports": [{"sales_deal_id": str(DEAL_B), "body": "B 수정 초안"}],
                "unassigned_report": None,
            },
        )

    asyncio.run(exercise())
    values = [event["preview"] for event in events]
    assert all(value["sales_deal_id"] in {str(DEAL_A), str(DEAL_B), None} for value in values)
    assert [value["revision"] for value in values] == list(range(1, len(values) + 1))
    assert any(
        value["body"] == 'B 초안\n"인용"' and value["sales_deal_id"] == str(DEAL_B)
        for value in values
    )
    assert any(value["body"] == "B 수정 초안" for value in values)
    assert values[-1]["section"] == "unassigned" and values[-1]["body"] == ""
    assert "SECRET" not in json.dumps(values) and "누출" not in json.dumps(
        values, ensure_ascii=False
    )


def test_model_call_telemetry_correlates_parallel_calls_and_failures_without_body(monkeypatch):
    logs = []
    monkeypatch.setattr(
        writer, "log_agent_event", lambda stage, **fields: logs.append({"stage": stage, **fields})
    )
    budget = writer._RunBudget()
    first, second = uuid4(), uuid4()

    async def exercise():
        await budget.on_chat_model_start({}, [["SECRET input"]], run_id=first)
        await budget.on_chat_model_start({}, [], run_id=second)
        await budget.on_llm_error(RuntimeError("SECRET error"), run_id=second)
        await budget.on_llm_end(
            LLMResult(
                generations=[
                    [
                        ChatGeneration(
                            message=AIMessage(
                                content="SECRET output",
                                usage_metadata={
                                    "input_tokens": 3,
                                    "output_tokens": 2,
                                    "total_tokens": 5,
                                },
                            )
                        )
                    ]
                ]
            ),
            run_id=first,
        )

    asyncio.run(exercise())
    assert [item["outcome"] for item in logs] == ["started", "started", "failed", "completed"]
    assert logs[2]["model_call_id"] == str(second) and logs[2]["call_count"] == 2
    assert logs[3]["model_call_id"] == str(first) and logs[3]["call_count"] == 1
    assert logs[3]["total_tokens"] == 5
    assert all(item["elapsed_ms"] >= 0 for item in logs[2:])
    assert all(item["timeout_seconds"] >= 180 for item in logs)
    assert not budget._started and not budget._chunks
    assert "SECRET" not in json.dumps(logs)


@pytest.mark.parametrize("endpoint", ["responses", "chat/completions"])
def test_real_streaming_sdk_round_trip_without_network(monkeypatch, caplog, endpoint):
    from pydantic import SecretStr

    good = draft()
    calls = [
        ("read_meeting_evidence", {}),
        ("review_report", {"draft": good}),
        ("ReportReview", {"issues": []}),
        ("FreeformMeetingReports", good),
    ]
    requests = []
    previews = []
    completed = set()
    ticks = count()
    monkeypatch.setattr(writer, "perf_counter", lambda: next(ticks) * 0.1)
    monkeypatch.setattr(
        writer,
        "publish_progress",
        lambda stage=None, **kwargs: previews.append(
            {"stage": stage, **kwargs, "response_finished": len(requests) - 1 in completed}
        ),
    )

    class EventStream(httpx.AsyncByteStream):
        def __init__(self, index, events):
            self.index, self.events = index, events

        async def __aiter__(self):
            for event in self.events:
                if event.get("type") == "response.completed" or event.get("usage"):
                    completed.add(self.index)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()

    def respond(request):
        requests.append(json.loads(request.content))
        assert str(request.url) == f"https://provider.invalid/v1/{endpoint}"
        assert requests[-1]["stream"] is True
        index = len(requests) - 1
        name, args = calls[index]
        arguments = json.dumps(args, ensure_ascii=False)
        fragments = [arguments[i : i + 17] for i in range(0, len(arguments), 17)]
        if endpoint == "responses":
            item = {
                "type": "function_call",
                "id": f"fc_{index}",
                "call_id": f"call_{index}",
                "name": name,
                "arguments": arguments,
                "status": "completed",
            }
            response = {
                "id": f"resp_{index}",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "synthetic-model",
                "output": [item],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 8,
                    "total_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0},
                },
            }
            events = [
                {"type": "response.created", "response": {**response, "output": []}},
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {**item, "arguments": "", "status": "in_progress"},
                },
                *[
                    {
                        "type": "response.function_call_arguments.delta",
                        "output_index": 0,
                        "item_id": item["id"],
                        "delta": fragment,
                    }
                    for fragment in fragments
                ],
                {"type": "response.completed", "response": response},
            ]
        else:
            base = {
                "id": f"chatcmpl_{index}",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "synthetic-model",
            }
            events = [
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": f"call_{index}",
                                        "type": "function",
                                        "function": {"name": name, "arguments": ""},
                                    },
                                ],
                            },
                        }
                    ],
                },
                *[
                    {
                        **base,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [
                                        {"index": 0, "function": {"arguments": fragment}},
                                    ]
                                },
                            }
                        ],
                    }
                    for fragment in fragments
                ],
                {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
                {
                    **base,
                    "choices": [],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "total_tokens": 20,
                    },
                },
            ]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=EventStream(index, events),
        )

    monkeypatch.setattr(writer.settings, "llm_api_url", f"https://provider.invalid/v1/{endpoint}")
    monkeypatch.setattr(writer.settings, "llm_api_key", SecretStr("synthetic-test-key"))
    monkeypatch.setattr(writer.settings, "llm_model", "synthetic-model")
    transport = httpx.MockTransport(respond)
    original = writer.ChatOpenAI

    async def exercise():
        async with httpx.AsyncClient(transport=transport) as client:
            monkeypatch.setattr(
                writer,
                "ChatOpenAI",
                lambda **kwargs: original(
                    **kwargs,
                    http_async_client=client,
                ),
            )
            return await writer.run(sample())

    result = asyncio.run(exercise())
    assert result.model_dump(mode="json") == good
    assert len(requests) == 3
    assert requests[0]["model"] == "synthetic-model"
    assert (
        requests[0]["max_output_tokens" if endpoint == "responses" else "max_completion_tokens"]
        == 12_000
    )
    if endpoint == "responses":
        assert any(item.get("type") == "function_call_output" for item in requests[1]["input"])
    partial = [item for item in previews if item.get("preview") and not item["response_finished"]]
    assert any(item["preview"]["body"] == "A는 보안 승인을 받" for item in partial) or any(
        0 < len(item["preview"]["body"]) < len(good["deal_reports"][0]["body"])
        and item["preview"]["sales_deal_id"] == str(DEAL_A)
        for item in partial
    )
    assert previews[-1]["stage"] == "report_complete"
    progress = [
        json.loads(record.getMessage().removeprefix("agent_progress "))
        for record in caplog.records
        if record.getMessage().startswith("agent_progress ")
    ]
    calls_finished = [
        item
        for item in progress
        if item["stage"] == "report_writing.model" and item.get("outcome") == "completed"
    ]
    assert len(calls_finished) == 3
    assert all(
        item["input_tokens"] == 12
        and item["output_tokens"] == 8
        and item["total_tokens"] == 20
        and item["elapsed_ms"] >= 0
        for item in calls_finished
    )
