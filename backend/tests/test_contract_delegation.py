"""Synthetic tool-loop decisions, bounded retries and sanitized output boundaries."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from app.agents import contract_delegation, schedule_management
from app.schemas.schedule_delegation import SafeScheduleCandidate, ScheduleRequest, validate_search
from app.services.contract_schedule_delegation import DelegationRuntime, check_retry
from app.services.contract_tracing import safe_fields
from app.services.llm import LLMError


def request(**changes):
    return {
        "preferred_starts_at": "2099-01-05T09:00:00+09:00",
        "preferred_ends_at": "2099-01-09T18:00:00+09:00",
        "duration_minutes": 60,
        "reason": "합성 계약 협의",
        **changes,
    }


def test_strict_request_and_normalized_identity():
    original = ScheduleRequest(**request())
    equivalent = ScheduleRequest(
        **request(preferred_starts_at="2099-01-05T00:00:00Z", reason="문구만 변경")
    )
    assert original.key() == equivalent.key()
    for invalid in [
        {"duration_minutes": 4},
        {"duration_minutes": 481},
        {"duration_minutes": "60"},
        {"preferred_starts_at": "2099-01-05T09:00:00"},
        {"preferred_ends_at": "2099-01-05T09:30:00+09:00"},
        {"team_id": str(uuid4())},
    ]:
        with pytest.raises(ValidationError):
            ScheduleRequest(**request(**invalid))


def test_deadlines_and_research_require_explicit_bounds():
    first = {"request": request(), "result": {"status": "no_candidates"}}
    wider = ScheduleRequest(
        **request(
            preferred_ends_at="2099-01-12T18:00:00+09:00",
            reason="첫 검색 후보 없음, 허용 기간 내 확대",
        )
    )
    with pytest.raises(ValueError, match="boundary_unconfirmed"):
        check_retry(wider, [first], {})
    constraints = {"not_after": "2099-01-12T18:00:00+09:00"}
    check_retry(wider, [first], constraints)
    validate_search(wider, datetime(2099, 1, 1, tzinfo=UTC), constraints)
    with pytest.raises(ValueError, match="constraint_violation"):
        validate_search(
            wider, datetime(2099, 1, 1, tzinfo=UTC), {"not_after": "2099-01-10T18:00:00+09:00"}
        )
    with pytest.raises(ValueError, match="search_limit"):
        check_retry(wider, [first, first], constraints)
    with pytest.raises(ValueError, match="duration_change"):
        check_retry(wider.model_copy(update={"duration_minutes": 30}), [first], constraints)
    for status in ("failed", "candidates_found"):
        with pytest.raises(ValueError, match="requires_no_candidates"):
            check_retry(wider, [{**first, "result": {"status": status}}], constraints)


def test_candidate_and_trace_allowlists_exclude_sensitive_text():
    candidate = SafeScheduleCandidate(
        candidate_id="id",
        starts_at="2099-01-05T09:00:00Z",
        ends_at="2099-01-05T10:00:00Z",
        priority=1,
        title="개인 진료",
        reason="환자 연락처",
    )
    assert "title" not in candidate.model_dump()
    assert "reason" not in candidate.model_dump()
    assert safe_fields(
        {
            "status": "failed",
            "reason_code": "schedule_execution_failed",
            "error": "secret",
            "prompt": "고객 원문",
            "nested": {"secret": 1},
        }
    ) == {"status": "failed", "reason_code": "schedule_execution_failed"}


class MemoryRuntime:
    """No model/network/DB: use production durable-journal mutations with an in-memory store."""

    reserve_model = DelegationRuntime.reserve_model
    record_calls = DelegationRuntime.record_calls
    record_result = DelegationRuntime.record_result
    clear_pending = DelegationRuntime.clear_pending
    record_invalid_turn = DelegationRuntime.record_invalid_turn

    def __init__(self, results=()):
        self.state = {
            "model_calls": 0,
            "tool_requests": 0,
            "history": [],
            "pending": [],
            "constraints": {},
            "requests": {},
            "searches": [],
        }
        self.results = list(results)
        self.requested = []

    async def restore(self):
        return deepcopy(self.state)

    async def _mutate(self, operation):
        return operation(self.state)

    async def request(self, call_key, args):
        self.requested.append(args)
        return self.results.pop(0)

    async def finish(self, output):
        self.state["final"] = output.model_dump(mode="json")
        return output


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def bind_tools(self, tools, **kwargs):
        assert [t["function"]["name"] for t in tools] == [
            "request_schedule_candidates",
            "finish_proposal",
        ]
        return self

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return next(self.responses)


def call(name, args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": str(uuid4())}])


@pytest.mark.parametrize(
    "statuses",
    [
        [],
        ["candidates_found"],
        ["no_candidates", "candidates_found"],
        ["no_candidates", "no_candidates"],
        ["failed"],
    ],
)
def test_decision_sequences(monkeypatch, statuses):
    responses = [
        call("request_schedule_candidates", request(reason=f"검증 근거 {i}"))
        for i in range(len(statuses))
    ]
    responses.append(call("finish_proposal", {"missing_information": ["테스트 종료"]}))
    model = Model(responses)
    monkeypatch.setattr(contract_delegation, "configured_chat_model", lambda: model)
    runtime = MemoryRuntime([{"status": s, "reason_code": s} for s in statuses])
    output = asyncio.run(contract_delegation.run({}, runtime))
    assert len(runtime.requested) == len(statuses)
    assert len(model.messages) == len(statuses) + 1
    assert output.missing_information == ["테스트 종료"]
    if statuses:
        assert any(getattr(m, "type", "") == "tool" for m in model.messages[-1])


def test_invalid_model_turns_stop_at_durable_limit(monkeypatch):
    model = Model([AIMessage(content="도구 없는 응답")] * 6)
    monkeypatch.setattr(contract_delegation, "configured_chat_model", lambda: model)
    runtime = MemoryRuntime()
    with pytest.raises(LLMError, match="model_limit"):
        asyncio.run(contract_delegation.run({}, runtime))
    assert len(model.messages) == 5
    with pytest.raises(LLMError, match="model_limit"):
        asyncio.run(contract_delegation.run({}, runtime))
    assert len(model.messages) == 5  # worker retry does not reset the budget


def test_pending_call_is_replayed_without_another_model_decision(monkeypatch):
    runtime = MemoryRuntime([{"status": "no_candidates"}])
    runtime.state["model_calls"] = 1
    pending = call("request_schedule_candidates", request()).tool_calls
    asyncio.run(runtime.record_calls(pending))
    model = Model([call("finish_proposal", {})])
    monkeypatch.setattr(contract_delegation, "configured_chat_model", lambda: model)
    asyncio.run(contract_delegation.run({}, runtime))
    assert len(runtime.requested) == 1
    assert len(model.messages) == 1
    assert runtime.state["model_calls"] == 2


def test_strict_postprocessing_removes_private_text_and_exact_time_overflow(monkeypatch):
    now = datetime(2099, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(schedule_management, "_now", lambda: now)
    # Find a weekday independent of the synthetic year.
    start = now + timedelta(days=1)
    while start.weekday() >= 5:
        start += timedelta(days=1)
    start = start.replace(hour=1)  # 10:00 KST
    end = start + timedelta(hours=1)
    snapshot = {
        "strict_delegation": True,
        "preferred_starts_at": start.isoformat(),
        "preferred_ends_at": end.isoformat(),
        "duration_minutes": 60,
    }
    candidate = schedule_management.ScheduleCandidate(
        candidate_id="private-person",
        title="민감한 일정",
        reason="개인 연락처",
        starts_at=start.isoformat(),
        ends_at=end.isoformat(),
        priority=1,
    )
    out = schedule_management._postprocess(
        schedule_management.ScheduleManagementOutput(schedule_candidates=[candidate]), snapshot
    )
    assert len(out.schedule_candidates) == 1
    assert out.schedule_candidates[0].title == "미팅"
    assert out.schedule_candidates[0].reason == ""
    assert out.schedule_candidates[0].candidate_id != "private-person"
    snapshot["preferred_ends_at"] = (end - timedelta(minutes=1)).isoformat()
    assert not schedule_management._postprocess(
        schedule_management.ScheduleManagementOutput(schedule_candidates=[candidate]), snapshot
    ).schedule_candidates


def test_expired_or_reassigned_parent_lease_rejects_writes():
    class Session:
        async def execute(self, stmt):
            return SimpleNamespace(scalar_one=lambda: parent)

    parent = SimpleNamespace(
        status_code="running",
        lease_owner="new",
        lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )
    runtime = DelegationRuntime(SimpleNamespace(id=uuid4()), "old", None)
    with pytest.raises(RuntimeError, match="lease_lost"):
        asyncio.run(runtime._active(Session()))
    parent.lease_owner = "old"
    parent.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(RuntimeError, match="lease_lost"):
        asyncio.run(runtime._active(Session()))
