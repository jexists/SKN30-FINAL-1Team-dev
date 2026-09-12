"""요청당 하나의 DeepAgents Supervisor와 검증된 보고서 artifact 경계."""

import asyncio
import copy
import hashlib
import json
import operator
import re
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import reduce
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any

from deepagents import FilesystemMiddleware, create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from deepagents.middleware.skills import SkillsMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, before_model
from langchain.agents.structured_output import StructuredOutputError, ToolStrategy
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from langsmith import tracing_context
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, model_validator

from app.agents.reports.meeting_tools import create_scoped_meeting_tools
from app.agents.reports.period_sources import create_period_tools
from app.services.agent_logging import (
    agent_log_context,
    log_agent_error,
    log_agent_event,
    safe_report_scope,
)
from app.services.agent_stream import publish_progress
from app.services.llm import (
    LLMError,
    configured_chat_model,
    is_transient_llm_error,
    llm_boundary_error_code,
    safe_token_usage,
)

REPORT_TIMEOUT_SECONDS = 1_200
REPORT_TASK_MODEL_CALL_LIMIT = 6
REPORT_TASK_RECURSION_LIMIT = 16
REVIEWER_ROLE = "report-reviewer"
SKILL_ROOT = Path(__file__).parent / "skills"
REPORT_WRITER_ROLES = {
    "meeting": "sales-meeting-report",
    "daily": "daily-report-writer",
    "weekly": "weekly-report-writer",
    "monthly": "monthly-report-writer",
}
REPORT_ROLES = frozenset(REPORT_WRITER_ROLES.values())
_WORK_ID = re.compile(r"(?m)^work_unit_id=([a-z0-9-]+)\s*$")


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=1, max_length=200, pattern=r"\S")
    intent: str = Field(min_length=1, max_length=500, pattern=r"\S")
    evidence: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _check_evidence(self):
        if any(not value.strip() or len(value) > 200 for value in self.evidence):
            raise ValueError("report_plan_evidence_invalid")
        return self


class WriterArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_unit_id: str = Field(min_length=1, max_length=100, pattern=r"[a-z0-9-]+")
    base_draft_version: int = Field(ge=0, le=1)
    review_round: int | None = Field(default=None, ge=1, le=1)
    plan: list[PlanItem] = Field(min_length=1, max_length=250)
    draft: dict[str, Any]

    @model_validator(mode="after")
    def _check_version(self):
        if (self.base_draft_version == 0) != (self.review_round is None):
            raise ValueError("report_writer_version_invalid")
        if not self.draft:
            raise ValueError("report_draft_empty")
        return self


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(min_length=1, max_length=200, pattern=r"\S")
    evidence: str = Field(min_length=1, max_length=1_000, pattern=r"\S")
    action: str = Field(min_length=1, max_length=1_000, pattern=r"\S")


class ReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_version: int = Field(ge=1, le=2)
    review_round: int = Field(ge=1, le=1)
    issues: list[ReviewIssue] = Field(max_length=250)


@dataclass(frozen=True)
class WorkUnit:
    work_unit_id: str
    scope: str
    schema: type[BaseModel]
    locations: frozenset[str]
    evidence_refs: frozenset[str]
    output_shape: str
    sales_deal_id: str | None = None


@dataclass(frozen=True)
class WorkflowSpec:
    report_kind: str
    writer_role: str
    stage: str
    instructions: str
    source: dict[str, Any]
    units: tuple[WorkUnit, ...]
    prefilled_sections: dict[str, BaseModel]
    assemble: Callable[[dict[str, BaseModel]], BaseModel]
    validate_draft: Callable[[BaseModel], None]
    validate_unit: Callable[[WorkUnit, BaseModel, BaseModel | None, frozenset[str]], None]
    on_draft: Callable[[int, BaseModel], None] = lambda _version, _draft: None
    source_count: int = 0


@dataclass(frozen=True)
class WorkflowResult:
    draft: BaseModel
    selected_version: int
    degraded: bool
    task_count: int
    review_count: int
    repair_count: int
    review_issues: tuple[ReviewIssue, ...] = ()
    review_incomplete: bool = False
    initial_review_conducted: bool = True
    repair_completed: bool | None = None

    @property
    def remaining_issues(self) -> tuple[ReviewIssue, ...]:
        """이전 호출자를 위한 별칭. 값은 수정 전 r1 검토 메모다."""
        return self.review_issues


@dataclass(frozen=True)
class _Assignment:
    work_unit_id: str
    phase: str
    role: str
    unit: WorkUnit | None = None
    draft_version: int | None = None
    review_round: int | None = None
    locations: frozenset[str] = frozenset()


_ACTIVE_ASSIGNMENT: ContextVar[tuple["_Coordinator", _Assignment] | None] = ContextVar(
    "report_active_assignment", default=None
)


class _Events(AsyncCallbackHandler):
    """실제 SDK 모델·도구 호출과 공급자 사용량만 요청 단위로 기록한다."""

    raise_error = True

    def __init__(self, stage: str, *, model_limit: int, tool_limit: int, task_limit: int):
        self.stage = stage
        self.model_limit = model_limit
        self.tool_limit = tool_limit
        self.task_limit = task_limit
        self.calls = self.tools = self.delegations = 0
        self.started: dict[Any, float] = {}

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        if self.calls >= self.model_limit:
            raise LLMError("report_generation_limit")
        self.calls += 1
        self.started[run_id] = perf_counter()
        active = _ACTIVE_ASSIGNMENT.get()
        log_agent_event(
            self.stage + ".model_started",
            model_call_count=self.calls,
            reason_code=active[1].phase if active else "supervisor",
        )

    async def on_tool_start(self, serialized, input_str, **kwargs):
        if self.tools >= self.tool_limit:
            raise LLMError("report_generation_limit")
        self.tools += 1
        if serialized.get("name") == "task":
            if self.delegations >= self.task_limit:
                raise LLMError("report_generation_limit")
            self.delegations += 1

    async def on_llm_end(self, response, *, run_id, **kwargs):
        usage = safe_token_usage((response.llm_output or {}).get("token_usage"))
        if not usage:
            for generations in response.generations:
                if generations:
                    for key, value in safe_token_usage(
                        getattr(getattr(generations[0], "message", None), "usage_metadata", None)
                    ).items():
                        usage[key] = usage.get(key, 0) + value
        started = self.started.pop(run_id, perf_counter())
        log_agent_event(
            self.stage + ".model_completed",
            elapsed_ms=round((perf_counter() - started) * 1000),
            **usage,
        )

    async def on_llm_error(self, error, *, run_id, **kwargs):
        started = self.started.pop(run_id, perf_counter())
        log_agent_event(
            self.stage + ".model_failed",
            elapsed_ms=round((perf_counter() - started) * 1000),
        )


def skill_files(role: str) -> dict[str, dict[str, Any]]:
    """호스트 전체가 아닌 코드가 지정한 공통/역할 MD만 가상 파일로 제공한다."""
    if role not in REPORT_ROLES:
        raise ValueError("report_role_invalid")
    paths = ["report-style/SKILL.md", f"{role}/SKILL.md"]
    if role == "sales-meeting-report":
        paths.append(f"{role}/references/examples.md")
    return {
        f"/skills/{path}": create_file_data((SKILL_ROOT / path).read_text(encoding="utf-8"))
        for path in paths
    }


def _clone_model(value: BaseModel) -> BaseModel:
    return type(value).model_validate(value.model_dump(mode="json"))


def _runtime_error(error: Exception) -> Exception:
    if isinstance(error, (ValidationError, StructuredOutputError)):
        return LLMError("llm_output_schema_mismatch")
    if isinstance(error, (LLMError, ValueError, PermissionError)):
        return error
    if code := llm_boundary_error_code(error):
        return LLMError(code)
    if isinstance(error, TimeoutError):
        return LLMError("report_generation_timeout")
    if isinstance(error, GraphRecursionError):
        return LLMError("report_generation_limit")
    return error


def _safe_section_validation_fields(
    error: ValidationError, section: type[BaseModel], value: Any
) -> dict[str, str]:
    """Record schema mismatch shape without recording generated text or arbitrary keys."""
    declared = set(section.model_fields)
    missing: list[str] = []
    paths: list[str] = []
    for item in error.errors(include_input=False, include_context=False, include_url=False):
        loc = item.get("loc", ())
        parts = []
        for part in loc:
            if isinstance(part, int):
                parts.append(str(part))
            elif part in declared:
                parts.append(part)
            else:
                parts.append("key#" + hashlib.sha256(str(part).encode()).hexdigest()[:12])
        path = ".".join(parts)
        paths.append(path)
        if item.get("type") == "missing":
            missing.append(path)
    actual = value if isinstance(value, dict) else {}
    known = sorted(key for key in actual if key in declared)
    unknown = sorted(
        "key#" + hashlib.sha256(str(key).encode()).hexdigest()[:12]
        for key in actual
        if key not in declared
    )
    return {
        "validation_error_path": ",".join(paths),
        "validation_missing_fields": ",".join(sorted(missing)),
        "validation_actual_keys": ",".join(known + unknown),
        "validation_actual_types": ",".join(
            f"{key}:{type(actual[key]).__name__}" for key in known
        ),
        "validation_null_fields": ",".join(sorted(key for key in known if actual[key] is None)),
    }


def retain_valid_draft(error: Exception, *, stage: str) -> None:
    """생성·공급자·파싱·한도 실패만 복구한다. 권한·입력·무결성 오류는 전파한다."""
    code = str(error)
    if not isinstance(error, LLMError) or not (
        is_transient_llm_error(code)
        or code
        in {
            "llm_response_not_object",
            "llm_response_not_json",
            "empty_llm_output",
            "llm_output_schema_mismatch",
            "report_output_invalid",
            "report_generation_timeout",
            "report_generation_limit",
            "report_generation_failed",
        }
    ):
        raise error
    log_agent_event(stage, outcome="degraded", reason_code="valid_draft_fallback")
    log_agent_error(error, stage=stage)


class _Coordinator:
    def __init__(self, spec: WorkflowSpec, backend: StateBackend):
        if REPORT_WRITER_ROLES.get(spec.report_kind) != spec.writer_role:
            raise ValueError("report_role_invalid")
        if len({unit.work_unit_id for unit in spec.units}) != len(spec.units):
            raise ValueError("report_work_unit_duplicate")
        self.spec = spec
        self.backend = backend
        self.units = {unit.work_unit_id: unit for unit in spec.units}
        self.sections = {key: _clone_model(value) for key, value in spec.prefilled_sections.items()}
        self.initial_artifacts: dict[str, WriterArtifact] = {}
        self.repair_artifacts: dict[str, WriterArtifact] = {}
        self.repair_sections: dict[str, BaseModel] = {}
        self.drafts: dict[int, BaseModel] = {}
        self.reviews: dict[int, ReportReview] = {}
        self.artifact_values: dict[str, Any] = {}
        self.assignments: dict[str, _Assignment] = {
            unit.work_unit_id: _Assignment(
                work_unit_id=unit.work_unit_id,
                phase="write_initial",
                role=spec.writer_role,
                unit=unit,
                locations=unit.locations,
            )
            for unit in spec.units
        }
        self.reserved: set[str] = set()
        self.finished_assignments: set[str] = set()
        self.failed_assignments: set[str] = set()
        self.call_assignments: dict[str, _Assignment] = {}
        self.revised_locations: set[str] = set()
        self.phase = "write_initial" if self.assignments else "review_initial"
        self.eligible_versions: set[int] = set()
        self.final_version: int | None = None
        self.degraded = False
        self.review_incomplete = False
        self.task_count = self.review_count = self.repair_count = 0
        self.lock = asyncio.Lock()
        self.seed_files: dict[str, dict[str, Any]] = {}
        if not self.assignments:
            self._assemble(1, persist=False)

    @property
    def max_tasks(self) -> int:
        return len(self.spec.units) * 2 + 1

    @property
    def has_valid_draft(self) -> bool:
        return bool(self.drafts)

    @property
    def latest_version(self) -> int:
        if not self.drafts:
            raise LLMError("report_generation_failed")
        return max(self.drafts)

    def _persist(self, path: str, value: Any, *, live: bool = True) -> None:
        normalized = copy.deepcopy(value)
        self.artifact_values[path] = normalized
        data = create_file_data(
            json.dumps(normalized, ensure_ascii=False, default=str, separators=(",", ":"))
        )
        if not live:
            self.seed_files[path] = data
            return
        result = self.backend.write(path, data["content"])
        if result.error is not None:
            raise PermissionError("report_artifact_write_failed")

    def _plans(self, version: int) -> list[dict[str, Any]]:
        values = []
        for unit in self.spec.units:
            repair_id = f"repair-{unit.work_unit_id.removeprefix('write-')}"
            artifact = self.repair_artifacts.get(repair_id) if version == 2 else None
            artifact = artifact or self.initial_artifacts.get(unit.work_unit_id)
            if artifact is not None:
                values.append(
                    {
                        "scope": unit.scope,
                        "work_unit_id": artifact.work_unit_id,
                        "plan": [item.model_dump(mode="json") for item in artifact.plan],
                    }
                )
        return values

    def _assemble(
        self,
        version: int,
        *,
        sections: dict[str, BaseModel] | None = None,
        persist: bool = True,
    ) -> None:
        source_sections = self.sections if sections is None else sections
        candidate = self.spec.assemble(
            {key: _clone_model(value) for key, value in source_sections.items()}
        )
        try:
            self.spec.validate_draft(candidate)
        except (TypeError, ValueError, ValidationError) as error:
            raise LLMError("report_output_invalid") from error
        candidate = _clone_model(candidate)
        self._persist(
            f"/artifacts/drafts/v{version}.json",
            {"draft_version": version, "draft": candidate.model_dump(mode="json")},
            live=persist,
        )
        self._persist(
            f"/artifacts/plans/v{version}.json",
            {"draft_version": version, "plans": self._plans(version)},
            live=persist,
        )
        self.drafts[version] = candidate
        self.sections = {key: _clone_model(value) for key, value in source_sections.items()}
        if version == 1:
            self.eligible_versions = {1}
        self.spec.on_draft(version, _clone_model(candidate))
        if version == 1:
            self.assignments = {
                "review-1": _Assignment(
                    work_unit_id="review-1",
                    phase="review_initial",
                    role=REVIEWER_ROLE,
                    draft_version=1,
                    review_round=1,
                    locations=frozenset(
                        location for unit in self.spec.units for location in unit.locations
                    ),
                )
            }
            self.phase = "review_initial"
            publish_progress("report_review", review_attempt=1, review_limit=1)
        else:
            self.assignments = {}
            self.phase = "finish"
            self.eligible_versions = {2}

    def _available(self) -> list[_Assignment]:
        return [
            assignment
            for key, assignment in self.assignments.items()
            if key not in self.reserved and key not in self.finished_assignments
        ]

    def public_state(self, *, issues: list[ReviewIssue] | None = None) -> dict[str, Any]:
        return {
            "report_kind": self.spec.report_kind,
            "next_phase": self.phase,
            "next_work_units": [
                {
                    "work_unit_id": item.work_unit_id,
                    "subagent_type": item.role,
                    "phase": item.phase,
                    **({"scope": item.unit.scope} if item.unit else {}),
                    "allowed_locations": sorted(item.locations),
                    **(
                        {"draft_version": item.draft_version, "review_round": item.review_round}
                        if item.draft_version
                        else {}
                    ),
                }
                for item in self._available()
            ],
            "eligible_versions": sorted(self.eligible_versions),
            **(
                {"issues": [issue.model_dump(mode="json") for issue in issues]}
                if issues is not None
                else {}
            ),
        }

    def _work_id(self, description: Any) -> str:
        if not isinstance(description, str) or len(description) > 4_000:
            raise PermissionError("report_task_description_invalid")
        matches = _WORK_ID.findall(description)
        remaining = _WORK_ID.sub("", description).strip()
        if len(matches) != 1 or len(remaining) < 20:
            raise PermissionError("report_task_description_invalid")
        return matches[0]

    def reserve(self, calls: list[dict[str, Any]]) -> None:
        if not calls:
            raise LLMError("report_generation_failed")
        if len(calls) != 1:
            raise PermissionError("report_supervisor_action_invalid")
        call = calls[0]
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise PermissionError("report_supervisor_action_invalid")
        if self.phase == "finish":
            if call.get("name") != "finish_report":
                raise PermissionError("report_supervisor_action_invalid")
            args = call.get("args", {})
            if (
                set(args) != {"candidate_version"}
                or args["candidate_version"] not in self.eligible_versions
            ):
                raise PermissionError("report_final_version_not_allowed")
            return
        if call.get("name") != "task":
            raise PermissionError("report_supervisor_action_invalid")
        args = call.get("args", {})
        if set(args) != {"description", "subagent_type"}:
            raise PermissionError("report_delegation_not_allowed")
        work_id = self._work_id(args["description"])
        assignment = self.assignments.get(work_id)
        if (
            assignment is None
            or assignment.phase != self.phase
            or assignment.role != args["subagent_type"]
            or work_id in self.reserved
            or work_id in self.finished_assignments
        ):
            raise PermissionError("report_delegation_not_allowed")
        self.reserved.add(work_id)
        self.call_assignments[call_id] = assignment
        self.task_count += 1
        if assignment.phase.startswith("review"):
            self.review_count += 1
        elif assignment.phase == "repair":
            self.repair_count += 1
        try:
            log_agent_event(
                self.spec.stage + ".assignment_reserved",
                outcome="reserved",
                **self.assignment_log_fields(assignment),
            )
        except Exception:
            pass

    def assignment_for_call(self, tool_call_id: str) -> _Assignment:
        try:
            return self.call_assignments[tool_call_id]
        except KeyError:
            raise PermissionError("report_delegation_not_allowed") from None

    def server_envelope(self, assignment: _Assignment) -> str:
        unit = assignment.unit
        payload = {
            "work_unit_id": assignment.work_unit_id,
            "report_kind": self.spec.report_kind,
            "phase": assignment.phase,
            "role": assignment.role,
            "draft_version": assignment.draft_version,
            "review_round": assignment.review_round,
            "scope": unit.scope if unit else None,
            "sales_deal_id": unit.sales_deal_id if unit else None,
            "allowed_locations": sorted(assignment.locations or (unit.locations if unit else ())),
            "allowed_plan_evidence": sorted(unit.evidence_refs) if unit else [],
            # A writer/repair task gets only its assigned source in the
            # transport contract; reviewers retain the full frozen set.
            "source_scopes": (
                sorted(self.all_meeting_scopes)
                if self.spec.report_kind == "meeting" and assignment.role == REVIEWER_ROLE
                else [unit.scope]
                if self.spec.report_kind == "meeting" and unit is not None
                else []
            ),
            "source_ids": [item["source_id"] for item in self.spec.source.get("source_units", [])]
            if self.spec.report_kind != "meeting"
            else [],
            "output_shape": unit.output_shape if unit else "ReportReview",
        }
        return "\n\nSERVER_ASSIGNMENT=" + json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        )

    @staticmethod
    def _assignment_kind(assignment: _Assignment) -> str:
        if assignment.phase == "repair":
            return "repair"
        if assignment.role == REVIEWER_ROLE:
            return "review"
        return "write"

    def assignment_log_fields(self, assignment: _Assignment) -> dict[str, Any]:
        allowed = (
            self.all_meeting_scopes
            if self.spec.report_kind == "meeting" and assignment.role == REVIEWER_ROLE
            else frozenset({assignment.unit.scope})
            if self.spec.report_kind == "meeting" and assignment.unit is not None
            else frozenset(item["source_id"] for item in self.spec.source.get("source_units", []))
        )
        existing = (
            self.all_meeting_scopes
            if self.spec.report_kind == "meeting"
            else frozenset(item["source_id"] for item in self.spec.source.get("source_units", []))
        )
        return {
            "report_kind": self.spec.report_kind,
            "assignment_id": assignment.work_unit_id,
            "work_unit_id": assignment.work_unit_id,
            "assignment_kind": self._assignment_kind(assignment),
            "assignment_phase": assignment.phase,
            "allowed_scopes": allowed,
            "existing_scopes": existing,
        }

    def meeting_scope_access(self, tool_name: str, scope: object) -> bool:
        active = _ACTIVE_ASSIGNMENT.get()
        existing = self.all_meeting_scopes
        if active is None:
            allowed, reason = frozenset(), "context_missing"
        elif active[0] is not self:
            allowed, reason = frozenset(), "other_assignment_context"
        else:
            assignment = active[1]
            allowed = (
                existing
                if assignment.role == REVIEWER_ROLE
                else (
                    frozenset({assignment.unit.scope})
                    if assignment.unit is not None
                    else frozenset()
                )
            )
            reason = (
                "allowed"
                if scope in allowed
                else "unknown_scope"
                if scope not in existing
                else "other_assignment"
            )
        decision = scope in allowed
        fields = {
            "tool_name": tool_name,
            "allowed_scopes": allowed,
            "existing_scopes": existing,
            "decision": "allowed" if decision else "denied",
            "reason_code": reason,
            **safe_report_scope(scope, existing),
        }
        if active is not None and active[0] is self:
            fields.update(self.assignment_log_fields(active[1]))
        try:
            log_agent_event(self.spec.stage + ".scope_guard", **fields)
        except Exception:
            pass
        return decision

    def allow_meeting_scope(self, scope: str) -> bool:
        active = _ACTIVE_ASSIGNMENT.get()
        if active is None or active[0] is not self:
            return False
        assignment = active[1]
        if assignment.role == REVIEWER_ROLE:
            return scope in self.all_meeting_scopes
        return assignment.unit is not None and assignment.unit.scope == scope

    def assigned_meeting_scope(self, tool_name: str) -> str | None:
        """writer/repair reader가 현재 서버 assignment scope만 사용하게 한다."""
        active = _ACTIVE_ASSIGNMENT.get()
        if active is None or active[0] is not self:
            return None
        assignment = active[1]
        if assignment.role == REVIEWER_ROLE or assignment.unit is None:
            return None
        return assignment.unit.scope

    def period_source_access(self, tool_name: str, source_id: object) -> bool:
        existing = frozenset(
            item["source_id"] for item in self.spec.source.get("source_units", [])
        )
        active = _ACTIVE_ASSIGNMENT.get()
        if active is None:
            allowed, reason = frozenset(), "context_missing"
        elif active[0] is not self:
            allowed, reason = frozenset(), "other_assignment_context"
        else:
            allowed = existing
            reason = "allowed" if source_id is None or source_id in existing else "unknown_scope"
        decision = source_id is None or source_id in allowed
        fields = {
            "report_kind": self.spec.report_kind,
            "tool_name": tool_name,
            "allowed_scopes": allowed,
            "existing_scopes": existing,
            "decision": "allowed" if decision else "denied",
            "reason_code": reason,
        }
        if source_id is not None:
            fields.update(safe_report_scope(source_id, existing))
        if active is not None and active[0] is self:
            fields.update(self.assignment_log_fields(active[1]))
        try:
            log_agent_event(self.spec.stage + ".scope_guard", **fields)
        except Exception:
            pass
        return decision

    @property
    def all_meeting_scopes(self) -> frozenset[str]:
        return frozenset(self.spec.source)

    def allowed_tools(
        self, assignment: _Assignment, source_names: set[str], output: str
    ) -> set[str]:
        allowed = {"read_file", output, *source_names}
        if assignment.phase in {"repair", "review_initial"}:
            allowed.add("read_validated_draft")
        if assignment.phase == "review_initial":
            allowed.add("read_writer_plans")
        if assignment.phase == "repair":
            allowed.add("read_validated_review")
        if (
            self.spec.report_kind == "meeting"
            and assignment.role != REVIEWER_ROLE
            and (assignment.unit is None or assignment.unit.sales_deal_id is None)
        ):
            allowed -= {"read_deal_crm", "read_previous_reports"}
        return allowed

    def sources_complete(self, assignment: _Assignment, calls: list[dict[str, Any]]) -> bool:
        if self.spec.report_kind == "meeting":
            expected = (
                self.all_meeting_scopes
                if assignment.role == REVIEWER_ROLE
                else frozenset({assignment.unit.scope})
                if assignment.unit
                else frozenset()
            )
            actual = {
                call["args"].get("scope")
                or (
                    assignment.unit.scope
                    if assignment.role != REVIEWER_ROLE and assignment.unit
                    else None
                )
                for call in calls
                if call["name"] == "read_meeting_evidence"
            }
            if not expected <= actual:
                return False
        else:
            if not any(call["name"] == "read_report_context" for call in calls):
                return False
            expected = {unit["source_id"] for unit in self.spec.source["source_units"]}
            reads = [call for call in calls if call["name"] == "read_report_sources"]
            actual = {call["args"].get("source_id") for call in reads}
            if None not in actual and not expected <= actual:
                return False
        required_artifacts: set[tuple[str, int]] = set()
        if assignment.phase == "repair":
            required_artifacts = {("read_validated_draft", 1), ("read_validated_review", 1)}
        elif assignment.phase == "review_initial":
            required_artifacts = {("read_validated_draft", 1), ("read_writer_plans", 1)}
        observed = {
            (
                call["name"],
                call["args"].get("draft_version", call["args"].get("review_round")),
            )
            for call in calls
        }
        return required_artifacts <= observed

    def _validate_plan(self, artifact: WriterArtifact, assignment: _Assignment) -> None:
        unit = assignment.unit
        if unit is None:
            raise PermissionError("report_work_unit_invalid")
        allowed_locations = assignment.locations or unit.locations
        planned_locations = [item.location for item in artifact.plan]
        if len(planned_locations) != len(set(planned_locations)) or set(planned_locations) != set(
            allowed_locations
        ):
            raise PermissionError("report_plan_scope_not_allowed")
        for item in artifact.plan:
            if (
                item.location not in allowed_locations
                or not set(item.evidence) <= unit.evidence_refs
            ):
                raise PermissionError("report_plan_scope_not_allowed")

    def _accept_writer(self, assignment: _Assignment, content: str) -> None:
        artifact = WriterArtifact.model_validate_json(content)
        expected_base = 1 if assignment.phase == "repair" else 0
        expected_round = 1 if assignment.phase == "repair" else None
        if (
            artifact.work_unit_id != assignment.work_unit_id
            or artifact.base_draft_version != expected_base
            or artifact.review_round != expected_round
        ):
            raise PermissionError("report_artifact_version_mismatch")
        self._validate_plan(artifact, assignment)
        assert assignment.unit is not None
        try:
            section = assignment.unit.schema.model_validate(artifact.draft)
        except ValidationError as error:
            log_agent_error(
                error,
                stage=f"{self.spec.stage}.output_validation",
                **_safe_section_validation_fields(error, assignment.unit.schema, artifact.draft),
            )
            raise LLMError("report_output_invalid") from error
        previous = (
            self.sections.get(assignment.unit.scope) if assignment.phase == "repair" else None
        )
        self.spec.validate_unit(assignment.unit, section, previous, assignment.locations)
        normalized = artifact.model_copy(update={"draft": section.model_dump(mode="json")})
        self._persist(
            f"/artifacts/writer/{assignment.work_unit_id}.json",
            normalized.model_dump(mode="json"),
        )
        if assignment.phase == "repair":
            self.repair_artifacts[assignment.work_unit_id] = normalized
            self.repair_sections[assignment.unit.scope] = section
            self.revised_locations.update(assignment.locations)
        else:
            self.initial_artifacts[assignment.work_unit_id] = normalized
            self.sections[assignment.unit.scope] = section

    def _accept_review(self, assignment: _Assignment, content: str) -> list[ReviewIssue]:
        review = ReportReview.model_validate_json(content)
        if (
            review.draft_version != assignment.draft_version
            or review.review_round != assignment.review_round
        ):
            raise PermissionError("report_artifact_version_mismatch")
        location_to_scope = {
            location: unit.scope for unit in self.spec.units for location in unit.locations
        }
        for issue in review.issues:
            if (
                issue.location not in location_to_scope
                or issue.location not in assignment.locations
            ):
                raise PermissionError("report_review_scope_not_allowed")
        self._persist(
            f"/artifacts/reviews/r{review.review_round}.json",
            review.model_dump(mode="json"),
        )
        self.reviews[review.review_round] = review
        if review.review_round == 1 and review.issues:
            scopes = {location_to_scope[issue.location] for issue in review.issues}
            repairs: dict[str, _Assignment] = {}
            for unit in self.spec.units:
                if unit.scope not in scopes:
                    continue
                work_id = f"repair-{unit.work_unit_id.removeprefix('write-')}"
                repairs[work_id] = _Assignment(
                    work_unit_id=work_id,
                    phase="repair",
                    role=self.spec.writer_role,
                    unit=unit,
                    draft_version=1,
                    review_round=1,
                    locations=frozenset(
                        issue.location
                        for issue in review.issues
                        if location_to_scope[issue.location] == unit.scope
                    ),
                )
            if not repairs:
                raise PermissionError("report_review_scope_not_allowed")
            self.assignments = repairs
            self.phase = "repair"
            publish_progress("report_writing", review_attempt=1, review_limit=1)
        elif review.review_round == 1:
            self.assignments = {}
            self.phase = "finish"
            self.eligible_versions = {1}
        return review.issues

    def _advance_after_writer(self, assignment: _Assignment) -> None:
        phase_assignments = {
            key for key, item in self.assignments.items() if item.phase == assignment.phase
        }
        if not phase_assignments <= self.finished_assignments:
            return
        if assignment.phase == "write_initial":
            self._assemble(1)
            return
        if self.repair_artifacts:
            try:
                self._assemble(2, sections={**self.sections, **self.repair_sections})
            except Exception as error:
                retain_valid_draft(
                    _runtime_error(error), stage=f"{self.spec.stage}.repair_assembly"
                )
                self.assignments = {}
                self.phase = "finish"
                self.eligible_versions = {1}
                self.degraded = True
                self.review_incomplete = True
        else:
            self.assignments = {}
            self.phase = "finish"
            self.eligible_versions = {1}
            self.degraded = True
            self.review_incomplete = True

    async def accept(self, assignment: _Assignment, content: str) -> dict[str, Any]:
        async with self.lock:
            if assignment.work_unit_id in self.finished_assignments:
                raise PermissionError("report_delegation_not_allowed")
            issues: list[ReviewIssue] | None = None
            if assignment.role == REVIEWER_ROLE:
                issues = self._accept_review(assignment, content)
            else:
                self._accept_writer(assignment, content)
            self.finished_assignments.add(assignment.work_unit_id)
            if assignment.role != REVIEWER_ROLE:
                self._advance_after_writer(assignment)
            return {
                "status": "accepted",
                "work_unit_id": assignment.work_unit_id,
                "artifact_path": (
                    f"/artifacts/reviews/r{assignment.review_round}.json"
                    if assignment.role == REVIEWER_ROLE
                    else f"/artifacts/writer/{assignment.work_unit_id}.json"
                ),
                **self.public_state(issues=issues),
            }

    async def fail(self, assignment: _Assignment, error: Exception) -> dict[str, Any]:
        async with self.lock:
            retain_valid_draft(error, stage=f"{self.spec.stage}.{assignment.phase}")
            self.degraded = True
            self.finished_assignments.add(assignment.work_unit_id)
            self.failed_assignments.add(assignment.work_unit_id)
            if assignment.phase == "review_initial":
                self.assignments = {}
                self.phase = "finish"
                self.eligible_versions = {1}
                self.review_incomplete = True
            elif assignment.phase == "repair":
                self.review_incomplete = True
                self._advance_after_writer(assignment)
            else:
                raise error
            return {
                "status": "degraded",
                "work_unit_id": assignment.work_unit_id,
                "reason_code": str(error),
                **self.public_state(),
            }

    def finish(self, candidate_version: int) -> dict[str, Any]:
        if self.phase != "finish" or candidate_version not in self.eligible_versions:
            raise PermissionError("report_final_version_not_allowed")
        self.final_version = candidate_version
        if candidate_version < self.latest_version:
            self.degraded = True
        self._persist(
            "/artifacts/final.json",
            {"draft_version": candidate_version, "degraded": self.degraded},
        )
        return {"status": "selected", "draft_version": candidate_version}

    def fallback(self, error: Exception) -> WorkflowResult:
        retain_valid_draft(error, stage=f"{self.spec.stage}.supervisor")
        self.degraded = True
        if not self.drafts:
            raise error
        self.final_version = self.latest_version
        self.review_incomplete = True
        return self.result()

    def _review_issues(self) -> tuple[ReviewIssue, ...]:
        initial = self.reviews.get(1)
        return tuple(initial.issues) if initial else ()

    def _repair_completed(self) -> bool | None:
        initial = self.reviews.get(1)
        if initial is None or not initial.issues:
            return None
        return 2 in self.drafts and not any(
            work_id.startswith("repair-") for work_id in self.failed_assignments
        )

    def result(self) -> WorkflowResult:
        if self.final_version is None:
            raise LLMError("report_generation_failed")
        return WorkflowResult(
            draft=_clone_model(self.drafts[self.final_version]),
            selected_version=self.final_version,
            degraded=self.degraded,
            task_count=self.task_count,
            review_count=self.review_count,
            repair_count=self.repair_count,
            review_issues=self._review_issues(),
            review_incomplete=self.review_incomplete,
            initial_review_conducted=1 in self.reviews,
            repair_completed=self._repair_completed(),
        )

    def artifact(self, kind: str, version: int) -> dict[str, Any]:
        active = _ACTIVE_ASSIGNMENT.get()
        if active is None or active[0] is not self:
            raise PermissionError("report_artifact_not_allowed")
        assignment = active[1]
        allowed = {
            "repair": {("draft", 1), ("review", 1)},
            "review_initial": {("draft", 1), ("plans", 1)},
        }.get(assignment.phase, set())
        if (kind, version) not in allowed:
            raise PermissionError("report_artifact_not_allowed")
        path = {
            "draft": f"/artifacts/drafts/v{version}.json",
            "plans": f"/artifacts/plans/v{version}.json",
            "review": f"/artifacts/reviews/r{version}.json",
        }[kind]
        result = self.backend.read(path, offset=0, limit=2)
        if result.error is not None or result.file_data is None:
            raise ValueError("report_artifact_missing")
        try:
            value = json.loads(result.file_data["content"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("report_artifact_invalid") from None
        if value != self.artifact_values.get(path):
            raise PermissionError("report_artifact_invalid")
        if assignment.phase == "repair" and kind == "draft" and assignment.unit is not None:
            if self.spec.report_kind == "meeting":
                return {
                    "draft_version": version,
                    "scope": assignment.unit.scope,
                    "draft": self.sections[assignment.unit.scope].model_dump(mode="json"),
                }
            return {
                "draft_version": version,
                "draft": self.drafts[version].model_dump(mode="json"),
            }
        if assignment.phase == "repair" and kind == "review" and assignment.unit is not None:
            review = self.reviews[version]
            return {
                "draft_version": review.draft_version,
                "review_round": review.review_round,
                "issues": [
                    issue.model_dump(mode="json")
                    for issue in review.issues
                    if issue.location in assignment.locations
                ],
            }
        return copy.deepcopy(value)


class _ChildGuard(AgentMiddleware):
    """도구 허용과 필수 읽기를 각 task의 메시지 기록에서 검증한다."""

    def __init__(
        self,
        coordinator: _Coordinator,
        files: dict[str, dict[str, Any]],
        source_tools: list[Callable],
        output_schema: type[BaseModel],
        role: str,
    ):
        self.coordinator = coordinator
        self.files = files
        self.required_skills = {path for path in files if path.endswith("/SKILL.md")}
        self.source_names = {
            getattr(tool, "__name__", getattr(tool, "name", "")) for tool in source_tools
        }
        self.output_name = output_schema.__name__
        self.role = role

    def _active(self) -> _Assignment:
        active = _ACTIVE_ASSIGNMENT.get()
        if active is None or active[0] is not self.coordinator or active[1].role != self.role:
            raise PermissionError("report_task_context_invalid")
        return active[1]

    @staticmethod
    def _successful_calls(messages: list[Any]) -> list[dict[str, Any]]:
        by_id = {
            call["id"]: call
            for message in messages
            for call in getattr(message, "tool_calls", [])
            if isinstance(call, dict) and isinstance(call.get("id"), str)
        }
        return [
            by_id[message.tool_call_id]
            for message in messages
            if isinstance(message, ToolMessage)
            and message.tool_call_id in by_id
            and getattr(message, "status", "success") != "error"
            and not (isinstance(message.content, str) and message.content.startswith("Error:"))
        ]

    def _skills_complete(self, calls: list[dict[str, Any]]) -> bool:
        read = set()
        for call in calls:
            if call["name"] != "read_file":
                continue
            args = call["args"]
            path = args.get("file_path")
            if (
                path in self.required_skills
                and args.get("offset", 0) == 0
                and args.get("limit", 2000) >= len(self.files[path]["content"].splitlines())
            ):
                read.add(path)
        return read == self.required_skills

    async def awrap_model_call(self, request, handler):
        assignment = self._active()
        messages = request.state.get("messages", [])
        if (
            sum(isinstance(message, AIMessage) for message in messages)
            >= REPORT_TASK_MODEL_CALL_LIMIT
        ):
            raise LLMError("report_generation_limit")
        discovered = {item["path"] for item in request.state.get("skills_metadata", [])}
        if discovered != self.required_skills:
            raise LLMError("report_generation_failed")
        allowed = self.coordinator.allowed_tools(assignment, self.source_names, self.output_name)
        previous = self._successful_calls(messages)
        output_available = self._skills_complete(previous) and self.coordinator.sources_complete(
            assignment, previous
        )
        response = await handler(
            request.override(
                tools=[tool for tool in request.tools if tool.name in allowed],
                response_format=request.response_format if output_available else None,
            )
        )
        calls = [call for message in response.result for call in getattr(message, "tool_calls", [])]
        if not calls:
            raise LLMError("report_generation_failed")
        signatures = {
            (call["name"], json.dumps(call.get("args", {}), sort_keys=True, default=str))
            for call in calls
        }
        if len(signatures) != len(calls):
            raise LLMError("report_generation_limit")
        previous_signatures = {
            (call["name"], json.dumps(call.get("args", {}), sort_keys=True, default=str))
            for call in previous
        }
        for call in calls:
            signature = (
                call["name"],
                json.dumps(call.get("args", {}), sort_keys=True, default=str),
            )
            if call["name"] not in allowed:
                raise PermissionError("report_tool_not_allowed")
            if (
                self.coordinator.spec.report_kind == "meeting"
                and
                call["name"] in self.source_names
                and assignment.role != REVIEWER_ROLE
                and "scope" in call.get("args", {})
                and call.get("args", {}).get("scope")
                != self.coordinator.assigned_meeting_scope(call["name"])
            ):
                raise PermissionError("report_scope_not_allowed")
            if call["name"] == "read_file" and call["args"].get("file_path") not in self.files:
                raise PermissionError("report_file_not_allowed")
            if call["name"] != self.output_name and signature in previous_signatures:
                raise LLMError("report_generation_limit")
        outputs = [call for call in calls if call["name"] == self.output_name]
        if outputs and (
            len(outputs) != 1
            or len(calls) != 1
            or not self._skills_complete(previous)
            or not self.coordinator.sources_complete(assignment, previous)
        ):
            raise LLMError("report_generation_failed")
        return response


class _SupervisorGuard(AgentMiddleware):
    def __init__(self, coordinator: _Coordinator):
        self.coordinator = coordinator
        self.task_description = (
            "Call exactly one server-allowed work unit per turn. Preserve a useful task "
            "description and include one `work_unit_id=<id>` line. Available agents:\n"
            f"- {coordinator.spec.writer_role}: selected "
            f"{coordinator.spec.report_kind} report writer\n"
            f"- {REVIEWER_ROLE}: common report reviewer"
        )

    async def awrap_model_call(self, request, handler):
        allowed = {"task", "finish_report"}
        tools = []
        for tool in request.tools:
            if tool.name not in allowed:
                continue
            tools.append(
                tool.model_copy(update={"description": self.task_description})
                if tool.name == "task"
                else tool
            )
        response = await handler(request.override(tools=tools))
        calls = [call for message in response.result for call in getattr(message, "tool_calls", [])]
        if any(call["name"] not in allowed for call in calls):
            raise PermissionError("report_tool_not_allowed")
        self.coordinator.reserve(calls)
        return response

    @staticmethod
    def _tool_message(command: Command, tool_call_id: str) -> ToolMessage:
        update = command.update if isinstance(command.update, dict) else {}
        messages = update.get("messages", [])
        matches = [
            message
            for message in messages
            if isinstance(message, ToolMessage) and message.tool_call_id == tool_call_id
        ]
        if len(matches) != 1 or not isinstance(matches[0].content, str):
            raise LLMError("report_generation_failed")
        return matches[0]

    @staticmethod
    def _receipt(command: Command, tool_call_id: str, value: dict[str, Any]) -> Command:
        update = dict(command.update) if isinstance(command.update, dict) else {}
        update["messages"] = [
            ToolMessage(
                content=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                tool_call_id=tool_call_id,
                name="task",
            )
        ]
        return Command(update=update)

    async def awrap_tool_call(self, request, handler):
        call = request.tool_call
        if call["name"] == "finish_report":
            return await handler(request)
        if call["name"] != "task":
            raise PermissionError("report_tool_not_allowed")
        assignment = self.coordinator.assignment_for_call(call["id"])
        token = _ACTIVE_ASSIGNMENT.set((self.coordinator, assignment))
        assignment_fields = self.coordinator.assignment_log_fields(assignment)
        started = perf_counter()
        try:
            with agent_log_context(**assignment_fields):
                try:
                    log_agent_event(
                        self.coordinator.spec.stage + ".assignment_started", outcome="started"
                    )
                except Exception:
                    pass
                augmented = {
                    **call,
                    "args": {
                        **call["args"],
                        "description": call["args"]["description"]
                        + self.coordinator.server_envelope(assignment),
                        "subagent_type": (
                            "general-purpose"
                            if assignment.role == self.coordinator.spec.writer_role
                            else assignment.role
                        ),
                    },
                }
                try:
                    command = await handler(request.override(tool_call=augmented))
                    if not isinstance(command, Command):
                        raise LLMError("report_generation_failed")
                    message = self._tool_message(command, call["id"])
                    receipt = await self.coordinator.accept(assignment, message.content)
                except Exception as error:
                    normalized = _runtime_error(error)
                    try:
                        log_agent_error(
                            normalized,
                            stage=self.coordinator.spec.stage + ".assignment_failed",
                            error_code=(
                                str(normalized)
                                if str(normalized) in {
                                    "report_scope_not_allowed",
                                    "report_deal_not_allowed",
                                    "report_source_not_allowed",
                                }
                                else None
                            ),
                            elapsed_ms=round((perf_counter() - started) * 1000),
                        )
                    except Exception:
                        pass
                    if not self.coordinator.has_valid_draft:
                        raise normalized from None
                    receipt = await self.coordinator.fail(assignment, normalized)
                    command = Command(update={})
                else:
                    try:
                        log_agent_event(
                            self.coordinator.spec.stage + ".assignment_completed",
                            outcome="completed",
                            elapsed_ms=round((perf_counter() - started) * 1000),
                            fallback_selected=False,
                        )
                    except Exception:
                        pass
                return self._receipt(command, call["id"], receipt)
        finally:
            _ACTIVE_ASSIGNMENT.reset(token)


def _artifact_tools(coordinator: _Coordinator) -> list[Callable]:
    def read_validated_draft(draft_version: int) -> dict[str, Any]:
        """현재 task에 허용된 정확한 버전의 서버 검증 초안을 읽는다."""
        return coordinator.artifact("draft", draft_version)

    def read_writer_plans(draft_version: int) -> dict[str, Any]:
        """현재 검토 task에 허용된 초안 버전의 짧은 근거 계획을 읽는다."""
        return coordinator.artifact("plans", draft_version)

    def read_validated_review(review_round: int) -> dict[str, Any]:
        """현재 수정 task에 허용된 r1 검토 artifact를 읽는다."""
        return coordinator.artifact("review", review_round)

    return [read_validated_draft, read_writer_plans, read_validated_review]


def _child(
    *,
    model,
    backend: StateBackend,
    coordinator: _Coordinator,
    files: dict[str, dict[str, Any]],
    source_tools: list[Callable],
    role: str,
    reviewer: bool,
):
    schemas = tuple(dict.fromkeys(unit.schema for unit in coordinator.spec.units))
    draft_schema = reduce(operator.or_, schemas) if schemas else dict[str, Any]
    if len(schemas) > 1 and all("kind" in schema.model_fields for schema in schemas):
        draft_schema = Annotated[draft_schema, Field(discriminator="kind")]
    output = (
        ReportReview
        if reviewer
        else create_model("WriterArtifact", __base__=WriterArtifact, draft=(draft_schema, ...))
    )
    guard = _ChildGuard(coordinator, files, source_tools, output, role)
    prompt = (
        "REPORT_REVIEWER. 검증된 초안을 직접 고치지 말고 location/evidence/action issue만 반환한다."
        if reviewer
        else "REPORT_WRITER. 배정된 한 scope만 작성하거나 배정된 location만 수정한다."
    )
    prompt += (
        "\n두 SKILL.md를 read_file(offset=0, limit=1000)로 모두 읽고 적용한다. "
        "사실은 domain reader와 허용된 version artifact로만 확인한다. source_index나 task 설명은 "
        "사실 근거가 아니다. 짧은 근거 계획은 최종 본문이 아니라 WriterArtifact.plan에 둔다. "
        "writer는 SERVER_ASSIGNMENT의 ID/version을 그대로 쓰고 allowed_locations 각각을 plan에 "
        "정확히 한 번 포함한다. reviewer는 허용된 location만 지적한다. "
        "마지막에는 지정된 구조화 출력 도구를 호출한다."
    )
    prompt += "\n" + coordinator.spec.instructions
    return create_agent(
        model,
        tools=[*source_tools, *_artifact_tools(coordinator)],
        system_prompt=prompt,
        middleware=[
            FilesystemMiddleware(
                backend=backend,
                tools=["read_file"],
                tool_token_limit_before_evict=None,
                human_message_token_limit_before_evict=None,
            ),
            SkillsMiddleware(backend=backend, sources=["/skills/"]),
            guard,
        ],
        response_format=ToolStrategy(output),
        name=role,
    ).with_config(recursion_limit=REPORT_TASK_RECURSION_LIMIT)


async def _run_supervisor(spec: WorkflowSpec) -> WorkflowResult:
    """선택 writer/common reviewer를 한 번씩 compile하고 Supervisor를 한 번 호출한다."""
    backend = StateBackend()
    coordinator = _Coordinator(spec, backend)
    files = skill_files(spec.writer_role)
    if spec.report_kind == "meeting":
        writer_source_tools = create_scoped_meeting_tools(
            {"source": spec.source},
            scope_access=coordinator.meeting_scope_access,
            assigned_scope=coordinator.assigned_meeting_scope,
            reviewer=False,
        )
        reviewer_source_tools = create_scoped_meeting_tools(
            {"source": spec.source}, scope_access=coordinator.meeting_scope_access
        )
    else:
        writer_source_tools = reviewer_source_tools = create_period_tools(
            spec.source, scope_access=coordinator.period_source_access
        )
    model = configured_chat_model()
    writer = _child(
        model=model,
        backend=backend,
        coordinator=coordinator,
        files=files,
        source_tools=writer_source_tools,
        role=spec.writer_role,
        reviewer=False,
    )
    reviewer = _child(
        model=model,
        backend=backend,
        coordinator=coordinator,
        files=files,
        source_tools=reviewer_source_tools,
        role=REVIEWER_ROLE,
        reviewer=True,
    )
    # 0.7.11의 native dispatcher/private-state filtering을 유지하면서, 예약된 transport
    # 이름으로 자동 GP 생성을 막는다. guard가 모델의 실제 writer 이름을 이 key로 변환한다.
    transport_subagents = [
        {
            "name": "general-purpose",
            "description": f"서버가 선택한 {spec.report_kind} 보고서 scope 작성·1회 수정",
            "runnable": writer,
        },
        {
            "name": REVIEWER_ROLE,
            "description": "선택 kind의 공통 기준 1차 검토",
            "runnable": reviewer,
        },
    ]

    def finish_report(candidate_version: int) -> dict[str, Any]:
        """검토 흐름이 종료된 뒤 허용된 서버 검증 초안 버전을 최종 선택한다."""
        return coordinator.finish(candidate_version)

    @before_model(can_jump_to=["end"])
    def stop_after_finish(state, runtime):
        if coordinator.final_version is not None:
            return {"jump_to": "end"}

    supervisor = create_deep_agent(
        model=model,
        tools=[finish_report],
        backend=backend,
        subagents=transport_subagents,
        system_prompt=(
            "REPORT_SUPERVISOR. 서버가 이미 report_kind를 고정했다. 다음 허용 work unit을 task로 "
            "위임하고 검증된 receipt를 확인해 작성→1차 검토→지적 scope당 최대 1회 수정→"
            "finish_report 순서로 끝낸다. task 설명 첫 줄에 정확한 "
            "work_unit_id=<id>를 쓰고, 그 뒤에는 목적·검사할 결과·수정 이유를 구체적으로 적는다. "
            "보고서나 review를 직접 쓰지 말고 source를 요청하거나 추측하지 않는다. parent task는 "
            "매 turn 하나씩 순차 위임한다. 매 receipt의 최신 phase/allowlist를 다음 호출에 "
            "사용한다. 검증된 최신 허용 버전을 선택한다.\n\n" + spec.instructions
        ),
        middleware=[
            FilesystemMiddleware(
                backend=backend,
                tools=["read_file"],
                tool_token_limit_before_evict=None,
                human_message_token_limit_before_evict=None,
            ),
            _SupervisorGuard(coordinator),
            stop_after_finish,
        ],
        name="report-supervisor",
    )
    task_limit = coordinator.max_tasks
    model_limit = max(16, task_limit * (REPORT_TASK_MODEL_CALL_LIMIT + 1) + 2)
    tool_limit = max(32, (task_limit + 2) * (spec.source_count + 10))
    recursion_limit = max(32, 4 * (task_limit + 2))
    events = _Events(
        spec.stage, model_limit=model_limit, tool_limit=tool_limit, task_limit=task_limit
    )
    started = perf_counter()
    try:
        with tracing_context(enabled=False):
            async with asyncio.timeout(REPORT_TIMEOUT_SECONDS):
                await supervisor.ainvoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": json.dumps(
                                    coordinator.public_state(),
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            }
                        ],
                        "files": {**files, **coordinator.seed_files},
                    },
                    config={
                        "recursion_limit": recursion_limit,
                        "callbacks": [events],
                        "run_name": spec.stage,
                        "metadata": {
                            "report_stage": spec.stage,
                            "report_kind": spec.report_kind,
                            "report_role": spec.writer_role,
                        },
                    },
                )
        return coordinator.result()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        normalized = _runtime_error(error)
        if coordinator.has_valid_draft:
            return coordinator.fallback(normalized)
        raise normalized from None
    finally:
        log_agent_event(
            spec.stage + ".runtime",
            elapsed_ms=round((perf_counter() - started) * 1000),
            model_call_count=events.calls,
            tool_call_count=events.tools,
            delegation_count=events.delegations,
            required_delegation_count=coordinator.task_count,
            call_limit=model_limit,
            timeout_seconds=REPORT_TIMEOUT_SECONDS,
        )


async def run_report_workflow(spec: WorkflowSpec) -> WorkflowResult:
    """입력 검증 뒤 요청 전체를 단일 실제 DeepAgents 실행으로 처리한다."""
    started = perf_counter()
    log_agent_event(spec.stage, outcome="started", schema_name=type(spec).__name__)
    try:
        result = await _run_supervisor(spec)
        spec.validate_draft(result.draft)
        log_agent_event(
            spec.stage,
            outcome="returned",
            reason_code=f"draft_v{result.selected_version}",
        )
        return result
    except Exception as error:
        log_agent_error(error, stage=spec.stage)
        raise
    finally:
        log_agent_event(spec.stage, elapsed_ms=round((perf_counter() - started) * 1000))
