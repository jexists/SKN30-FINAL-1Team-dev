import asyncio
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.services import contract_tracing


class TraceClient:
    def __init__(self):
        self.created = []
        self.updated = []

    def create_run(self, **kwargs):
        self.created.append(kwargs)

    def update_run(self, run_id, **kwargs):
        self.updated.append({"id": run_id, **kwargs})


def configure(monkeypatch, client):
    monkeypatch.setattr(contract_tracing, "settings", SimpleNamespace(
        contract_langsmith_enabled=True, langsmith_api_key=SecretStr("synthetic-test-key"),
        langsmith_project="synthetic-tests"))
    monkeypatch.setattr(contract_tracing, "_client", lambda: client)


def test_trace_nesting_and_private_payload_exclusion(monkeypatch):
    client = TraceClient()
    configure(monkeypatch, client)

    async def exercise():
        async with contract_tracing.span("contract", run_id="synthetic", prompt="PRIVATE"):
            async with contract_tracing.span("schedule", attempt=1) as result:
                result.update(status="no_candidates", raw_output="PRIVATE")
    asyncio.run(exercise())
    assert len(client.created) == 2
    assert client.created[1]["parent_run_id"] == client.created[0]["id"]
    assert "PRIVATE" not in repr(client.created + client.updated)
    assert contract_tracing._parent.get() is None


def test_trace_failure_does_not_fail_business_operation(monkeypatch):
    class BrokenClient(TraceClient):
        def create_run(self, **kwargs):
            raise RuntimeError("synthetic transport error")
    configure(monkeypatch, BrokenClient())

    async def exercise():
        async with contract_tracing.span("contract"):
            return 42
    assert asyncio.run(exercise()) == 42


def test_business_exception_is_not_uploaded(monkeypatch):
    client = TraceClient()
    configure(monkeypatch, client)

    async def exercise():
        async with contract_tracing.span("contract"):
            raise ValueError("PRIVATE_EXCEPTION")
    with pytest.raises(ValueError, match="PRIVATE_EXCEPTION"):
        asyncio.run(exercise())
    assert "PRIVATE_EXCEPTION" not in repr(client.created + client.updated)
    assert client.updated[-1]["extra"]["metadata"]["status"] == "failed"
