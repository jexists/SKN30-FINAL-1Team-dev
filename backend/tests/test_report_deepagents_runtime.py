"""Offline contract tests for the request-wide DeepAgents report runtime."""

import asyncio
import copy
import hashlib
import itertools
import json
import threading
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import replace
from uuid import UUID

import httpx
import pytest
from deepagents.middleware._state import private_state_field_names
from deepagents.middleware.summarization import SummarizationState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from app.agents.reports import harness
from app.agents.reports import meeting as meeting_report
from app.agents.reports import period as period_report
from app.agents.reports.meeting_tools import create_scoped_meeting_tools
from app.agents.reports.period_sources import create_period_tools
from app.services.agent_logging import agent_log_context, collect_token_usage
from app.services.llm import LLMError


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str


class Bundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: dict[str, Finding]


def _tool_call(counter, name, args):
    return {"name": name, "args": args, "id": f"call-{next(counter)}", "type": "tool_call"}


def _assignment(messages):
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if isinstance(content, str) and "SERVER_ASSIGNMENT=" in content:
            return json.loads(content.rsplit("SERVER_ASSIGNMENT=", 1)[1])
    return None


def _public_state(messages):
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if not isinstance(content, str):
            continue
        try:
            value = json.loads(content)
        except ValueError:
            continue
        if isinstance(value, dict) and "next_phase" in value:
            return value
    raise AssertionError("supervisor did not receive workflow state")


class ScriptedModel(BaseChatModel):
    """Drive the real SDK graph from server receipts, without provider traffic."""

    writer_role: str
    issues_r1: list[str] = []
    attack: str = ""
    failure: str = ""
    failure_phase: str = "review_initial"
    failure_work_unit: str | None = ""
    marker: str = ""
    _seen: list = PrivateAttr(default_factory=list)
    _bound: list = PrivateAttr(default_factory=list)
    _counter: itertools.count = PrivateAttr(default_factory=lambda: itertools.count(1))
    _parent_turns: int = PrivateAttr(default=0)
    _attacked: bool = PrivateAttr(default=False)
    _phases: list[str] = PrivateAttr(default_factory=list)
    _descriptions: list[str] = PrivateAttr(default_factory=list)
    _requested: dict = PrivateAttr(default_factory=lambda: defaultdict(list))
    _drafts: dict = PrivateAttr(default_factory=dict)
    _last_tools: set[str] = PrivateAttr(default_factory=set)

    @property
    def _llm_type(self):
        return "report-request-wide-offline-script"

    def bind_tools(self, tools, **kwargs):
        self._last_tools = {getattr(tool, "name", "") for tool in tools}
        self._bound.append(
            {getattr(tool, "name", ""): getattr(tool, "description", "") for tool in tools}
        )
        return self

    def _call(self, name, args):
        return _tool_call(self._counter, name, args)

    def _result(self, calls):
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=calls,
                        usage_metadata={
                            "input_tokens": 10,
                            "output_tokens": 2,
                            "total_tokens": 12,
                        },
                    )
                )
            ]
        )

    def _supervisor(self, messages):
        self._parent_turns += 1
        state = _public_state(messages)
        units = state["next_work_units"]
        if units:
            unit = units[0]
            role = unit["subagent_type"]
            work_id = unit["work_unit_id"]
            description = (
                f"work_unit_id={work_id}\n"
                "배정된 범위의 동결 근거를 읽고 검증 가능한 artifact를 반환하라."
            )
            if not self._attacked:
                if self.attack == "batch-tasks":
                    self._attacked = True
                    second = units[1]
                    return self._result(
                        [
                            self._call(
                                "task",
                                {"description": description, "subagent_type": role},
                            ),
                            self._call(
                                "task",
                                {
                                    "description": (
                                        f"work_unit_id={second['work_unit_id']}\n"
                                        "두 번째 범위도 같은 응답에서 동시에 위임한다."
                                    ),
                                    "subagent_type": second["subagent_type"],
                                },
                            ),
                        ]
                    )
                if self.attack == "wrong-role":
                    self._attacked = True
                    role = (
                        harness.REVIEWER_ROLE if role != harness.REVIEWER_ROLE else self.writer_role
                    )
                elif self.attack == "general-purpose":
                    self._attacked = True
                    role = "general-purpose"
                elif self.attack == "unknown-work":
                    self._attacked = True
                    description = description.replace(work_id, "write-999", 1)
                elif self.attack == "short-description":
                    self._attacked = True
                    description = f"work_unit_id={work_id}\n짧다"
            return self._result(
                [self._call("task", {"description": description, "subagent_type": role})]
            )
        version = max(state["eligible_versions"])
        return self._result([self._call("finish_report", {"candidate_version": version})])

    def _reads(self, assignment):
        calls = [
            self._call(
                "read_file",
                {"file_path": "/skills/report-style/SKILL.md", "offset": 0, "limit": 1000},
            ),
            self._call(
                "read_file",
                {
                    "file_path": f"/skills/{self.writer_role}/SKILL.md",
                    "offset": 0,
                    "limit": 1000,
                },
            ),
        ]
        if assignment["phase"] == "prepare":
            source_id = assignment["scope"]
            if self.attack == "prepare-sibling-source" and not self._attacked:
                self._attacked = True
                source_id = (
                    "meeting_bundle:2" if source_id == "meeting_bundle:1" else "meeting_bundle:1"
                )
            return calls + [
                self._call("read_report_context", {}),
                self._call("read_report_sources", {"source_id": source_id})
            ]
        if assignment["report_kind"] == "meeting":
            scopes = (
                assignment["source_scopes"]
                if assignment["role"] == harness.REVIEWER_ROLE
                else [assignment["scope"]]
            )
            if self.attack == "sibling-source" and not self._attacked:
                self._attacked = True
                scopes = ["sibling-scope"]
            calls.extend(
                self._call(
                    "read_meeting_evidence",
                    {"scope": scope}
                    if assignment["role"] == harness.REVIEWER_ROLE
                    or self.attack == "sibling-source"
                    else {},
                )
                for scope in scopes
            )
        else:
            calls.extend(
                [self._call("read_report_context", {}), self._call("read_report_sources", {})]
            )
            if assignment["phase"] == "synthesize":
                calls.append(self._call("read_writer_digests", {}))
        phase = assignment["phase"]
        if phase == "review_initial":
            calls.append(self._call("read_validated_draft", {"draft_version": 1}))
            if self.attack != "missing-plan-once" or self._attacked:
                calls.append(self._call("read_writer_plans", {"draft_version": 1}))
        elif phase == "repair":
            calls.extend(
                [
                    self._call("read_validated_draft", {"draft_version": 1}),
                    self._call("read_validated_review", {"review_round": 1}),
                ]
            )
        return calls

    def _writer_artifact(self, assignment):
        work_id = assignment["work_unit_id"]
        scope = assignment["scope"]
        phase = assignment["phase"]
        locations = assignment["allowed_locations"]
        evidence = assignment["allowed_plan_evidence"]
        if phase == "prepare":
            draft = {
                "source_id": scope,
                "report_kind": assignment["report_kind"],
                "facts": [
                    {
                        "kind": "fact",
                        "content": f"{scope} 동결 원문",
                        "source_id": scope,
                        "evidence_ref": evidence[0],
                    }
                ],
                "evidence_refs": [evidence[0]],
            }
            if self.attack in {
                "prepare-item-anchor",
                "prepare-foreign-source-ref",
            } and not self._attacked:
                self._attacked = True
                draft["facts"][0]["evidence_ref"] = (
                    "meeting_bundle:2"
                    if self.attack == "prepare-foreign-source-ref"
                    else "meeting_context.activity_id"
                )
            if (
                self.attack == "prepare-aggregate-anchor"
                and not self._attacked
            ):
                self._attacked = True
                draft["evidence_refs"] = ["meeting_context.activity_id"]
        elif phase == "repair":
            draft = copy.deepcopy(self._drafts[scope])
            field = locations[0].rsplit(".", 1)[-1]
            draft[field] += " 수정"
        else:
            draft = {"body": f"{self.marker}{scope} 초기 본문"}
            if "title" in assignment["output_shape"]:
                draft["kind"] = "deal"
                draft["title"] = f"{scope} 제목"
            elif assignment["report_kind"] == "meeting" and (
                scope == "common_report" or scope == "unassigned_report"
            ):
                draft["kind"] = "section"
            self._drafts[scope] = copy.deepcopy(draft)
        artifact = {
            "work_unit_id": work_id,
            "base_draft_version": 1 if phase == "repair" else 0,
            "review_round": 1 if phase == "repair" else None,
            "plan": [
                {
                    "location": location,
                    "intent": "동결 근거를 사실 그대로 반영한다.",
                    "evidence": [evidence[0]],
                }
                for location in locations
            ],
            "draft": draft,
        }
        if self.attack == "artifact-version" and not self._attacked:
            self._attacked = True
            artifact.update(base_draft_version=1, review_round=1)
        elif self.attack == "plan-scope" and not self._attacked:
            self._attacked = True
            artifact["plan"][0]["location"] = "sibling.body"
        elif self.attack == "invalid-nested-draft" and not self._attacked:
            self._attacked = True
            artifact["draft"]["unexpected"] = "SDK가 거부해야 한다"
        return artifact

    def _review_artifact(self, assignment):
        round_ = assignment["review_round"]
        artifact = {
            "draft_version": assignment["draft_version"],
            "review_round": round_,
            "issues": [
                {
                    "location": location,
                    "evidence": "동결 근거와 초안을 대조했다.",
                    "action": "해당 위치만 사실에 맞게 수정한다.",
                }
                for location in self.issues_r1
            ],
        }
        if self.attack == "review-version" and not self._attacked:
            self._attacked = True
            artifact.update(draft_version=2)
        return artifact

    def _child(self, messages, assignment):
        key = (assignment["phase"], assignment["work_unit_id"])
        if self.attack == "prepare-sibling-source" and any(
            isinstance(message, ToolMessage)
            and isinstance(message.content, str)
            and message.content.startswith("Error:")
            for message in messages
        ):
            raise PermissionError("report_source_not_allowed")
        if not any(isinstance(message, ToolMessage) for message in messages):
            description = next(
                message.content
                for message in reversed(messages)
                if isinstance(getattr(message, "content", None), str)
                and "SERVER_ASSIGNMENT=" in message.content
            )
            self._descriptions.append(description)
            calls = self._reads(assignment)
            self._requested[key].extend(copy.deepcopy(calls))
            return self._result(calls)
        if (
            self.attack == "missing-plan-once"
            and assignment["phase"] == "review_initial"
            and "ReportReview" not in self._last_tools
        ):
            self._attacked = True
            call = self._call("read_writer_plans", {"draft_version": 1})
            self._requested[key].append(copy.deepcopy(call))
            return self._result([call])
        if (
            self.failure
            and assignment["phase"] == self.failure_phase
            and (not self.failure_work_unit or assignment["work_unit_id"] == self.failure_work_unit)
        ):
            if self.failure == "recoverable":
                raise LLMError("report_generation_failed")
            if self.failure == "input":
                raise LLMError("period_report_sources_invalid")
            if self.failure == "invalid-schema":
                raise LLMError("report_output_invalid")
            request = httpx.Request("POST", "https://synthetic.invalid")
            status = (
                int(self.failure.removeprefix("provider-"))
                if self.failure.startswith("provider-")
                else 401
            )
            raise httpx.HTTPStatusError(
                "PRIVATE PROVIDER DETAIL",
                request=request,
                response=httpx.Response(status, request=request),
            )
        self._phases.append(assignment["phase"])
        if assignment["role"] == harness.REVIEWER_ROLE:
            return self._result([self._call("ReportReview", self._review_artifact(assignment))])
        return self._result([self._call("WriterArtifact", self._writer_artifact(assignment))])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._seen.append(copy.deepcopy(messages))
        if "REPORT_SUPERVISOR" in str(messages[0].content):
            return self._supervisor(messages)
        assignment = _assignment(messages)
        if assignment is None:
            raise AssertionError("child did not receive a server assignment")
        return self._child(messages, assignment)


def _spec(kind="daily", *, unit_count=1, validate_calls=None):
    meeting = kind == "meeting"
    writer_role = (
        "sales-meeting-report"
        if meeting
        else {
            "daily": "daily-report-writer",
            "weekly": "weekly-report-writer",
            "monthly": "monthly-report-writer",
        }[kind]
    )
    sections = [f"scope-{index}" for index in range(1, unit_count + 1)]
    if meeting:
        source = {
            scope: {
                "evidence": [{"segment_id": f"E{index}"}],
                "attachments": [],
                "required_evidence_ids": [f"E{index}"],
            }
            for index, scope in enumerate(sections, 1)
        }
    else:
        source = {
            "run_context": {"report_kind": kind, "guidance": "PRIVATE CONTEXT"},
            "source_units": [
                {
                    "source_id": "source-1",
                    "source_type": "child_submission",
                    "content": {"body": "PRIVATE SOURCE"},
                }
            ],
        }
    units = tuple(
        harness.WorkUnit(
            work_unit_id=f"write-{index:03}",
            scope=scope,
            schema=Finding,
            locations=frozenset({f"{scope}.body"}),
            evidence_refs=(frozenset({f"E{index}"}) if meeting else frozenset({"source-1"})),
            output_shape='{"body":"..."}',
        )
        for index, scope in enumerate(sections, 1)
    )

    def validate(draft):
        value = Bundle.model_validate(draft.model_dump(mode="json"))
        if set(value.sections) != set(sections):
            raise ValueError("report_scope_invalid")
        if validate_calls is not None:
            validate_calls.append(value.model_dump(mode="json"))

    def validate_unit(unit, value, previous, locations):
        Finding.model_validate(value.model_dump(mode="json"))
        if previous is not None and value.body == previous.body:
            raise LLMError("report_output_invalid")
        if previous is not None and locations != frozenset({f"{unit.scope}.body"}):
            raise PermissionError("report_revision_scope_not_allowed")

    return harness.WorkflowSpec(
        report_kind=kind,
        writer_role=writer_role,
        stage="runtime",
        instructions="합성 사실만 작성하라.",
        source=source,
        units=units,
        prefilled_sections={},
        assemble=lambda values: Bundle(sections=values),
        validate_draft=validate,
        validate_unit=validate_unit,
        source_count=len(source) if meeting else len(source["source_units"]),
    )


def _spy_supervisor(monkeypatch):
    created = []
    compiled = []
    invoked = []
    original = harness.create_deep_agent
    original_create_agent = harness.create_agent

    class GraphSpy:
        def __init__(self, graph):
            self.graph = graph

        async def ainvoke(self, *args, **kwargs):
            invoked.append((args, kwargs))
            return await self.graph.ainvoke(*args, **kwargs)

    def create(*args, **kwargs):
        created.append(kwargs)
        return GraphSpy(original(*args, **kwargs))

    def compile_child(*args, **kwargs):
        compiled.append(kwargs["name"])
        return original_create_agent(*args, **kwargs)

    monkeypatch.setattr(harness, "create_deep_agent", create)
    monkeypatch.setattr(harness, "create_agent", compile_child)
    return created, compiled, invoked


async def _run(monkeypatch, model, spec):
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)
    return await harness.run_report_workflow(spec)


@pytest.mark.parametrize(
    "kind,role",
    [
        ("meeting", "sales-meeting-report"),
        ("daily", "daily-report-writer"),
        ("weekly", "weekly-report-writer"),
        ("monthly", "monthly-report-writer"),
    ],
)
def test_actual_sdk_uses_one_supervisor_and_selected_writer_then_initial_review(
    monkeypatch, caplog, kind, role
):
    created, compiled, invoked = _spy_supervisor(monkeypatch)
    model = ScriptedModel(writer_role=role)
    with collect_token_usage() as usage:
        result = asyncio.run(_run(monkeypatch, model, _spec(kind)))

    assert len(created) == len(invoked) == 1
    assert compiled == [role, harness.REVIEWER_ROLE]
    assert {agent["name"] for agent in created[0]["subagents"]} == {
        "general-purpose",
        harness.REVIEWER_ROLE,
    }
    parent_task_descriptions = [
        tools["task"] for tools in model._bound if "task" in tools and "finish_report" in tools
    ]
    assert parent_task_descriptions
    assert all(
        role in value and "general-purpose" not in value for value in parent_task_descriptions
    )
    assert result.selected_version == 1 and result.degraded is False
    assert (result.task_count, result.review_count, result.repair_count) == (2, 1, 0)
    assert result.initial_review_conducted is True
    assert result.repair_completed is None
    assert result.review_issues == ()
    assert result.review_incomplete is False
    assert model._phases == ["write_initial", "review_initial"]
    assignments = [
        json.loads(text.rsplit("SERVER_ASSIGNMENT=", 1)[1]) for text in model._descriptions
    ]
    assert [item["role"] for item in assignments] == [role, harness.REVIEWER_ROLE]
    assert assignments[1]["allowed_locations"] == ["scope-1.body"]
    assert model._parent_turns == 3
    assert all(
        "work_unit_id=" in text and "검증 가능한 artifact" in text for text in model._descriptions
    )
    assert all("SERVER_ASSIGNMENT=" in text for text in model._descriptions)
    assert usage == {"input_tokens": 70, "output_tokens": 14, "total_tokens": 84}
    assert result.draft.sections["scope-1"].body == "scope-1 초기 본문"
    for calls in model._requested.values():
        names = [call["name"] for call in calls]
        assert names.count("read_file") == 2
        if kind != "meeting":
            assert {"read_report_context", "read_report_sources"} <= set(names)
    runtime = [
        json.loads(record.getMessage().split(" ", 1)[1])
        for record in caplog.records
        if '"stage": "runtime.runtime"' in record.getMessage()
    ]
    assert len(runtime) == 1
    assert runtime[0]["model_call_count"] == 7
    assert runtime[0]["tool_call_count"] == (11 if kind == "meeting" else 13)
    assert runtime[0]["delegation_count"] == runtime[0]["required_delegation_count"] == 2
    parent_messages = [
        messages for messages in model._seen if "REPORT_SUPERVISOR" in str(messages[0].content)
    ]
    assert "PRIVATE SOURCE" not in str(parent_messages)
    assert "PRIVATE SOURCE" not in caplog.text


def test_flagged_scopes_are_repaired_once_and_v2_child_draft_wins(monkeypatch):
    validations = []
    spec = _spec("daily", unit_count=2, validate_calls=validations)
    model = ScriptedModel(
        writer_role=spec.writer_role,
        issues_r1=["scope-1.body", "scope-2.body"],
    )
    created, compiled, invoked = _spy_supervisor(monkeypatch)

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert len(created) == len(invoked) == 1
    assert compiled == [spec.writer_role, harness.REVIEWER_ROLE]
    assert result.selected_version == 2 and result.degraded is False
    assert (result.task_count, result.review_count, result.repair_count) == (5, 1, 2)
    assert model._phases.count("review_initial") == 1
    assert model._phases.count("repair") == 2
    assert result.initial_review_conducted is True
    assert result.repair_completed is True
    assert result.review_incomplete is False
    assert [issue.location for issue in result.review_issues] == [
        "scope-1.body",
        "scope-2.body",
    ]
    finish_turn = [
        messages for messages in model._seen if "REPORT_SUPERVISOR" in str(messages[0].content)
    ][-1]
    assert _public_state(finish_turn)["eligible_versions"] == [2]
    assert {key[1] for key in model._requested if key[0] == "repair"} == {
        "repair-001",
        "repair-002",
    }
    for scope in ("scope-1", "scope-2"):
        assert result.draft.sections[scope].body == f"{scope} 초기 본문 수정"
    assert validations[-1] == result.draft.model_dump(mode="json")

    expected_reads = {
        ("review_initial", "review-1"): {
            ("read_validated_draft", "draft_version", 1),
            ("read_writer_plans", "draft_version", 1),
        },
        ("repair", "repair-001"): {
            ("read_validated_draft", "draft_version", 1),
            ("read_validated_review", "review_round", 1),
        },
        ("repair", "repair-002"): {
            ("read_validated_draft", "draft_version", 1),
            ("read_validated_review", "review_round", 1),
        },
    }
    for key, expected in expected_reads.items():
        actual = {
            (call["name"], field, call["args"][field])
            for call in model._requested[key]
            for field in call["args"]
            if call["name"].startswith("read_validated") or call["name"] == "read_writer_plans"
        }
        assert expected <= actual


def test_no_second_review_task_or_model_call_after_repair(monkeypatch):
    spec = _spec("daily")
    model = ScriptedModel(
        writer_role=spec.writer_role,
        issues_r1=["scope-1.body"],
    )

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 2 and result.degraded is False
    assert [issue.location for issue in result.review_issues] == ["scope-1.body"]
    assert result.review_incomplete is False
    assert result.repair_completed is True
    assert (result.task_count, result.review_count, result.repair_count) == (3, 1, 1)
    assert model._phases == [
        "write_initial",
        "review_initial",
        "repair",
    ]


def test_writer_and_reviewer_must_read_required_meeting_scopes(monkeypatch):
    spec = _spec("meeting", unit_count=2)
    model = ScriptedModel(writer_role=spec.writer_role, issues_r1=["scope-1.body"])

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 2
    for key, calls in model._requested.items():
        assert [call["name"] for call in calls].count("read_file") == 2
        expected_scopes = (
            ["scope-1", "scope-2"]
            if key[1] == "review-1"
            else ["scope-1"]
            if key[1] in {"write-001", "repair-001"}
            else ["scope-2"]
        )
        actual = [
            call["args"].get("scope") or expected_scopes[0]
            for call in calls
            if call["name"] == "read_meeting_evidence"
        ]
        assert actual == expected_scopes


def test_output_tool_is_hidden_until_missing_plan_is_actually_read(monkeypatch):
    spec = _spec("daily")
    model = ScriptedModel(writer_role=spec.writer_role, attack="missing-plan-once")

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 1
    review_tools = [set(tools) for tools in model._bound if "read_writer_plans" in tools]
    assert len(review_tools) >= 3
    assert "ReportReview" not in review_tools[-3]
    assert "ReportReview" not in review_tools[-2]
    assert "ReportReview" in review_tools[-1]
    assert [call["name"] for call in model._requested[("review_initial", "review-1")]].count(
        "read_writer_plans"
    ) == 1


def test_nested_writer_schema_retries_in_same_sdk_child_before_accept(monkeypatch):
    accepted = []
    spec = replace(
        _spec("daily"),
        on_draft=lambda version, draft: accepted.append((version, draft.model_dump(mode="json"))),
    )
    model = ScriptedModel(writer_role=spec.writer_role, attack="invalid-nested-draft")

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 1
    assert accepted == [(1, result.draft.model_dump(mode="json"))]
    assert model._phases.count("write_initial") == 2
    assert model._phases.count("review_initial") == 1
    assert any(
        isinstance(message, ToolMessage) and "validation error" in str(message.content).lower()
        for messages in model._seen
        for message in messages
    )


def test_meeting_limits_scale_past_a_tiny_fixed_task_cap(monkeypatch):
    spec = _spec("meeting", unit_count=12)
    model = ScriptedModel(writer_role=spec.writer_role)

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.task_count == 13
    assert result.review_count == 1
    assert model._parent_turns == 14
    assert set(result.draft.sections) == {f"scope-{index}" for index in range(1, 13)}


def test_parent_rejects_batched_tasks_before_children_run(monkeypatch):
    spec = _spec("daily", unit_count=2)
    model = ScriptedModel(writer_role=spec.writer_role, attack="batch-tasks")

    with pytest.raises(PermissionError, match="report_supervisor_action_invalid"):
        asyncio.run(_run(monkeypatch, model, spec))

    assert model._descriptions == []
    assert model._phases == []


def test_meeting_writers_batch_through_native_tool_node(monkeypatch):
    class BatchDealModel(ScriptedModel):
        _writer_barrier = PrivateAttr(default_factory=lambda: threading.Barrier(4))

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            assignment = _assignment(messages)
            if (
                assignment
                and assignment["phase"] == "write_initial"
                and not any(isinstance(message, AIMessage) for message in messages)
            ):
                self._writer_barrier.wait(timeout=2)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        def _supervisor(self, messages):
            state = _public_state(messages)
            units = state["next_work_units"]
            if state["next_phase"] == "write_initial" and len(units) >= 2 and not self._attacked:
                self._attacked = True
                self._parent_turns += 1
                return self._result(
                    [
                        self._call(
                            "task",
                            {
                                "description": (
                                    f"work_unit_id={unit['work_unit_id']}\n"
                                    "배정된 범위의 동결 근거를 읽고 검증 가능한 "
                                    "artifact를 반환하라."
                                ),
                                "subagent_type": unit["subagent_type"],
                            },
                        )
                        for unit in units
                    ]
                )
            return super()._supervisor(messages)

    spec = _spec("meeting", unit_count=4)
    spec = replace(
        spec,
        units=tuple(
            replace(unit, sales_deal_id=f"deal-{index}" if index < 3 else None)
            for index, unit in enumerate(spec.units)
        ),
    )
    model = BatchDealModel(writer_role=spec.writer_role)
    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.task_count == 5  # three deal + one common writer in one turn, then one review
    assert result.review_count == 1
    assert model._parent_turns == 3
    writer_assignments = {
        assignment["work_unit_id"]: assignment
        for assignment in map(_assignment, model._seen)
        if assignment and assignment["phase"] == "write_initial"
    }
    assert set(writer_assignments) == {f"write-{index:03}" for index in range(1, 5)}
    assert {item["scope"] for item in writer_assignments.values()} == {
        f"scope-{index}" for index in range(1, 5)
    }
    assert writer_assignments["write-004"]["sales_deal_id"] is None
    assert set(result.draft.sections) == {f"scope-{index}" for index in range(1, 5)}
    for work_id in writer_assignments:
        assert [call["name"] for call in model._requested[("write_initial", work_id)]].count(
            "read_meeting_evidence"
        ) == 1


@pytest.mark.parametrize("attack", ["duplicate-id", "duplicate-work", "mixed-scope", "mixed-phase"])
def test_meeting_deal_batch_reservation_is_atomic(attack):
    spec = _spec("meeting", unit_count=2)
    spec = replace(
        spec,
        units=tuple(
            replace(unit, sales_deal_id=f"deal-{index}")
            for index, unit in enumerate(spec.units)
        ),
    )
    coordinator = harness._Coordinator(spec, object())
    calls = [
        {
            "name": "task",
            "id": "same-call" if attack == "duplicate-id" else f"call-{index}",
            "args": {
                "description": (
                    f"work_unit_id=write-00{index + 1}\n"
                    "배정된 범위의 동결 근거를 읽고 검증 가능한 artifact를 반환하라."
                ),
                "subagent_type": spec.writer_role,
            },
        }
        for index in range(2)
    ]
    if attack == "mixed-scope":
        calls[1]["args"]["description"] = calls[1]["args"]["description"].replace(
            "write-002", "write-999"
        )
    elif attack == "duplicate-work":
        calls[1]["args"]["description"] = calls[0]["args"]["description"]
    elif attack == "mixed-phase":
        coordinator.assignments["write-002"] = replace(
            coordinator.assignments["write-002"], phase="review_initial"
        )
    with pytest.raises(PermissionError):
        coordinator.reserve(calls)
    assert coordinator.reserved == set()
    assert coordinator.call_assignments == {}


@pytest.mark.parametrize("scope", ["common_report", "unassigned_report"])
def test_meeting_batch_reservation_allows_unassigned_writer(scope):
    spec = _spec("meeting", unit_count=2)
    spec = replace(
        spec,
        units=tuple(
            replace(
                unit,
                scope=scope if index else unit.scope,
                sales_deal_id=f"deal-{index}" if index == 0 else None,
            )
            for index, unit in enumerate(spec.units)
        ),
    )
    coordinator = harness._Coordinator(spec, object())
    calls = [
        {
            "name": "task",
            "id": f"call-{index}",
            "args": {
                "description": (
                    f"work_unit_id=write-00{index + 1}\n"
                    "배정된 범위의 동결 근거를 읽고 검증 가능한 artifact를 반환하라."
                ),
                "subagent_type": spec.writer_role,
            },
        }
        for index in range(2)
    ]

    coordinator.reserve(calls)

    assert coordinator.reserved == {"write-001", "write-002"}
    assert coordinator.call_assignments["call-1"].unit.scope == scope
    assert coordinator.call_assignments["call-1"].unit.sales_deal_id is None


def test_native_dispatcher_strips_long_parent_private_state_from_children(monkeypatch):
    private_keys = private_state_field_names(SummarizationState)
    child_private_keys = []
    child_saw_long_parent = []
    original_child = harness.create_agent
    original_parent = harness.create_deep_agent

    class CapturePrivateState(AgentMiddleware):
        state_schema = SummarizationState

        async def awrap_model_call(self, request, handler):
            child_private_keys.append(private_keys & request.state.keys())
            child_saw_long_parent.append("LONG_PARENT_ONLY" in str(request.state.get("messages")))
            return await handler(request)

    def create_child(*args, **kwargs):
        kwargs["middleware"] = [CapturePrivateState(), *kwargs["middleware"]]
        return original_child(*args, **kwargs)

    def create_parent(*args, **kwargs):
        graph = original_parent(*args, **kwargs)

        class InjectLongParentState:
            async def ainvoke(self, state, *invoke_args, **invoke_kwargs):
                state = {
                    **state,
                    "messages": [
                        *state["messages"],
                        HumanMessage(content="LONG_PARENT_ONLY" * 4_000),
                    ],
                    "jump_to": None,
                    "_summarization_event": {
                        "cutoff_index": 0,
                        "summary_message": HumanMessage(content="PRIVATE_PARENT_SUMMARY"),
                        "file_path": "/private-parent-history",
                    },
                    "_summarization_session_id": "private-parent-session",
                }
                return await graph.ainvoke(state, *invoke_args, **invoke_kwargs)

        return InjectLongParentState()

    monkeypatch.setattr(harness, "create_agent", create_child)
    monkeypatch.setattr(harness, "create_deep_agent", create_parent)
    model = ScriptedModel(writer_role="daily-report-writer")

    result = asyncio.run(_run(monkeypatch, model, _spec("daily")))

    assert result.selected_version == 1
    assert private_keys == {"jump_to", "_summarization_event", "_summarization_session_id"}
    assert child_private_keys and all(not keys for keys in child_private_keys)
    assert not any(child_saw_long_parent)


def test_actual_meeting_entrypoint_keeps_server_identity_and_evidence_assembly(monkeypatch):
    from test_report_writing_deep import sample

    source = sample()
    model = ScriptedModel(writer_role=meeting_report.WRITER_ROLE)
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)

    result = asyncio.run(meeting_report.run(source))

    assert [item.sales_deal_id for item in result.deal_reports] == list(
        source.evidence.selected_deal_ids
    )
    assert result.deal_reports[0].evidence_ids == ["S0002"]
    assert result.deal_reports[1].body == meeting_report.NO_DEAL_EVIDENCE_TEXT
    assert model._phases == [
        "write_initial",
        "write_initial",
        "write_initial",
        "review_initial",
    ]


def test_actual_meeting_common_report_stays_fact_bullets_through_review_repair(monkeypatch):
    from test_report_writing_deep import sample

    initial = "- 구매팀과 두 영업 딜을 함께 검토했습니다."
    repaired = (
        initial
        + "\n- 통합 도입 여부는 9월 25일까지 내부 결정합니다."
        + "\n- 김지훈 담당자가 9월 15일까지 공통 이전 일정표를 전달합니다."
    )

    class CommonBulletModel(ScriptedModel):
        def _writer_artifact(self, assignment):
            artifact = super()._writer_artifact(assignment)
            scope = assignment["scope"]
            if scope == "common_report":
                artifact["draft"] = {
                    "body": repaired if assignment["phase"] == "repair" else initial,
                    "kind": "section",
                }
                self._drafts[scope] = copy.deepcopy(artifact["draft"])
            elif scope.startswith("deal_reports") and assignment["phase"] == "write_initial":
                artifact["draft"]["body"] = "**논의 내용**\n\n딜 근거를 기록했습니다."
                self._drafts[scope] = copy.deepcopy(artifact["draft"])
            return artifact

    source = sample().model_dump(mode="json")
    source["evidence"]["items"][0]["segment"]["text"] = (
        "구매팀과 두 영업 딜을 함께 검토했다. 통합 도입 여부는 9월 25일까지 내부 결정하고, "
        "김지훈 담당자가 9월 15일까지 공통 이전 일정표를 전달한다."
    )
    source["transcript"] = "\n".join(
        item["segment"]["text"] for item in source["evidence"]["items"]
    )
    source["evidence"]["transcript_sha256"] = hashlib.sha256(
        source["transcript"].encode()
    ).hexdigest()
    start = 0
    for item in source["evidence"]["items"]:
        item["segment"]["start"] = start
        item["segment"]["end"] = start + len(item["segment"]["text"])
        start = item["segment"]["end"] + 1
    source = meeting_report.ReportWritingInput.model_validate(source)

    model = CommonBulletModel(
        writer_role=meeting_report.WRITER_ROLE,
        issues_r1=["common_report.body"],
    )
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)

    result = asyncio.run(meeting_report.run(source))

    assert result.common_report.body == repaired
    assert "**미팅 목적**" not in result.common_report.body
    assert "미확인" not in result.common_report.body
    assert result.common_report.body.splitlines() == [
        "- 구매팀과 두 영업 딜을 함께 검토했습니다.",
        "- 통합 도입 여부는 9월 25일까지 내부 결정합니다.",
        "- 김지훈 담당자가 9월 15일까지 공통 이전 일정표를 전달합니다.",
    ]
    assert result.deal_reports[0].body.startswith("**논의 내용**\n\n")
    assert model._phases.count("review_initial") == 1
    assert model._phases.count("repair") == 1
    child_prompts = [
        str(messages[0].content)
        for messages in model._seen
        if "REPORT_WRITER" in str(messages[0].content)
        or "REPORT_REVIEWER" in str(messages[0].content)
    ]
    assert child_prompts
    assert all("common_report 본문은 공통으로 확인된 사실" in prompt for prompt in child_prompts)


def test_actual_period_entrypoint_returns_server_validated_child_body(monkeypatch):
    from test_period_report_writing_deep import sample

    class PeriodModel(ScriptedModel):
        def _writer_artifact(self, assignment):
            artifact = super()._writer_artifact(assignment)
            if assignment["phase"] == "synthesize":
                artifact["draft"] = {
                    "fields": [{"field_id": "body", "value": "동결 제출을 집계한 일일 본문"}]
                }
            return artifact

    model = PeriodModel(writer_role="daily-report-writer")
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)

    result = asyncio.run(period_report.run(sample()))

    assert result.fields[0].value == "동결 제출을 집계한 일일 본문"
    assert model._phases == ["prepare", "prepare", "synthesize", "review_initial"]
    assert all(
        [
            call["args"].get("source_id")
            for call in model._requested[("prepare", work_id)]
            if call["name"] == "read_report_sources"
        ]
        == [scope]
        for work_id, scope in (
            ("prepare-meeting-bundle-1", "meeting_bundle:1"),
            ("prepare-meeting-bundle-2", "meeting_bundle:2"),
        )
    )
    assert any(
        call["name"] == "read_writer_digests"
        for call in model._requested[("synthesize", "write-001")]
    )


@pytest.mark.parametrize(
    ("failure", "failure_work_unit"),
    [
        (failure, work_unit)
        for failure in ("provider-429", "invalid-schema")
        for work_unit in ("prepare-meeting-bundle-1", None)
    ],
)
def test_period_prepare_failure_reaches_synthesis_as_failed_source(
    monkeypatch, failure, failure_work_unit
):
    from test_period_report_writing_deep import sample

    class FailedPrepareModel(ScriptedModel):
        _digests: list[dict] = PrivateAttr(default_factory=list)

        def _writer_artifact(self, assignment):
            artifact = super()._writer_artifact(assignment)
            if assignment["phase"] == "synthesize":
                artifact["draft"] = {
                    "fields": [{"field_id": "body", "value": "실패를 표시한 본문"}]
                }
            return artifact

    model = FailedPrepareModel(
        writer_role="daily-report-writer",
        failure=failure,
        failure_phase="prepare",
        failure_work_unit=failure_work_unit,
    )
    original = harness._Coordinator.writer_digests

    def capture(self):
        value = original(self)
        model._digests = copy.deepcopy(value)
        return value

    monkeypatch.setattr(harness._Coordinator, "writer_digests", capture)
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)
    events = []
    monkeypatch.setattr(
        period_report, "log_agent_event", lambda _stage, **kwargs: events.append(kwargs)
    )

    result = asyncio.run(period_report.run(sample()))

    assert result.fields[0].value == "실패를 표시한 본문"
    assert events[-1]["outcome"] == "degraded"
    assert [item.get("source_id") or item["draft"]["source_id"] for item in model._digests] == [
        "meeting_bundle:1",
        "meeting_bundle:2",
    ]
    expected_error = (
        "llm_provider_error:429" if failure == "provider-429" else "report_output_invalid"
    )
    for index, item in enumerate(model._digests):
        if failure_work_unit is None or index == 0:
            assert item["status"] == "failed"
            assert item["error_code"] == expected_error
            assert "동결 원문" not in json.dumps(item, ensure_ascii=False)
        else:
            assert item["draft"]["source_id"] == "meeting_bundle:2"
    assert any(
        call["name"] == "read_report_sources" and not call["args"]
        for call in model._requested[("synthesize", "write-001")]
    )


def test_period_prepare_permission_error_propagates_through_native_graph(monkeypatch):
    from test_period_report_writing_deep import sample

    model = ScriptedModel(writer_role="daily-report-writer", attack="prepare-sibling-source")
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)

    with pytest.raises(PermissionError, match="report_source_not_allowed"):
        asyncio.run(period_report.run(sample()))
    assert "synthesize" not in model._phases


@pytest.mark.parametrize(
    "attack", ["prepare-item-anchor", "prepare-aggregate-anchor", "prepare-foreign-source-ref"]
)
def test_period_prepare_invalid_digest_becomes_failed_source_and_synthesis_reads_original(
    monkeypatch, attack
):
    from test_period_report_writing_deep import sample

    class AnchorDigestModel(ScriptedModel):
        def _writer_artifact(self, assignment):
            artifact = super()._writer_artifact(assignment)
            if assignment["phase"] == "synthesize":
                artifact["draft"] = {
                    "fields": [{"field_id": "body", "value": "원문으로 종합한 본문"}]
                }
            return artifact

    model = AnchorDigestModel(writer_role="daily-report-writer", attack=attack)
    captured_digests = []
    original_digests = harness._Coordinator.writer_digests

    def capture_digests(coordinator):
        value = original_digests(coordinator)
        captured_digests.append(copy.deepcopy(value))
        return value

    monkeypatch.setattr(harness._Coordinator, "writer_digests", capture_digests)
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)

    events = []
    monkeypatch.setattr(
        period_report, "log_agent_event", lambda _stage, **kwargs: events.append(kwargs)
    )
    writes = []
    original_write = harness.StateBackend.write

    def record_write(backend, path, content):
        writes.append(path)
        return original_write(backend, path, content)

    monkeypatch.setattr(harness.StateBackend, "write", record_write)
    result = asyncio.run(period_report.run(sample()))

    assert result.fields[0].value == "원문으로 종합한 본문"
    assert events[-1]["outcome"] == "degraded"
    assert captured_digests[-1][0] == {
        "source_id": "meeting_bundle:1",
        "status": "failed",
        "error_code": "report_source_digest_invalid",
    }
    assert captured_digests[-1][1]["draft"]["source_id"] == "meeting_bundle:2"
    assert "/artifacts/source-digests/meeting_bundle:1.json" not in writes
    assert "/artifacts/source-digests/meeting_bundle:2.json" in writes
    assert "synthesize" in model._phases
    assert any(
        call["name"] == "read_report_sources" and not call["args"]
        for call in model._requested[("synthesize", "write-001")]
    )


@pytest.mark.parametrize("suppress_cancellation", [False, True])
def test_period_parent_cancellation_does_not_persist_late_prepare_artifact(
    monkeypatch, suppress_cancellation
):
    from test_period_report_writing_deep import sample

    class HangingPrepareModel(ScriptedModel):
        _started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)
        _late_artifact_returned: bool = PrivateAttr(default=False)

        async def _agenerate(self, messages, **kwargs):
            assignment = _assignment(messages)
            if assignment and assignment["phase"] == "prepare":
                self._started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    if not suppress_cancellation:
                        raise
                    result = self._generate(
                        [
                            *messages,
                            ToolMessage(
                                content="late frozen source",
                                tool_call_id="late-source",
                                name="read_report_sources",
                            ),
                        ],
                        **kwargs,
                    )
                    calls = result.generations[0].message.tool_calls
                    artifact_call = next(
                        call for call in calls if call["name"] == "WriterArtifact"
                    )
                    harness.WriterArtifact.model_validate(artifact_call["args"])
                    self._late_artifact_returned = True
                    return result
            return self._generate(messages, **kwargs)

    model = HangingPrepareModel(writer_role="daily-report-writer")
    writes = []
    original_write = harness.StateBackend.write

    def record_write(self, path, content):
        writes.append(path)
        return original_write(self, path, content)

    monkeypatch.setattr(harness.StateBackend, "write", record_write)
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)

    async def check():
        task = asyncio.create_task(period_report.run(sample()))
        await model._started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())
    assert model._late_artifact_returned is suppress_cancellation
    assert not any(path.startswith("/artifacts/source-digests/") for path in writes)
    assert "/artifacts/final.json" not in writes


def test_period_preparers_enter_native_sdk_graph_concurrently(monkeypatch):
    from test_period_report_writing_deep import sample

    class ParallelPeriodModel(ScriptedModel):
        _prepare_barrier = PrivateAttr(default_factory=lambda: threading.Barrier(2))

        def _supervisor(self, messages):
            state = _public_state(messages)
            if state["next_phase"] == "prepare" and len(state["next_work_units"]) == 2:
                calls = [
                    self._call(
                        "task",
                        {
                            "description": (
                                f"work_unit_id={unit['work_unit_id']}\n"
                                "배정된 범위의 동결 근거를 읽고 검증 가능한 artifact를 반환하라."
                            ),
                            "subagent_type": unit["subagent_type"],
                        },
                    )
                    for unit in state["next_work_units"]
                ]
                return self._result(calls)
            return super()._supervisor(messages)

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            assignment = _assignment(messages)
            if assignment and assignment["phase"] == "prepare" and not any(
                isinstance(message, AIMessage) for message in messages
            ):
                self._prepare_barrier.wait(timeout=2)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        def _writer_artifact(self, assignment):
            artifact = super()._writer_artifact(assignment)
            if assignment["phase"] == "synthesize":
                artifact["draft"] = {"fields": [{"field_id": "body", "value": "병렬 준비 본문"}]}
            return artifact

    model = ParallelPeriodModel(writer_role="daily-report-writer")
    monkeypatch.setattr(harness, "configured_chat_model", lambda: model)
    result = asyncio.run(period_report.run(sample()))

    assert result.fields[0].value == "병렬 준비 본문"
    assert model._phases.count("prepare") == 2
    assert model._phases[-2:] == ["synthesize", "review_initial"]


def test_concurrent_requests_isolate_models_sources_artifacts_and_usage(monkeypatch):
    async def check():
        current = ContextVar("runtime_test_request")
        models = {
            key: ScriptedModel(writer_role="daily-report-writer", marker=f"{key}-")
            for key in ("A", "B")
        }
        specs = {key: _spec("daily") for key in models}
        for key, spec in specs.items():
            spec.source["run_context"]["guidance"] = f"PRIVATE-SOURCE-{key}"
        monkeypatch.setattr(harness, "configured_chat_model", lambda: models[current.get()])

        async def run(key):
            token = current.set(key)
            try:
                with collect_token_usage() as usage:
                    result = await harness.run_report_workflow(specs[key])
                return result, usage
            finally:
                current.reset(token)

        results = await asyncio.gather(run("A"), run("B"))
        for key, (result, usage) in zip(("A", "B"), results, strict=True):
            assert result.draft.sections["scope-1"].body == f"{key}-scope-1 초기 본문"
            assert usage == {"input_tokens": 70, "output_tokens": 14, "total_tokens": 84}
            messages = str(models[key]._seen)
            assert f"PRIVATE-SOURCE-{key}" in messages
            assert f"PRIVATE-SOURCE-{'B' if key == 'A' else 'A'}" not in messages

    asyncio.run(check())


@pytest.mark.parametrize(
    "attack,kind",
    [
        ("wrong-role", "daily"),
        ("general-purpose", "daily"),
        ("unknown-work", "daily"),
        ("short-description", "daily"),
        ("artifact-version", "daily"),
        ("review-version", "daily"),
        ("plan-scope", "daily"),
        ("sibling-source", "meeting"),
    ],
)
def test_invalid_role_work_version_plan_and_source_scope_are_rejected(monkeypatch, attack, kind):
    spec = _spec(kind, unit_count=2 if kind == "meeting" else 1)
    model = ScriptedModel(writer_role=spec.writer_role, attack=attack)
    with pytest.raises(PermissionError):
        asyncio.run(_run(monkeypatch, model, spec))


def test_report_kind_rejects_a_sibling_writer_before_model_use(monkeypatch):
    spec = replace(_spec("daily"), writer_role="monthly-report-writer")
    model = ScriptedModel(writer_role="monthly-report-writer")

    with pytest.raises(ValueError, match="report_role_invalid"):
        asyncio.run(_run(monkeypatch, model, spec))

    assert model._seen == []


def test_recoverable_initial_review_failure_keeps_valid_v1(monkeypatch):
    spec = _spec("daily")
    model = ScriptedModel(writer_role=spec.writer_role, failure="recoverable")

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 1 and result.degraded is True
    assert result.draft.sections["scope-1"].body == "scope-1 초기 본문"
    assert result.initial_review_conducted is False
    assert result.repair_completed is None
    assert result.review_issues == ()
    assert result.review_incomplete is True
    assert (result.task_count, result.review_count, result.repair_count) == (2, 1, 0)


def test_recoverable_repair_failure_keeps_latest_valid_draft(monkeypatch):
    spec = _spec("daily")
    model = ScriptedModel(
        writer_role=spec.writer_role,
        issues_r1=["scope-1.body"],
        failure="recoverable",
        failure_phase="repair",
    )

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 1 and result.degraded is True
    assert result.draft.sections["scope-1"].body == "scope-1 초기 본문"
    assert result.repair_completed is False
    assert result.review_incomplete is True
    assert (result.task_count, result.review_count, result.repair_count) == (3, 1, 1)


def test_partial_repair_failure_keeps_valid_mixed_v2_with_honest_metadata(monkeypatch):
    spec = _spec("daily", unit_count=2)
    model = ScriptedModel(
        writer_role=spec.writer_role,
        issues_r1=["scope-1.body", "scope-2.body"],
        failure="recoverable",
        failure_phase="repair",
        failure_work_unit="repair-002",
    )

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 2 and result.degraded is True
    assert result.draft.sections["scope-1"].body == "scope-1 초기 본문 수정"
    assert result.draft.sections["scope-2"].body == "scope-2 초기 본문"
    assert [issue.location for issue in result.review_issues] == ["scope-1.body", "scope-2.body"]
    assert result.review_incomplete is True
    assert result.repair_completed is False
    assert (result.task_count, result.review_count, result.repair_count) == (5, 1, 2)


def test_invalid_repair_assembly_never_replaces_v1(monkeypatch):
    spec = _spec("daily")
    validate = spec.validate_draft
    calls = 0

    def reject_v2(draft):
        nonlocal calls
        calls += 1
        validate(draft)
        if calls == 2:
            raise ValueError("report_scope_invalid")

    spec = replace(spec, validate_draft=reject_v2)
    model = ScriptedModel(writer_role=spec.writer_role, issues_r1=["scope-1.body"])

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 1 and result.degraded is True
    assert result.draft.sections["scope-1"].body == "scope-1 초기 본문"
    assert (result.task_count, result.review_count, result.repair_count) == (3, 1, 1)


@pytest.mark.parametrize("failure", ["auth", "provider-400", "provider-403", "input"])
def test_nonrecoverable_failure_after_valid_draft_is_not_hidden_by_fallback(
    monkeypatch, caplog, failure
):
    spec = _spec("daily")
    model = ScriptedModel(writer_role=spec.writer_role, failure=failure)
    expected = "period_report_sources_invalid" if failure == "input" else "llm_provider_error:"
    with pytest.raises(LLMError, match=expected):
        asyncio.run(_run(monkeypatch, model, spec))
    assert "PRIVATE PROVIDER DETAIL" not in caplog.text


def test_transient_provider_failure_after_valid_draft_keeps_v1(monkeypatch):
    spec = _spec("daily")
    model = ScriptedModel(writer_role=spec.writer_role, failure="provider-429")

    result = asyncio.run(_run(monkeypatch, model, spec))

    assert result.selected_version == 1 and result.degraded is True


def test_backend_runtime_failure_after_v1_propagates(monkeypatch, caplog):
    original_write = harness.StateBackend.write

    def fail_review_write(self, path, content):
        if path == "/artifacts/reviews/r1.json":
            raise RuntimeError("PRIVATE BACKEND DETAIL")
        return original_write(self, path, content)

    monkeypatch.setattr(harness.StateBackend, "write", fail_review_write)
    spec = _spec("daily")
    model = ScriptedModel(writer_role=spec.writer_role)

    with pytest.raises(RuntimeError, match="PRIVATE BACKEND DETAIL"):
        asyncio.run(_run(monkeypatch, model, spec))
    assert "PRIVATE BACKEND DETAIL" not in caplog.text


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_is_normalized_and_caller_cancellation_propagates(monkeypatch, cancel):
    async def check():
        class HangingModel(BaseChatModel):
            _started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

            @property
            def _llm_type(self):
                return "report-hanging-offline-script"

            def bind_tools(self, tools, **kwargs):
                return self

            def _generate(self, messages, stop=None, run_manager=None, **kwargs):
                raise AssertionError("async path expected")

            async def _agenerate(self, messages, **kwargs):
                self._started.set()
                await asyncio.Future()

        model = HangingModel()
        monkeypatch.setattr(harness, "configured_chat_model", lambda: model)
        monkeypatch.setattr(harness, "REPORT_TIMEOUT_SECONDS", 180 if cancel else 0.02)
        task = asyncio.create_task(harness.run_report_workflow(_spec("daily")))
        await model._started.wait()
        if cancel:
            task.cancel()
        expected = asyncio.CancelledError if cancel else LLMError
        with pytest.raises(expected, match=None if cancel else "report_generation_timeout"):
            await task

    asyncio.run(check())


def test_scoped_and_period_tools_keep_exact_frozen_boundaries():
    meeting_payload = {
        "source": {
            "deal_reports[0]": {
                "sales_deal_id": str(UUID(int=1)),
                "evidence": [{"id": "E1"}],
                "attachments": [],
                "required_evidence_ids": ["E1"],
                "crm_context": {"company": "A"},
                "previous_reports": [{"body": "old"}],
            }
        }
    }
    frozen = copy.deepcopy(meeting_payload)
    evidence, crm, previous = create_scoped_meeting_tools(meeting_payload)
    assert evidence("deal_reports[0]")["evidence"] == [{"id": "E1"}]
    assert crm("deal_reports[0]", UUID(int=1)) == {"crm_context": {"company": "A"}}
    assert previous("deal_reports[0]", UUID(int=1)) == {"previous_reports": [{"body": "old"}]}
    evidence("deal_reports[0]")["evidence"].clear()
    assert meeting_payload == frozen
    with pytest.raises(PermissionError):
        evidence("deal_reports[1]")

    period_payload = {
        "run_context": {"guidance": "PRIVATE"},
        "source_units": [{"source_id": "source-1", "content": {"body": "가" * 60_000}}],
    }
    context, sources = create_period_tools(period_payload)
    assert context() == period_payload["run_context"]
    assert sources("source-1") == period_payload["source_units"]
    sources()[0]["content"]["body"] = "changed"
    assert len(sources()[0]["content"]["body"]) == 60_000
    with pytest.raises(PermissionError):
        sources("source-2")


def test_scope_guards_emit_real_json_correlation_for_meeting_and_period(caplog):
    caplog.set_level("INFO", logger="app.services.agent_logging")
    meeting = harness._Coordinator(_spec("meeting", unit_count=2), object())
    assignment = meeting.assignments["write-001"]
    token = harness._ACTIVE_ASSIGNMENT.set((meeting, assignment))
    try:
        with agent_log_context(run_id="run-1", parent_run_id="parent-1"):
            assert meeting.meeting_scope_access("read_meeting_evidence", "scope-1")
            assert not meeting.meeting_scope_access("read_meeting_evidence", "scope-9")
            assert not meeting.meeting_scope_access("read_meeting_evidence", "scope-2")
    finally:
        harness._ACTIVE_ASSIGNMENT.reset(token)

    period = harness._Coordinator(_spec("daily"), object())
    assignment = period.assignments["write-001"]
    token = harness._ACTIVE_ASSIGNMENT.set((period, assignment))
    try:
        with agent_log_context(run_id="run-2", parent_run_id="parent-2"):
            assert period.period_source_access("read_report_sources", "source-1")
            assert not period.period_source_access("read_report_sources", "source-9")
    finally:
        harness._ACTIVE_ASSIGNMENT.reset(token)

    events = [json.loads(record.getMessage().split(" ", 1)[1]) for record in caplog.records]
    assert [event["reason_code"] for event in events] == [
        "allowed",
        "unknown_scope",
        "other_assignment",
        "allowed",
        "unknown_scope",
    ]
    assert events[0]["run_id"] == "run-1" and events[0]["parent_run_id"] == "parent-1"
    assert events[3]["run_id"] == "run-2" and events[3]["parent_run_id"] == "parent-2"
    assert events[1]["decision"] == events[2]["decision"] == events[4]["decision"] == "denied"
    assert events[0]["requested_scope"] == "scope-1"
    assert "requested_scope" not in events[1]


def test_writer_and_repair_envelopes_expose_only_assigned_meeting_scope():
    coordinator = harness._Coordinator(_spec("meeting", unit_count=2), object())
    writer = coordinator.assignments["write-001"]
    assert json.loads(coordinator.server_envelope(writer).split("SERVER_ASSIGNMENT=", 1)[1])[
        "source_scopes"
    ] == [
        "scope-1"
    ]

    repair = replace(
        writer,
        work_unit_id="repair-001",
        phase="repair",
    )
    assert json.loads(coordinator.server_envelope(repair).split("SERVER_ASSIGNMENT=", 1)[1])[
        "source_scopes"
    ] == [
        "scope-1"
    ]

    reviewer = replace(
        writer,
        work_unit_id="review-1",
        phase="review_initial",
        role=harness.REVIEWER_ROLE,
        unit=None,
    )
    assert json.loads(coordinator.server_envelope(reviewer).split("SERVER_ASSIGNMENT=", 1)[1])[
        "source_scopes"
    ] == [
        "scope-1",
        "scope-2",
    ]


def test_reviewer_skips_sentinel_sources_but_assembly_keeps_sentinel_result():
    scopes = {
        "deal_reports[0]": {
            "sales_deal_id": str(UUID("00000000-0000-0000-0000-000000000001")),
            "required_evidence_ids": ["S0001"],
        },
        "deal_reports[1]": {
            "sales_deal_id": str(UUID("00000000-0000-0000-0000-000000000002")),
            "required_evidence_ids": [],
        },
        "common_report": {"required_evidence_ids": ["S0002"]},
    }
    coordinator = harness._Coordinator(
        replace(_spec("meeting"), source=scopes), object()
    )
    reviewer = harness._Assignment(
        "review-1",
        "review_initial",
        harness.REVIEWER_ROLE,
        draft_version=1,
        review_round=1,
        locations=frozenset({"deal_reports[0].body", "common_report.body"}),
    )
    envelope = json.loads(coordinator.server_envelope(reviewer).split("SERVER_ASSIGNMENT=", 1)[1])
    assert envelope["source_scopes"] == ["common_report", "deal_reports[0]"]
    calls = [
        {"name": "read_meeting_evidence", "args": {"scope": "deal_reports[0]"}},
        {"name": "read_meeting_evidence", "args": {"scope": "common_report"}},
        {"name": "read_validated_draft", "args": {"draft_version": 1}},
        {"name": "read_writer_plans", "args": {"draft_version": 1}},
    ]
    assert coordinator.sources_complete(reviewer, calls)
    assert not coordinator.sources_complete(reviewer, calls[:1])
    assembled = meeting_report._assemble(
        scopes,
        {
            "deal_reports[0]": meeting_report._DealDraft(title="A", body="A"),
            "deal_reports[1]": meeting_report._DealDraft(
                title=meeting_report.NO_DEAL_EVIDENCE_TEXT,
                body=meeting_report.NO_DEAL_EVIDENCE_TEXT,
            ),
            "common_report": meeting_report._SectionDraft(body="공통"),
        },
    )
    assert assembled.deal_reports[1].body == meeting_report.NO_DEAL_EVIDENCE_TEXT


def test_writer_meeting_readers_bind_scope_server_side_and_reject_scope_argument():
    payload = {
        "source": {
            "scope-1": {
                "evidence": [{"id": "E1"}],
                "attachments": [],
                "required_evidence_ids": ["E1"],
            },
            "scope-2": {
                "evidence": [{"id": "E2"}],
                "attachments": [],
                "required_evidence_ids": ["E2"],
            },
        }
    }
    evidence = create_scoped_meeting_tools(
        payload, assigned_scope=lambda _tool_name: "scope-1", reviewer=False
    )[0]
    graph = harness.create_agent(
        FakeMessagesListChatModel(responses=[AIMessage(content="done")]), tools=[evidence]
    )
    exposed = graph.nodes["tools"].bound._tools_by_name["read_meeting_evidence"]
    assert "scope" not in exposed.args_schema.model_fields
    assert exposed.args_schema.model_json_schema()["properties"] == {}
    assert asyncio.run(exposed.ainvoke({}))["evidence"] == [{"id": "E1"}]
    with pytest.raises(ValidationError):
        asyncio.run(exposed.ainvoke({"scope": "scope-2"}))


def test_all_runtime_markdown_files_are_accounted_for():
    paths = {
        path.removeprefix("/skills/")
        for role in harness.REPORT_ROLES
        for path in harness.skill_files(role)
    }
    actual = {
        path.relative_to(harness.SKILL_ROOT).as_posix() for path in harness.SKILL_ROOT.rglob("*.md")
    }
    assert len(paths) == 6
    assert paths == actual
