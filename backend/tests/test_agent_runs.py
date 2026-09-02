import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_openai import StreamChunkTimeoutError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from test_report_writing_deep import ScriptedModel, sample

from app.agents import report_writing_deep
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.agent import AgentRun
from app.models.workspace import Member
from app.schemas.agent_runs import (
    REPORT_GENERATION_JSON_MAX_BYTES,
    AgentRunCreate,
    ReportGenerationCreate,
    ReportGenerationScope,
)
from app.services import agent_runs as service
from app.services import agent_worker

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
TEMPLATE = {"fields": [{"id": "summary", "label": "요약"}]}
_MISSING = object()


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return list(self.values)


class _Result:
    def __init__(self, *, scalar=_MISSING, scalars=None):
        self.scalar = scalar
        self.scalar_values = [] if scalars is None else scalars

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    async def get(self, *_args):
        return None

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        pass

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


class _SessionContext:
    def __init__(self, db: _Db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def llm_ready(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_url", "https://provider.invalid/v1/responses")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_api_key", _Secret("super-secret-key"))
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))


@pytest.fixture
def llm_missing(monkeypatch):
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: False))


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _run(member: Member, *, status_code: str = "queued", key: UUID | None = None) -> AgentRun:
    return AgentRun(
        id=uuid4(),
        team_id=member.team_id,
        parent_run_id=None,
        requested_by_member_id=member.id,
        agent_code="report_writing",
        trigger_code="user",
        idempotency_key=key or uuid4(),
        report_id=None,
        status_code=status_code,
        llm_model_name="test-model",
        prompt_version="test.v1",
        request_snapshot={},
        request_hash=None,
        scope_key=None,
        source_refs={},
        input_snapshot={},
        output_snapshot=None,
        evidence=None,
        error_message=None,
        error_code=None,
        current_stage_code=status_code,
        attempt_count=0,
        payload_expires_at=None,
        payload_redacted_at=None,
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=None,
        next_attempt_at=NOW,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        created_at=NOW,
        started_at=None,
        finished_at=None,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def _daily_payload(**overrides):
    payload = {
        "idempotency_key": str(uuid4()),
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "template_snapshot": TEMPLATE,
        "content": {"values": {}, "activities": []},
    }
    payload.update(overrides)
    return payload


def test_generic_queue_only_accepts_contract_and_schedule_agents():
    with pytest.raises(ValidationError):
        AgentRunCreate(
            agent_code="meeting_processing",
            idempotency_key=uuid4(),
        )
    AgentRunCreate(
        agent_code="contract_management_select_candidates",
        idempotency_key=uuid4(),
    )


def test_report_generation_input_has_one_typed_scope():
    meeting = ReportGenerationCreate(
        idempotency_key=uuid4(),
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        source_activity_id=uuid4(),
        sales_deal_ids=[uuid4()],
        template_snapshot=TEMPLATE,
        content={},
        transcript="고객이 다음 달 예산을 검토합니다.",
    )
    assert service.generation_scope_key(meeting).startswith("meeting:")
    with pytest.raises(ValidationError):
        ReportGenerationCreate(
            idempotency_key=uuid4(),
            report_kind="meeting",
            report_date=date(2026, 8, 17),
            sales_deal_ids=[uuid4()],
            template_snapshot=TEMPLATE,
            content={},
            transcript="원문",
        )
    with pytest.raises(ValidationError):
        ReportGenerationScope(report_kind="weekly", period_start=date(2026, 8, 1))


@pytest.mark.parametrize("field_name", ["template_snapshot", "content"])
def test_report_generation_rejects_oversized_json_fields(field_name):
    payload = _daily_payload(**{field_name: {"value": "가" * REPORT_GENERATION_JSON_MAX_BYTES}})

    with pytest.raises(ValidationError, match=f"{field_name}_too_large"):
        ReportGenerationCreate.model_validate(payload)


def test_report_generation_rejects_missing_llm_before_db(llm_missing):
    with _client(_Db(), _member()) as client:
        response = client.post(
            "/api/report-generations", headers={"Origin": ORIGIN}, json=_daily_payload()
        )
    assert response.status_code == 503
    assert response.json() == {"detail": "llm_not_configured"}


def test_report_generation_is_queued_without_creating_a_report(llm_ready, monkeypatch):
    member = _member()
    db = _Db(_Result(scalar=None))

    async def frozen_input(payload, owner, current_db):
        assert owner is member and current_db is db
        return (
            "report_writing",
            {"report_kind": "daily", "content": {}},
            {
                "report_kind": "daily",
                "report_date": "2026-08-17",
                "period_start": None,
                "period_end": None,
            },
        )

    monkeypatch.setattr(service, "_report_generation_input", frozen_input)
    with _client(db, member) as client:
        response = client.post(
            "/api/report-generations", headers={"Origin": ORIGIN}, json=_daily_payload()
        )

    assert response.status_code == 202
    run = db.added[0]
    assert isinstance(run, AgentRun)
    assert run.report_id is None
    assert run.request_snapshot == response.json()["generation_input"]
    assert run.request_snapshot["content"] == {"values": {}, "activities": []}
    assert run.input_snapshot["report_kind"] == "daily"
    assert run.scope_key == "daily:2026-08-17"
    assert run.payload_expires_at - run.created_at == service.REPORT_GENERATION_RETENTION
    assert response.headers["Location"] == f"/api/agent-runs/{run.id}"


def test_generation_input_restores_only_requesters_ui_values():
    team_id = uuid4()
    owner = _member(team_id=team_id)
    run = _run(owner, status_code="running")
    deal_id = uuid4()
    activity_id = uuid4()
    run.agent_code = "meeting_processing"
    run.scope_key = f"meeting:{activity_id}"
    run.payload_expires_at = datetime.now(UTC) + timedelta(days=1)
    run.request_snapshot = {
        "report_kind": "meeting",
        "report_date": "2026-08-17",
        "period_start": None,
        "period_end": None,
        "source_activity_id": str(activity_id),
        "sales_deal_ids": [str(deal_id)],
        "template_snapshot": TEMPLATE,
        "content": {"title": "방문 미팅", "attachments": [{"name": "memo.pdf"}]},
        "transcript": "고객이 예산을 승인했습니다.",
        "guidance": None,
    }
    run.input_snapshot = {
        "source": {"transcript": "고객이 예산을 승인했습니다."},
        "crm_context": {"private": "응답하면 안 되는 CRM"},
    }
    run.output_snapshot = {
        "reports": None,
        "analyses": [],
        "evidence": {"selected_deal_ids": [str(deal_id)]},
        "errors": {},
        "context_lookups": [{"private": "응답하면 안 되는 CRM"}],
    }

    with _client(_Db(_Result(scalar=run)), owner) as client:
        restored = client.get(f"/api/agent-runs/{run.id}")

    assert restored.status_code == 200
    generation_input = restored.json()["generation_input"]
    assert generation_input["transcript"] == "고객이 예산을 승인했습니다."
    assert generation_input["content"]["attachments"] == [{"name": "memo.pdf"}]
    assert "crm_context" not in generation_input
    assert "context_lookups" not in restored.json()["output_snapshot"]

    manager = _member(role="manager", team_id=team_id)
    with _client(_Db(_Result(scalar=run)), manager) as client:
        hidden = client.get(f"/api/agent-runs/{run.id}")
    assert hidden.status_code == 200
    assert hidden.json()["generation_input"] is None
    assert hidden.json()["output_snapshot"] is None


def test_redacted_generation_has_no_reconnect_input():
    member = _member()
    run = _run(member, status_code="cancelled")
    run.request_snapshot = {
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "period_start": None,
        "period_end": None,
        "source_activity_id": None,
        "sales_deal_ids": [],
        "template_snapshot": TEMPLATE,
        "content": {"activities": [], "attachments": []},
        "transcript": None,
        "guidance": "이번 주 계약 위험을 강조",
    }
    run.payload_redacted_at = NOW
    with _client(_Db(_Result(scalar=run)), member) as client:
        response = client.get(f"/api/agent-runs/{run.id}")
    assert response.status_code == 200
    assert response.json()["generation_input"] is None


def test_latest_generation_uses_server_scope_and_requester():
    member = _member(role="manager")
    run = _run(member, status_code="completed")
    run.scope_key = "daily:2026-08-17"
    run.payload_expires_at = datetime.now(UTC) + timedelta(days=1)
    db = _Db(_Result(scalar=run))
    with _client(db, member) as client:
        response = client.get(
            "/api/report-generations/latest?report_kind=daily&report_date=2026-08-17"
        )
    assert response.status_code == 200
    assert response.json()["id"] == str(run.id)
    sql = str(db.statements[0])
    assert "agent_run.requested_by_member_id" in sql
    assert "agent_run.scope_key" in sql
    assert "agent_run.report_id IS NULL" in sql


def test_active_generation_scope_conflict_is_not_a_report_conflict(llm_ready, monkeypatch):
    member = _member()
    cause = RuntimeError("duplicate")
    cause.constraint_name = "agent_run_active_generation_scope_key"
    original = RuntimeError("adapter")
    original.__cause__ = cause
    error = IntegrityError("insert", {}, original)

    class ConflictDb(_Db):
        async def flush(self):
            raise error

    db = ConflictDb(_Result(scalar=None), _Result(scalar=None))

    async def frozen_input(*_args):
        return "report_writing", {"report_kind": "daily"}, {"report_kind": "daily"}

    monkeypatch.setattr(service, "_report_generation_input", frozen_input)
    with _client(db, member) as client:
        response = client.post(
            "/api/report-generations", headers={"Origin": ORIGIN}, json=_daily_payload()
        )
    assert response.status_code == 409
    assert response.json() == {"detail": "report_generation_in_progress"}


def test_generation_race_does_not_reuse_member_expired_by_rollback(llm_ready, monkeypatch):
    stored_member = _member()

    class ExpiringMember:
        expired = False

        @property
        def id(self):
            assert not self.expired, "rollback 뒤 ORM member를 다시 읽었습니다"
            return stored_member.id

        @property
        def team_id(self):
            assert not self.expired, "rollback 뒤 ORM member를 다시 읽었습니다"
            return stored_member.team_id

    member = ExpiringMember()
    payload = ReportGenerationCreate.model_validate(_daily_payload())
    winner = _run(stored_member, key=payload.idempotency_key)
    winner.request_hash = service._request_hash(payload.model_dump(mode="json"))
    error = IntegrityError("insert", {}, RuntimeError("duplicate"))

    class RaceDb(_Db):
        async def flush(self):
            raise error

        async def rollback(self):
            await super().rollback()
            member.expired = True

    async def frozen_input(*_args):
        return "report_writing", {"report_kind": "daily"}, {"report_kind": "daily"}

    monkeypatch.setattr(service, "_report_generation_input", frozen_input)
    read, run_id = asyncio.run(
        service.create_report_generation(
            payload,
            member,
            RaceDb(_Result(scalar=None), _Result(scalar=winner)),
        )
    )

    assert read.id == winner.id and run_id is None


def test_member_cannot_read_another_requesters_run():
    member = _member()
    db = _Db(_Result(scalar=None))
    with _client(db, member) as client:
        response = client.get(f"/api/agent-runs/{uuid4()}")
    assert response.status_code == 404
    assert "agent_run.requested_by_member_id" in str(db.statements[0])


@pytest.mark.anyio
async def test_worker_completes_meeting_output_without_an_apply_phase(monkeypatch):
    member = _member()
    run = _run(member)
    run.agent_code = "meeting_processing"
    run.input_snapshot = {"source": {"transcript": "원문"}}
    run.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    claim_db = _Db(_Result(scalar=run))
    complete_db = _Db(SimpleNamespace(rowcount=1))
    sessions = iter((claim_db, complete_db))
    monkeypatch.setattr(
        service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )
    output = SimpleNamespace(
        errors={},
        analyses=[],
        evidence=SimpleNamespace(items=[]),
        model_dump=lambda **_kwargs: {"reports": None, "analyses": [], "errors": {}},
    )

    async def dispatch(*_args):
        return output

    monkeypatch.setattr(service, "dispatch", dispatch)
    await service.execute(run.id)

    assert run.status_code == "completed"
    assert run.current_stage_code == "completed"
    assert run.output_snapshot == {"reports": None, "analyses": [], "errors": {}}
    assert not hasattr(run, "apply_status")


@pytest.mark.anyio
async def test_worker_claim_excludes_expired_or_redacted_report_payloads(monkeypatch):
    db = _Db(_Result(scalar=None))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    assert await agent_worker.claim("worker-1") is None

    statement = str(db.statements[0])
    params = repr(db.statements[0].compile().params)
    assert "agent_run.payload_expires_at" in statement
    assert "agent_run.payload_redacted_at IS NULL" in statement
    assert "schedule_management" in params
    assert "meeting_analysis" not in params


@pytest.mark.anyio
async def test_running_generation_is_cancelled_and_redacted_at_payload_expiry(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")
    run.request_hash = "0" * 64
    run.request_snapshot = {"private": "request"}
    run.input_snapshot = {"private": "input"}
    run.payload_expires_at = datetime.now(UTC) + timedelta(milliseconds=50)
    run.lease_owner = "worker-1"
    cancelled = False

    async def prepare(*_args):
        return "report_writing", run.input_snapshot, member.id

    async def dispatch(*_args):
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled = True
            raise

    db = _Db(SimpleNamespace(rowcount=1))
    monkeypatch.setattr(service, "prepare_claimed", prepare)
    monkeypatch.setattr(service, "dispatch", dispatch)
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    await agent_worker.run_claimed(run, run.lease_owner)

    assert cancelled is True
    assert run.status_code == "cancelled"
    assert run.error_code == "agent_run_payload_expired"
    assert run.request_snapshot == {} and run.input_snapshot == {}
    assert run.payload_redacted_at is not None


@pytest.mark.anyio
async def test_completion_cannot_store_output_after_payload_expiry(monkeypatch):
    run = _run(_member(), status_code="running")
    run.payload_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    run.lease_owner = "worker-1"
    db = _Db(SimpleNamespace(rowcount=0), SimpleNamespace(rowcount=1))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))
    output = SimpleNamespace(model_dump=lambda **_kwargs: {"body": "late output"})

    await agent_worker._complete(run, run.lease_owner, output)

    assert "agent_run.payload_expires_at >" in str(db.statements[0])
    assert run.status_code == "cancelled"
    assert run.output_snapshot is None
    assert run.payload_redacted_at is not None


@pytest.mark.anyio
async def test_frozen_report_input_rechecks_requester_before_dispatch(monkeypatch):
    member = _member()
    run = _run(member)
    run.input_snapshot = {"report_kind": "daily"}
    run.request_hash = "0" * 64
    run.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    db = _Db(_Result(scalar=None))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    with pytest.raises(ValueError, match="requester_not_active"):
        await service.prepare_claimed(run, "worker-1")


@pytest.mark.anyio
async def test_expired_report_input_never_reaches_requester_or_dispatch(monkeypatch):
    run = _run(_member())
    run.input_snapshot = {"report_kind": "daily"}
    run.request_hash = "0" * 64
    run.payload_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    monkeypatch.setattr(
        service,
        "get_sessionmaker",
        lambda: (_ for _ in ()).throw(AssertionError("requester query must not run")),
    )

    with pytest.raises(ValueError, match="agent_run_payload_expired"):
        await service.prepare_claimed(run, "worker-1")


def test_only_network_and_provider_failures_are_retried():
    assert service.is_transient_error("llm_request_failed:ReadTimeout") is True
    assert service.is_transient_error("llm_provider_error:429") is True
    assert service.is_transient_error("llm_provider_error:503") is True
    assert service.is_transient_error("agent_run_timeout") is False
    assert service.is_transient_error("report_agent_timeout") is False
    assert service.is_transient_error("review_limit_exceeded") is False
    assert agent_worker.MAX_ATTEMPTS == 2


def _provider_failure(kind: str) -> BaseException:
    request = httpx.Request("POST", "https://provider.invalid/v1/responses")
    if kind == "httpx_connection":
        return httpx.ConnectError("private", request=request)
    if kind == "openai_connection":
        return openai.APIConnectionError(request=request)
    if kind == "langchain_stream_timeout":
        return StreamChunkTimeoutError(180, model_name="private-model")
    response = httpx.Response(int(kind), request=request)
    error_type = openai.RateLimitError if kind == "429" else openai.InternalServerError
    return error_type("private", response=response, body=None)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure_kind,error_code",
    [
        ("httpx_connection", "llm_request_failed:ConnectError"),
        ("openai_connection", "llm_request_failed:APIConnectionError"),
        ("langchain_stream_timeout", "llm_request_failed:StreamChunkTimeoutError"),
        ("429", "llm_provider_error:429"),
        ("503", "llm_provider_error:503"),
    ],
)
async def test_provider_failure_reaches_workers_single_retry(monkeypatch, failure_kind, error_code):
    member = _member()
    run = _run(member, status_code="running")
    run.request_hash = "0" * 64
    run.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)

    class BrokenModel(ScriptedModel):
        def _generate(self, *args, **kwargs):
            raise _provider_failure(failure_kind)

    async def prepare(*_args):
        return "report_writing", {}, member.id

    async def dispatch(*_args):
        return await report_writing_deep.run(sample(), model=BrokenModel(responses=[]))

    monkeypatch.setattr(service, "prepare_claimed", prepare)
    monkeypatch.setattr(service, "dispatch", dispatch)

    for attempt, expected_status in ((1, "queued"), (2, "failed")):
        run.status_code = "running"
        run.current_stage_code = "running_agent"
        run.attempt_count = attempt
        run.lease_owner = f"worker-{attempt}"
        db = _Db(SimpleNamespace(rowcount=1))
        monkeypatch.setattr(
            service,
            "get_sessionmaker",
            lambda db=db: lambda: _SessionContext(db),
        )

        await agent_worker.run_claimed(run, run.lease_owner)

        assert run.error_code == error_code
        assert run.status_code == expected_status
        assert run.current_stage_code == ("retry_wait" if attempt == 1 else "failed")


def test_finalize_redacts_only_report_generation_payloads():
    report_run = _run(_member(), status_code="completed")
    report_run.input_snapshot = {"transcript": "민감 원문"}
    report_run.output_snapshot = {"body": "초안"}
    report_run.evidence = {"quote": "민감 원문"}
    service.redact_payload(report_run, now=NOW)
    assert report_run.input_snapshot == {}
    assert report_run.output_snapshot is None
    assert report_run.evidence is None
    assert report_run.payload_redacted_at == NOW

    contract_run = _run(_member(), status_code="completed")
    contract_run.agent_code = "schedule_management"
    contract_run.output_snapshot = {"schedule_candidates": []}
    service.redact_payload(contract_run, now=NOW)
    assert contract_run.output_snapshot == {"schedule_candidates": []}


@pytest.mark.anyio
async def test_expired_report_payload_cleanup_is_one_bulk_update(monkeypatch):
    db = _Db(SimpleNamespace(rowcount=2))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))
    assert await service.redact_expired_payloads(NOW) == 2
    assert db.commit_count == 1
    sql = str(db.statements[0])
    params = db.statements[0].compile().params
    assert "payload_expires_at" in sql
    assert "payload_redacted_at" in sql
    assert "CASE WHEN" in sql
    assert "cancelled" in params.values()
    assert "agent_run_payload_expired" in params.values()
    # Status appears only in SET CASE expressions; expiry is not terminal-only.
    assert "agent_run.status_code" not in sql.split(" WHERE ", 1)[1]


def test_transient_generation_migration_keeps_blue_green_agent_storage():
    sql = (
        Path(__file__).parents[1] / "sql/20260902_0019_transient_report_generation.sql"
    ).read_text(encoding="utf-8")
    active_sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert "DROP COLUMN IF EXISTS parent_run_id" not in active_sql
    assert "DROP COLUMN" not in active_sql
    assert "DROP INDEX" not in active_sql
    assert "attempt_count BETWEEN" not in sql
    assert "agent_run_lifecycle_migrated" not in sql


def test_manual_meeting_apply_routes_are_removed():
    paths = {
        (method, route.path)
        for route in app.routes
        if hasattr(route, "path")
        for method in getattr(route, "methods", set())
    }
    assert ("POST", "/api/agent-runs/{agent_run_id}/apply") not in paths
    assert ("PATCH", "/api/agent-runs/{agent_run_id}/meeting-notes") not in paths
