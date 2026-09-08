"""Service lifecycle with a transaction-serialized fake; PostgreSQL has a separate test."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.contract_management import NextMeetingProposalOutput, NextMeetingSuggestion
from app.models.agent import AgentRun
from app.models.crm import Activity
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.services import agent_worker
from app.services.contract_schedule_delegation import DelegationRuntime
from app.services.llm import LLMError


class Store:
    def __init__(self, candidate_count=0):
        self.lock = asyncio.Lock()
        self.now = datetime.now(UTC)
        self.member = SimpleNamespace(id=uuid4(), team_id=uuid4(), role_code="member")
        self.deal = SimpleNamespace(id=uuid4(), team_id=self.member.team_id,
                                    owner_member_id=self.member.id)
        self.parent = SimpleNamespace(
            id=uuid4(), team_id=self.member.team_id, requested_by_member_id=self.member.id,
            status_code="running", lease_owner="owner", trigger_code="user",
            lease_expires_at=self.now + timedelta(minutes=5), delegation_state={},
            source_refs={"sales_deal_id": str(self.deal.id)},
            input_snapshot={"sales_deals": [{"id": str(self.deal.id)}]},
        )
        self.children = {}
        self.executions = 0
        self.candidate_count = candidate_count

    def __call__(self):
        return Session(self)

    def args(self, offset=0):
        return {"preferred_starts_at": (self.now + timedelta(days=2+offset)).isoformat(),
                "preferred_ends_at": (self.now + timedelta(days=7)).isoformat(),
                "duration_minutes": 60, "reason": f"합성 검색 근거 {offset}"}

    async def execute_child(self, child_id):
        async with self.lock:
            child = self.children[child_id]
            if child.status_code != "queued":
                return
            child.status_code = "running"
            child.attempt_count = 1
            self.executions += 1
        await asyncio.sleep(0)
        async with self.lock:
            start = datetime.fromisoformat(child.input_snapshot["preferred_starts_at"])
            child.output_snapshot = {"schedule_candidates": [{
                "candidate_id": str(uuid4()), "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(hours=1)).isoformat(), "priority": 1,
            }] if self.candidate_count else []}
            child.status_code = "completed"


class Session:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        await self.store.lock.acquire()
        return self

    async def __aexit__(self, *args):
        self.store.lock.release()

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        value = {AgentRun: self.store.parent, SalesDeal: self.store.deal,
                 Member: self.store.member, Activity: []}[entity]
        return SimpleNamespace(scalar_one=lambda: value, scalar_one_or_none=lambda: value,
                               scalars=lambda: SimpleNamespace(all=lambda: value))

    def add(self, child):
        self.store.children[child.id] = child

    async def commit(self):
        pass

    async def get(self, model, key):
        return self.store.children.get(key)


def test_concurrent_duplicate_and_restart_reuse_one_child(monkeypatch):
    async def exercise():
        store = Store(candidate_count=1)
        monkeypatch.setattr(agent_worker, "execute", store.execute_child)
        runtime = DelegationRuntime(store.parent, "owner", store)
        await runtime.restore()
        results = await asyncio.gather(runtime.request("1:0", store.args()),
                                       runtime.request("2:0", store.args()))
        assert results[0]["schedule_run_id"] == results[1]["schedule_run_id"]
        assert len(store.children) == store.executions == 1
        resumed = DelegationRuntime(store.parent, "owner", store)
        assert await resumed.request("1:0", store.args()) == results[0]
        assert (await resumed.restore())["tool_requests"] == 2
        assert store.executions == 1
        output = NextMeetingProposalOutput(
            next_meeting_suggestion=NextMeetingSuggestion(sales_deal_id="invented", reason="x"),
            schedule_management_run_id=results[0]["schedule_run_id"])
        final = await resumed.finish(output)
        assert final.next_meeting_suggestion.sales_deal_id == str(store.deal.id)
        assert final.schedule_status == "candidates_found"
        with pytest.raises(ValueError, match="invalid_selected"):
            await resumed.finish(
                output.model_copy(update={"schedule_management_run_id": str(uuid4())}))
    asyncio.run(exercise())


def test_two_empty_searches_and_invalid_requests_are_bounded(monkeypatch):
    async def exercise():
        store = Store()
        monkeypatch.setattr(agent_worker, "execute", store.execute_child)
        runtime = DelegationRuntime(store.parent, "owner", store)
        await runtime.restore()
        assert (await runtime.request("1", store.args()))["status"] == "no_candidates"
        assert (await runtime.request("2", store.args(offset=1)))["status"] == "no_candidates"
        third = await runtime.request("3", store.args(offset=2))
        assert third["reason_code"] == "search_limit_exceeded"
        assert (await runtime.request("4", {}))["reason_code"] == "invalid_tool_arguments"
        with pytest.raises(LLMError, match="tool_limit"):
            await runtime.request("5", {})
        assert len(store.children) == store.executions == 2
        finished = await runtime.finish(NextMeetingProposalOutput())
        assert finished.schedule_status == "no_candidates"
    asyncio.run(exercise())


def test_reuse_rechecks_reassigned_deal(monkeypatch):
    async def exercise():
        store = Store()
        monkeypatch.setattr(agent_worker, "execute", store.execute_child)
        runtime = DelegationRuntime(store.parent, "owner", store)
        await runtime.restore()
        await runtime.request("1", store.args())
        store.deal.owner_member_id = uuid4()
        denied = await runtime.request("2", store.args())
        assert denied["reason_code"] == "schedule_scope_denied"
        assert store.executions == 1
    asyncio.run(exercise())


def test_lost_child_lease_does_not_cancel_worker_loop(monkeypatch):
    async def cancel_work(*args):
        raise asyncio.CancelledError()
    monkeypatch.setattr(agent_worker, "_run_claimed_work", cancel_work)
    asyncio.run(agent_worker.run_claimed(None, "owner"))
