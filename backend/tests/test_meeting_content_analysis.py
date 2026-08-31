import asyncio
import json
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from pydantic import PrivateAttr, ValidationError

from app.agents import meeting_content_analysis
from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    SegmentApplicability,
    SegmentAssignment,
)
from app.services.llm import LLMError


def _deal(deal_id, *, title="LP1000 공급"):
    return meeting_content_analysis.DealGroundingContext(
        sales_deal_id=deal_id,
        deal_no="DL-001",
        title=title,
        description="LP1000 신규 공급 검토",
        product_names=["LP1000"],
        deal_type_name="신규 공급",
        pipeline_stage_name="제안",
    )


def test_segment_transcript_preserves_exact_source_offsets():
    transcript = '첫 문장.  둘째 문장!\n\n마지막 "문장"'

    segments = meeting_content_analysis.segment_transcript(transcript)

    assert [segment.text for segment in segments] == [
        "첫 문장.",
        "둘째 문장!",
        '마지막 "문장"',
    ]
    assert all(transcript[item.start : item.end] == item.text for item in segments)
    assert [item.segment_id for item in segments] == ["S0001", "S0002", "S0003"]


def test_input_snapshot_requires_context_for_every_selected_deal():
    deal_a, deal_b = uuid4(), uuid4()
    snapshot = meeting_content_analysis.input_snapshot(
        "LP1000 견적을 요청했다.",
        [_deal(deal_a), _deal(deal_b, title="유지보수 계약")],
    )

    assert snapshot["source"]["selected_deal_ids"] == [str(deal_a), str(deal_b)]
    assert snapshot["deals"][0]["product_names"] == ["LP1000"]

    snapshot["deals"].pop()
    with pytest.raises(ValidationError, match="grounding_deals_mismatch"):
        meeting_content_analysis.MeetingContentAgentInput.model_validate(snapshot)


@pytest.mark.anyio
async def test_run_returns_a_validated_evidence_ledger(monkeypatch):
    deal_id = uuid4()
    snapshot = meeting_content_analysis.input_snapshot(
        "LP1000 견적을 요청했다.",
        [_deal(deal_id)],
    )
    captured = {}

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return MeetingContentAnalysisOutput(
            assignments=[
                SegmentAssignment(
                    segment_id="S0001",
                    applicability=SegmentApplicability(scope="deal", deal_ids=[deal_id]),
                )
            ]
        )

    monkeypatch.setattr(meeting_content_analysis, "generate_structured", fake_generate_structured)

    ledger = await meeting_content_analysis.run(snapshot)

    assert ledger.items[0].applicability.deal_ids == [deal_id]
    assert captured["schema"] is MeetingContentAnalysisOutput
    assert captured["schema_name"] == "meeting_content_assignments"
    assert "LP1000 견적을 요청했다." in captured["input_text"]
    assert str(deal_id) in captured["input_text"]


@pytest.mark.anyio
async def test_run_retries_once_when_the_llm_omits_a_segment(monkeypatch):
    deal_id = uuid4()
    snapshot = meeting_content_analysis.input_snapshot(
        "첫 문장. 둘째 문장.",
        [_deal(deal_id)],
    )
    calls = []

    async def fake_generate_structured(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return MeetingContentAnalysisOutput(
                assignments=[
                    SegmentAssignment(
                        segment_id="S0001",
                        applicability=SegmentApplicability(scope="meeting_context"),
                    )
                ]
            )
        return MeetingContentAnalysisOutput(
            assignments=[
                SegmentAssignment(
                    segment_id="S0001",
                    applicability=SegmentApplicability(scope="meeting_context"),
                ),
                SegmentAssignment(
                    segment_id="S0002",
                    applicability=SegmentApplicability(scope="deal", deal_ids=[deal_id]),
                ),
            ]
        )

    monkeypatch.setattr(meeting_content_analysis, "generate_structured", fake_generate_structured)

    ledger = await meeting_content_analysis.run(snapshot)

    assert len(calls) == 2
    assert "모든 입력 segment_id" in calls[1]["input_text"]
    assert len(ledger.items) == 2


@pytest.mark.anyio
async def test_unresolved_is_a_valid_result_and_is_not_retried(monkeypatch):
    deal_id = uuid4()
    snapshot = meeting_content_analysis.input_snapshot(
        "가격을 다시 검토하기로 했다.",
        [_deal(deal_id)],
    )
    call_count = 0

    async def fake_generate_structured(**kwargs):
        nonlocal call_count
        call_count += 1
        return MeetingContentAnalysisOutput(
            assignments=[
                SegmentAssignment(
                    segment_id="S0001",
                    applicability=SegmentApplicability(scope="unresolved"),
                )
            ]
        )

    monkeypatch.setattr(meeting_content_analysis, "generate_structured", fake_generate_structured)

    ledger = await meeting_content_analysis.run(snapshot)

    assert call_count == 1
    assert ledger.items[0].applicability.scope == "unresolved"


class ScriptedGroundingModel(FakeMessagesListChatModel):
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


def _call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(uuid4())}])


def _assignment(segment_id, scope, deal_id=None):
    return {
        "segment_id": segment_id,
        "applicability": {"scope": scope, "deal_ids": [str(deal_id)] if deal_id else []},
    }


def _grounding_case():
    deal_a, deal_b = uuid4(), uuid4()
    snapshot = meeting_content_analysis.input_snapshot(
        "LP1000 가격을 문의했다. 지난번 보여준 작은 제품도 자료 요청.",
        [_deal(deal_a), _deal(deal_b, title="휴대형 공급")],
        crm_context={"company": {"name": "합성회사"}, "unrelated": "노출하지 않는 값"},
    )
    initial = [
        _assignment("S0001", "deal", deal_a),
        _assignment("S0002", "unresolved"),
    ]
    return snapshot, deal_a, deal_b, initial


@pytest.mark.anyio
async def test_real_tool_loop_refines_only_unresolved_and_preserves_source():
    snapshot, deal_a, deal_b, initial = _grounding_case()
    looked_up = []

    async def lookup(kind, deal_id):
        looked_up.append((kind, deal_id))
        return {"items": [{"product_name": "휴대형", "prior_demo": "작은 제품"}]}

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            _call("product_details", sales_deal_id=str(deal_b)),
            _call(
                "MeetingContentAnalysisOutput", assignments=[_assignment("S0002", "deal", deal_b)]
            ),
        ]
    )
    result = await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)

    assert looked_up == [("product_details", deal_b)]
    assert result.items[0].applicability.deal_ids == [deal_a]
    assert result.items[1].applicability.deal_ids == [deal_b]
    assert [item.segment.model_dump(mode="json") for item in result.items] == snapshot["source"][
        "segments"
    ]
    assert "합성회사" in str(model._seen[0])
    assert "노출하지 않는 값" not in str(model._seen)
    assert set.union(*model._tool_sets) == {
        "MeetingContentAnalysisOutput",
        "trade_history",
        "previous_reports",
        "product_details",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "lookup_result", [None, {}, {"items": [], "count": 0}, {"error": "not_found"}]
)
async def test_no_new_evidence_keeps_unresolved_even_if_model_guesses(lookup_result):
    snapshot, _, deal_b, initial = _grounding_case()
    calls = []

    async def lookup(kind, deal_id):
        calls.append((kind, deal_id))
        return lookup_result

    responses = [_call("MeetingContentAnalysisOutput", assignments=initial)]
    if lookup_result is not None:
        responses.append(_call("previous_reports", sales_deal_id=str(deal_b)))
    responses.append(
        _call("MeetingContentAnalysisOutput", assignments=[_assignment("S0002", "deal", deal_b)])
    )
    result = await meeting_content_analysis.run(
        snapshot, lookup=lookup, model=ScriptedGroundingModel(responses=responses)
    )
    assert result.items[1].applicability.scope == "unresolved"
    assert len(calls) == (0 if lookup_result is None else 1)


@pytest.mark.anyio
async def test_no_unresolved_skips_the_lookup_agent():
    snapshot, _, deal_b, initial = _grounding_case()
    initial[1] = _assignment("S0002", "deal", deal_b)

    async def lookup(*args):
        pytest.fail("이미 귀속된 원문에는 추가 조회하지 않는다")

    model = ScriptedGroundingModel(
        responses=[_call("MeetingContentAnalysisOutput", assignments=initial)]
    )
    result = await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)
    assert result.items[1].applicability.deal_ids == [deal_b]
    assert len(model._seen) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("segment_id", ["S0001", "S9999"])
async def test_refinement_rejects_resolved_changes_or_new_segments(segment_id):
    snapshot, _, deal_b, initial = _grounding_case()

    async def lookup(*args):
        return {"items": [{"name": "휴대형"}]}

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            _call("product_details", sales_deal_id=str(deal_b)),
            _call(
                "MeetingContentAnalysisOutput",
                assignments=[_assignment(segment_id, "deal", deal_b)],
            ),
        ]
    )
    with pytest.raises(LLMError, match="^meeting_content_refinement_segments_mismatch$"):
        await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)


@pytest.mark.anyio
async def test_tool_target_and_global_lookup_limit_are_enforced(monkeypatch):
    snapshot, deal_a, deal_b, initial = _grounding_case()
    monkeypatch.setattr(meeting_content_analysis, "MAX_LOOKUPS", 3)
    calls = []

    async def lookup(kind, deal_id):
        calls.append((kind, deal_id))
        return {"items": [{"name": "휴대형"}]}

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            _call("previous_reports", sales_deal_id=str(uuid4())),
            _call("product_details", sales_deal_id=str(deal_b)),
            _call("previous_reports", sales_deal_id=str(deal_b)),
            _call("trade_history", sales_deal_id=str(deal_b)),
            _call("product_details", sales_deal_id=str(deal_a)),
            _call("MeetingContentAnalysisOutput", assignments=[_assignment("S0002", "unresolved")]),
        ]
    )
    result = await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)
    assert len(calls) == 3
    assert all(deal_id == deal_b for _, deal_id in calls)
    assert "deal_not_selected" in str(model._seen)
    assert "meeting_content_lookup_limit" in str(model._seen)
    assert result.items[1].applicability.scope == "unresolved"


@pytest.mark.anyio
async def test_refinement_cannot_return_an_unselected_deal():
    snapshot, _, deal_b, initial = _grounding_case()

    async def lookup(*args):
        return {"items": [{"name": "휴대형"}]}

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            _call("product_details", sales_deal_id=str(deal_b)),
            _call(
                "MeetingContentAnalysisOutput",
                assignments=[_assignment("S0002", "deal", uuid4())],
            ),
        ]
    )
    with pytest.raises(LLMError, match="^meeting_content_refinement_deal_not_selected$"):
        await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)


@pytest.mark.anyio
async def test_model_budget_includes_initial_classification():
    snapshot, _, deal_b, initial = _grounding_case()

    async def lookup(*args):
        return {}

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            *[
                _call("product_details", sales_deal_id=str(deal_b))
                for _ in range(meeting_content_analysis.MAX_MODEL_CALLS)
            ],
        ]
    )
    with pytest.raises(LLMError, match="^meeting_content_model_call_limit$"):
        await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)
    assert len(model._seen) == meeting_content_analysis.MAX_MODEL_CALLS


@pytest.mark.anyio
async def test_repeated_empty_lookup_runs_once_and_keeps_unresolved():
    snapshot, _, deal_b, initial = _grounding_case()
    calls = []

    async def lookup(kind, deal_id):
        calls.append((kind, deal_id))
        await asyncio.sleep(0)
        return {"items": []}

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "previous_reports",
                        "args": {"sales_deal_id": str(deal_b)},
                        "id": str(uuid4()),
                    }
                    for _ in range(2)
                ],
            ),
            _call("previous_reports", sales_deal_id=str(deal_b)),
            _call("MeetingContentAnalysisOutput", assignments=[_assignment("S0002", "unresolved")]),
        ]
    )

    ledger = await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)

    assert calls == [("previous_reports", deal_b)]
    assert ledger.items[1].applicability.scope == "unresolved"
    tool_results = [
        json.loads(message.content)
        for message in model._seen[-1]
        if message.type == "tool" and message.name == "previous_reports"
    ]
    assert len(tool_results) == 3
    assert all(result["no_new_information"] is True for result in tool_results)


@pytest.mark.anyio
async def test_transient_lookup_failure_is_not_cached():
    snapshot, _, deal_b, initial = _grounding_case()
    calls = 0

    async def lookup(kind, deal_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("private transient failure")
        return {"items": [{"name": "휴대형"}]}

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            _call("product_details", sales_deal_id=str(deal_b)),
            _call("product_details", sales_deal_id=str(deal_b)),
            _call(
                "MeetingContentAnalysisOutput", assignments=[_assignment("S0002", "deal", deal_b)]
            ),
        ]
    )
    ledger = await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)
    assert calls == 2
    assert ledger.items[1].applicability.deal_ids == [deal_b]
    assert "private transient failure" not in str(model._seen)


@pytest.mark.anyio
async def test_sdk_calls_log_actual_usage_and_safe_start_finish_progress(monkeypatch, caplog):
    snapshot, _, deal_b, initial = _grounding_case()
    progress = []
    monkeypatch.setattr(
        meeting_content_analysis,
        "publish_progress",
        lambda stage=None, **metrics: progress.append((stage, metrics)),
    )

    async def lookup(kind, deal_id):
        return {"items": [{"name": "휴대형"}]}

    responses = [
        _call("MeetingContentAnalysisOutput", assignments=initial),
        _call("product_details", sales_deal_id=str(deal_b)),
        _call("MeetingContentAnalysisOutput", assignments=[_assignment("S0002", "deal", deal_b)]),
    ]
    for message in responses:
        message.usage_metadata = {"input_tokens": 20, "output_tokens": 10, "total_tokens": 30}
    await meeting_content_analysis.run(
        snapshot, lookup=lookup, model=ScriptedGroundingModel(responses=responses)
    )

    events = [
        json.loads(record.message.removeprefix("agent_progress "))
        for record in caplog.records
        if record.message.startswith("agent_progress ")
    ]
    completed = [
        event for event in events if event["stage"] == "meeting_content.model_call_completed"
    ]
    assert [event["call_count"] for event in completed] == [1, 2, 3]
    assert all(event["input_tokens"] == 20 and event["total_tokens"] == 30 for event in completed)
    assert all(event["elapsed_ms"] >= 0 for event in completed)
    assert len(progress) == 2
    assert [stage for stage, _ in progress] == ["content_analysis", "content_analysis"]
    assert progress[0][1]["call_count"] == 0
    assert progress[1][1]["call_count"] == 3
    assert progress[1][1]["call_limit"] == 24
    assert "합성회사" not in caplog.text
    assert "지난번 보여준" not in caplog.text


@pytest.mark.anyio
async def test_sdk_budget_uses_top_level_usage_once_and_counts_no_blocked_call(monkeypatch):
    events = []
    monkeypatch.setattr(meeting_content_analysis, "MAX_MODEL_CALLS", 1)
    monkeypatch.setattr(
        meeting_content_analysis,
        "log_agent_event",
        lambda stage, **fields: events.append((stage, fields)),
    )
    budget = meeting_content_analysis._ModelBudget()
    call_id = uuid4()
    await budget.on_chat_model_start({}, [[AIMessage(content="private prompt")]], run_id=call_id)
    with pytest.raises(LLMError, match="meeting_content_model_call_limit"):
        await budget.on_chat_model_start({}, [], run_id=uuid4())
    await budget.on_llm_end(
        LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="private output",
                            usage_metadata={
                                "input_tokens": 100,
                                "output_tokens": 50,
                                "total_tokens": 150,
                            },
                        )
                    )
                ]
            ],
            llm_output={
                "token_usage": {"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}
            },
        ),
        run_id=call_id,
    )
    assert budget.calls == 1
    assert len(events) == 2
    assert events[-1][1]["total_tokens"] == 23
    assert "private" not in str(events)


@pytest.mark.anyio
async def test_timeout_and_tool_errors_do_not_expose_private_values(monkeypatch):
    snapshot, _, deal_b, initial = _grounding_case()

    async def lookup(*args):
        raise RuntimeError("private CRM information")

    model = ScriptedGroundingModel(
        responses=[
            _call("MeetingContentAnalysisOutput", assignments=initial),
            _call("product_details", sales_deal_id=str(deal_b)),
            _call("MeetingContentAnalysisOutput", assignments=[_assignment("S0002", "unresolved")]),
        ]
    )
    result = await meeting_content_analysis.run(snapshot, lookup=lookup, model=model)
    assert result.items[1].applicability.scope == "unresolved"
    assert "private CRM information" not in str(model._seen)
    assert "crm_lookup_failed" in str(model._seen)

    async def slow_generate(**kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(meeting_content_analysis, "RUN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(meeting_content_analysis, "generate_structured", slow_generate)
    with pytest.raises(LLMError, match="^meeting_content_timeout$"):
        await meeting_content_analysis.run(snapshot)
