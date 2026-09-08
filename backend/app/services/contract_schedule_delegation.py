"""Durable contract-to-schedule delegation, scoped to one parent and one deal."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.agents import contract_management, schedule_management
from app.core.config import settings
from app.models.agent import AgentRun
from app.models.crm import Activity
from app.models.sales import SalesDeal, SalesPipelineStage
from app.models.workspace import Member
from app.schemas.schedule_delegation import (
    MAX_MODEL_CALLS,
    MAX_SEARCHES,
    MAX_TOOL_REQUESTS,
    SafeScheduleCandidate,
    ScheduleRequest,
    ScheduleToolResult,
    validate_search,
)
from app.services.contract_tracing import span
from app.services.llm import LLMError


def _failure(code: str) -> dict:
    return ScheduleToolResult(status="failed", reason_code=code).model_dump(mode="json")


def check_retry(request: ScheduleRequest, searches: list, constraints: dict) -> None:
    if not searches:
        return
    if len(searches) >= MAX_SEARCHES:
        raise ValueError("search_limit_exceeded")
    first = searches[0]
    if (first.get("result") or {}).get("status") != "no_candidates":
        raise ValueError("research_requires_no_candidates")
    previous = ScheduleRequest.model_validate(first["request"])
    if request.duration_minutes != previous.duration_minutes:
        raise ValueError("duration_change_not_allowed")
    if request.reason == previous.reason:
        raise ValueError("research_reason_required")
    # Do not treat a contract expiry as an explicit meeting deadline. Until a server-side
    # structured scheduling constraint exists, the first window is the outer boundary.
    if not constraints.get("not_after") and (
        request.preferred_starts_at < previous.preferred_starts_at
        or request.preferred_ends_at > previous.preferred_ends_at
    ):
        raise ValueError("research_boundary_unconfirmed")


async def strict_snapshot(session, member, deal, request: ScheduleRequest) -> dict:
    """Internal running-parent path. No legacy fallback dates or automatic widening."""
    activities = (
        (
            await session.execute(
                select(Activity).where(
                    Activity.team_id == member.team_id,
                    Activity.owner_member_id == deal.owner_member_id,
                    Activity.deleted_at.is_(None),
                    # Include long-running events that began before the requested window.
                    Activity.starts_at < request.preferred_ends_at + timedelta(days=1),
                )
            )
        )
        .scalars()
        .all()
    )
    windows = []
    for activity in activities:
        window = {
            "id": str(activity.id),
            "starts_at": activity.starts_at.isoformat(),
            "ends_at": activity.ends_at.isoformat() if activity.ends_at else None,
            "all_day": activity.all_day,
        }
        try:
            _, end = schedule_management._occupied_range(window)
        except (ValueError, TypeError):
            raise ValueError("invalid_existing_schedule") from None
        if end > request.preferred_starts_at:
            windows.append(window)
    return {
        **request.model_dump(mode="json"),
        "sales_deal_id": str(deal.id),
        "activities": windows,
        "strict_delegation": True,
    }


class DelegationRuntime:
    def __init__(self, run: AgentRun, lease_owner: str, sessionmaker):
        self.run = run
        self.lease_owner = lease_owner
        self.sessions = sessionmaker

    async def _active(self, session) -> AgentRun:
        parent = (
            await session.execute(
                select(AgentRun)
                .where(
                    AgentRun.id == self.run.id,
                )
                .with_for_update()
            )
        ).scalar_one()
        now = datetime.now(UTC)
        if (
            parent.status_code != "running"
            or parent.lease_owner != self.lease_owner
            or parent.lease_expires_at is None
            or parent.lease_expires_at <= now
        ):
            raise RuntimeError("agent_run_lease_lost")
        deadline = (parent.delegation_state or {}).get("deadline")
        if deadline and datetime.fromisoformat(deadline) <= now:
            raise LLMError("contract_delegation_timeout")
        return parent

    async def _scope(self, session, parent):
        deal_ids = [x["id"] for x in parent.input_snapshot.get("sales_deals", [])]
        target = (parent.source_refs or {}).get("sales_deal_id")
        if target is None and len(deal_ids) == 1:
            target = deal_ids[0]
        if target is None or str(target) not in deal_ids:
            raise ValueError("schedule_target_required")
        deal = (
            await session.execute(
                select(SalesDeal)
                .join(
                    SalesPipelineStage,
                    SalesPipelineStage.id == SalesDeal.sales_pipeline_stage_id,
                )
                .where(
                    SalesDeal.id == UUID(target),
                    SalesDeal.team_id == parent.team_id,
                    SalesDeal.deleted_at.is_(None),
                    SalesPipelineStage.phase_code != "closed",
                )
            )
        ).scalar_one_or_none()
        if deal is None:
            raise ValueError("schedule_scope_denied")
        requester = parent.requested_by_member_id or deal.owner_member_id
        member = (
            await session.execute(
                select(Member).where(
                    Member.id == requester,
                    Member.team_id == parent.team_id,
                    Member.active.is_(True),
                    Member.role_code.in_(("member", "manager")),
                )
            )
        ).scalar_one_or_none()
        if member is None or (member.role_code == "member" and deal.owner_member_id != member.id):
            raise ValueError("schedule_scope_denied")
        return member, deal

    async def restore(self) -> dict:
        async with self.sessions() as session:
            parent = await self._active(session)
            state = deepcopy(parent.delegation_state or {})
            if not state:
                state = {
                    "model_calls": 0,
                    "tool_requests": 0,
                    "history": [],
                    "pending": [],
                    "requests": {},
                    "searches": [],
                    "constraints": {},
                    "deadline": (
                        datetime.now(UTC)
                        + timedelta(seconds=settings.contract_delegation_timeout_seconds)
                    ).isoformat(),
                }
                # Only server-built input can supply these; never use model output as a bound.
                state["constraints"] = parent.input_snapshot.get("schedule_constraints") or {}
                parent.delegation_state = state
                await session.commit()
            self.run.delegation_state = state
            return state

    async def _mutate(self, operation):
        async with self.sessions() as session:
            parent = await self._active(session)
            state = deepcopy(parent.delegation_state)
            result = operation(state)
            parent.delegation_state = state
            await session.commit()
            self.run.delegation_state = state
            return result

    async def reserve_model(self) -> int:
        def reserve(state):
            if state["model_calls"] >= MAX_MODEL_CALLS:
                raise LLMError("contract_model_limit_exceeded")
            state["model_calls"] += 1
            return state["model_calls"]

        return await self._mutate(reserve)

    async def record_calls(self, calls):
        # Only explicit tool arguments are journaled; no model reasoning/content blocks.
        safe_calls = [
            {"name": c["name"], "args": c["args"], "id": c["id"], "type": "tool_call"}
            for c in calls
        ]

        def record(state):
            state["pending"] = safe_calls
            state["history"].append({"role": "assistant", "tool_calls": safe_calls})

        await self._mutate(record)

    async def record_invalid_turn(self):
        await self._mutate(lambda state: state.update(last_error="invalid_model_tool_response"))

    async def record_result(self, call_id, result):
        def record(state):
            if not any(x.get("id") == call_id for x in state["history"]):
                state["history"].append({"role": "tool", "id": call_id, "result": result})

        await self._mutate(record)

    async def clear_pending(self):
        await self._mutate(lambda state: state.update(pending=[]))

    async def reject(self, call_key, code):
        return await self.request(call_key, {}, rejection=code)

    async def request(self, call_key: str, args: dict, *, rejection=None) -> dict:
        async with span("schedule.request", run_id=str(self.run.id)) as trace:
            result = await self._request(call_key, args, rejection)
            trace.update(
                status=result["status"],
                reason_code=result["reason_code"],
                candidate_count=len(result.get("schedule_candidates", [])),
            )
            state = await self.restore()
            trace.update(search_count=len(state["searches"]),
                         tool_call_count=state["tool_requests"])
            try:
                parsed = ScheduleRequest.model_validate(args)
                trace.update(search_starts_at=parsed.preferred_starts_at.isoformat(),
                             search_ends_at=parsed.preferred_ends_at.isoformat(),
                             duration_minutes=parsed.duration_minutes,
                             constraint_basis=(
                                 "explicit_bound" if state["constraints"] else "initial_window"))
            except ValidationError:
                pass
            return result

    async def _request(self, call_key, args, rejection):
        async with self.sessions() as session:
            parent = await self._active(session)
            state = deepcopy(parent.delegation_state)
            existing = state["requests"].get(call_key)
            if existing and "result" in existing:
                if existing.get("run_id"):
                    try:
                        await self._scope(session, parent)
                    except ValueError:
                        return _failure("schedule_scope_denied")
                return existing["result"]
            if existing is None:
                if state["tool_requests"] >= MAX_TOOL_REQUESTS:
                    raise LLMError("contract_tool_limit_exceeded")
                state["tool_requests"] += 1
                state["requests"][call_key] = {}
            try:
                if rejection:
                    raise ValueError(rejection)
                request = ScheduleRequest.model_validate(args)
                searches = state["searches"]
                # Reuse never bypasses current authorization (e.g. a reassigned deal).
                member, deal = await self._scope(session, parent)
                previous = next((s for s in searches if s["key"] == request.key()), None)
                if previous:
                    child_id = UUID(previous["run_id"])
                else:
                    validate_search(request, datetime.now(UTC), state["constraints"])
                    check_retry(request, searches, state["constraints"])
                    snapshot = await strict_snapshot(session, member, deal, request)
                    child_id = uuid4()
                    session.add(
                        AgentRun(
                            id=child_id,
                            team_id=parent.team_id,
                            parent_run_id=parent.id,
                            requested_by_member_id=member.id,
                            agent_code="schedule_management",
                            trigger_code=parent.trigger_code,
                            idempotency_key=None,
                            status_code="queued",
                            llm_model_name=settings.llm_model,
                            prompt_version=schedule_management.PROMPT_VERSION,
                            source_refs={"sales_deal_id": str(deal.id)},
                            input_snapshot=snapshot,
                            request_hash=None,
                            delegation_key=request.key(),
                            output_snapshot=None,
                            evidence=None,
                            error_message=None,
                            started_at=None,
                            finished_at=None,
                        )
                    )
                    searches.append(
                        {
                            "key": request.key(),
                            "run_id": str(child_id),
                            "request": request.model_dump(mode="json"),
                        }
                    )
                state["requests"][call_key]["run_id"] = str(child_id)
            except (ValueError, HTTPException) as error:
                code = (
                    "invalid_tool_arguments" if isinstance(error, ValidationError) else str(error)
                )
                allowed = {
                    "search_in_past",
                    "schedule_constraint_violation",
                    "search_horizon_exceeded",
                    "search_limit_exceeded",
                    "research_requires_no_candidates",
                    "duration_change_not_allowed",
                    "research_reason_required",
                    "research_boundary_unconfirmed",
                    "schedule_target_required",
                    "schedule_scope_denied",
                    "unknown_tool",
                    "invalid_existing_schedule",
                }
                result = _failure(code if code in allowed else "invalid_tool_arguments")
                state["requests"][call_key]["result"] = result
                parent.delegation_state = state
                await session.commit()
                return result
            parent.delegation_state = state
            await session.commit()

        result = await self._execute_child(child_id)

        def save(state):
            state["requests"][call_key]["result"] = result
            for search in state["searches"]:
                if search["run_id"] == str(child_id):
                    search["result"] = result

        await self._mutate(save)
        return result

    async def _execute_child(self, child_id):
        from app.services import agent_worker

        while True:
            await self.restore()  # parent lease, cancellation and deadline fence
            # claim uses SKIP LOCKED; a single worker can execute its own child.
            async with span("schedule.agent", run_id=str(child_id), parent_run_id=str(self.run.id)):
                await agent_worker.execute(child_id)
            async with self.sessions() as session:
                child = await session.get(AgentRun, child_id)
                if child.status_code == "completed":
                    candidates = [
                        SafeScheduleCandidate.model_validate(c)
                        for c in (child.output_snapshot or {}).get("schedule_candidates", [])
                    ]
                    result = ScheduleToolResult(
                        status="candidates_found" if candidates else "no_candidates",
                        reason_code="candidates_available" if candidates else "no_available_slot",
                        schedule_run_id=str(child.id),
                        schedule_candidates=candidates,
                        applied_conditions={
                            k: child.input_snapshot[k]
                            for k in (
                                "preferred_starts_at",
                                "preferred_ends_at",
                                "duration_minutes",
                            )
                        },
                    ).model_dump(mode="json")
                    return result
                if child.status_code in ("failed", "cancelled"):
                    return {
                        **_failure("schedule_execution_failed"),
                        "schedule_run_id": str(child.id),
                    }
                if (
                    child.attempt_count >= agent_worker.MAX_ATTEMPTS
                    and child.lease_expires_at is not None
                    and child.lease_expires_at <= datetime.now(UTC)
                ):
                    return {
                        **_failure("schedule_execution_failed"),
                        "schedule_run_id": str(child.id),
                    }
            await asyncio.sleep(0.25)

    async def finish(self, output):
        async with self.sessions() as session:
            parent = await self._active(session)
            state = deepcopy(parent.delegation_state)
            searches = state["searches"]
            successful = [
                s for s in searches if (s.get("result") or {}).get("status") == "candidates_found"
            ]
            if successful:
                selected = next(
                    (s for s in successful if s["run_id"] == output.schedule_management_run_id),
                    None,
                )
                if selected is None or output.next_meeting_suggestion is None:
                    raise ValueError("invalid_selected_schedule")
                member, deal = await self._scope(session, parent)
                child = await session.get(AgentRun, UUID(selected["run_id"]))
                if (
                    child is None
                    or child.parent_run_id != parent.id
                    or child.team_id != parent.team_id
                    or child.status_code != "completed"
                    or not (child.output_snapshot or {}).get("schedule_candidates")
                ):
                    raise ValueError("invalid_selected_schedule")
                suggestion = contract_management.NextMeetingSuggestion(
                    sales_deal_id=str(deal.id), **selected["request"]
                )
                output = output.model_copy(
                    update={
                        "next_meeting_suggestion": suggestion,
                        "schedule_status": "candidates_found",
                        "schedule_reason_code": "candidates_available",
                    }
                )
            else:
                if output.schedule_management_run_id is not None:
                    raise ValueError("invalid_selected_schedule")
                rejected = not searches and bool(state["requests"])
                failed = rejected or any(
                    (s.get("result") or {}).get("status") == "failed" for s in searches
                )
                status = "failed" if failed else "no_candidates" if searches else "not_requested"
                code = (
                    "schedule_request_rejected" if rejected else
                    "schedule_execution_failed"
                    if failed
                    else ("no_available_slot" if searches else
                          "missing_information" if output.missing_information
                          else "meeting_not_needed")
                )
                output = output.model_copy(
                    update={
                        "schedule_status": status,
                        "schedule_reason_code": code,
                        "schedule_management_run_id": None,
                        "next_meeting_suggestion": None,
                    }
                )
            # Ground risk code/severity/references in server-produced signals.
            signals = parent.input_snapshot.get("risk_signals", [])
            output.risks = [
                risk
                for risk in output.risks
                if any(
                    risk.code == signal.get("code")
                    and risk.severity == signal.get("severity")
                    and all(
                        ref.model_dump() in signal.get("source_refs", [])
                        for ref in risk.source_refs
                    )
                    for signal in signals
                )
            ]
            state["final"] = output.model_dump(mode="json")
            parent.delegation_state = state
            await session.commit()
            self.run.delegation_state = state
            return output


async def run(parent: AgentRun, lease_owner: str, sessionmaker):
    from app.agents import contract_delegation

    runtime = DelegationRuntime(parent, lease_owner, sessionmaker)
    state = await runtime.restore()
    remaining = (datetime.fromisoformat(state["deadline"]) - datetime.now(UTC)).total_seconds()
    async with span(
        "contract.schedule_delegation",
        run_id=str(parent.id),
        attempt=parent.attempt_count,
        prompt_version=contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
    ) as trace:
        try:
            async with asyncio.timeout(max(0, remaining)):
                output = await contract_delegation.run(parent.input_snapshot, runtime)
                trace.update(status=output.schedule_status, reason_code=output.schedule_reason_code)
                return output
        except TimeoutError:
            raise LLMError("contract_delegation_timeout") from None
