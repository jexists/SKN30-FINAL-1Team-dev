import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents import report_writing
from app.agents.report_writing import ReportDraftOutput
from app.api import agent_runs
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.agent_runs import AgentRunCreate
from app.services import agent_runs as agent_run_service
from app.services import llm

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
TEMPLATE = {"fields": [{"id": "summary", "label": "요약"}]}
_MISSING = object()


class _Secret:
    """SecretStr 대체. 값이 메시지에 새는지 보려고 일부러 눈에 띄는 문자열을 쓴다."""

    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class _Result:
    def __init__(self, *, scalar=_MISSING):
        self.scalar = scalar

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        pass

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


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
    yield


@pytest.fixture
def llm_missing(monkeypatch):
    """개발 .env 에 LLM 값이 있어도 미설정 상태를 강제한다."""
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: False))
    yield


def _member(*, role: str = "member") -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        login_id=f"{uuid4()}@salesluv.demo",
        password_hash="unused",
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _report(member: Member, *, status_code: str = "draft") -> Report:
    return Report(
        id=uuid4(),
        team_id=member.team_id,
        author_member_id=member.id,
        recipient_member_id=None,
        template_snapshot=TEMPLATE,
        source_activity_id=None,
        report_kind="daily",
        report_date=date(2026, 8, 17),
        period_start=None,
        period_end=None,
        status_code=status_code,
        content={"summary": ""},
        transcript=None,
        source_snapshot=None,
        ai_evidence=None,
        note=None,
        reviewed_by_member_id=None,
        reviewed_at=None,
        created_at=NOW,
        updated_at=NOW,
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
        status_code=status_code,
        llm_model_name="test-model",
        prompt_version=report_writing.PROMPT_VERSION,
        source_refs={"report_id": str(uuid4())},
        input_snapshot={},
        output_snapshot=None,
        evidence=None,
        error_message=None,
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


def test_agent_run_request_rejects_unsafe_values():
    report_id = uuid4()
    key = uuid4()
    with pytest.raises(ValidationError):
        # 이번 범위에 없는 agent 는 받지 않는다.
        AgentRunCreate(agent_code="meeting_analysis", report_id=report_id, idempotency_key=key)
    with pytest.raises(ValidationError):
        # 상태와 팀은 요청으로 정할 수 없다.
        AgentRunCreate(
            agent_code="report_writing",
            report_id=report_id,
            idempotency_key=key,
            status_code="completed",
        )
    with pytest.raises(ValidationError):
        # idempotency_key 는 필수다.
        AgentRunCreate(agent_code="report_writing", report_id=report_id)


def test_llm_not_configured_returns_503(llm_missing):
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "report_writing",
                "report_id": str(uuid4()),
                "idempotency_key": str(uuid4()),
            },
        )
    assert response.status_code == 503
    assert response.json() == {"detail": "llm_not_configured"}
    assert db.commit_count == 0


def test_accepted_run_is_queued_and_does_not_touch_report(llm_ready, monkeypatch):
    # TestClient 는 응답 뒤 백그라운드 작업을 실제로 돌린다. 실행 자체는 별도로 검증하고
    # 여기서는 예약 여부만 본다. 그대로 두면 실제 DB 엔진에 붙어 다른 테스트를 오염시킨다.
    scheduled: list[UUID] = []

    async def _fake_execute(run_id: UUID) -> None:
        scheduled.append(run_id)

    monkeypatch.setattr(agent_run_service, "execute", _fake_execute)

    member = _member()
    report = _report(member)
    db = _Db(_Result(scalar=None), _Result(scalar=report))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "report_writing",
                "report_id": str(report.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status_code"] == "queued"
    assert body["output_snapshot"] is None
    assert response.headers["Location"] == f"/api/agent-runs/{body['id']}"
    assert response.headers["Retry-After"] == str(agent_runs.RETRY_AFTER_SECONDS)

    # 사람이 확인하기 전에는 보고서를 고치지 않는다.
    assert report.content == {"summary": ""}
    assert report.status_code == "draft"
    assert db.commit_count == 1
    assert scheduled == [UUID(body["id"])]


def test_same_idempotency_key_returns_existing_run(llm_ready):
    member = _member()
    key = uuid4()
    existing = _run(member, status_code="running", key=key)
    db = _Db(_Result(scalar=existing))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "report_writing",
                "report_id": str(uuid4()),
                "idempotency_key": str(key),
            },
        )

    assert response.status_code == 202
    assert response.json()["id"] == str(existing.id)
    assert response.json()["status_code"] == "running"
    # 새 실행을 만들지 않았다.
    assert db.added == []
    assert db.commit_count == 0


def test_submitted_report_cannot_be_drafted(llm_ready):
    member = _member()
    submitted = _report(member, status_code="submitted")
    db = _Db(_Result(scalar=None), _Result(scalar=submitted))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "report_writing",
                "report_id": str(submitted.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "report_not_editable"}
    assert db.rollback_count == 1


def test_member_cannot_read_other_requesters_run():
    member = _member()
    db = _Db(_Result(scalar=None))
    with _client(db, member) as client:
        response = client.get(f"/api/agent-runs/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "agent_run_not_found"}
    sql = str(db.statements[0])
    assert "agent_run.requested_by_member_id" in sql
    assert "agent_run.team_id" in sql


@pytest.mark.anyio
async def test_provider_errors_never_leak_url_or_key(llm_ready, monkeypatch):
    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("https://provider.invalid 로 붙지 못함")

    monkeypatch.setattr(llm.httpx, "AsyncClient", _FailingClient)

    with pytest.raises(llm.LLMError) as caught:
        await llm.generate_structured(
            instructions="x",
            input_text="y",
            schema=ReportDraftOutput,
            schema_name="report_draft",
        )

    message = str(caught.value)
    assert "super-secret-key" not in message
    assert "provider.invalid" not in message
    assert message == "llm_request_failed:ConnectError"


@pytest.mark.anyio
async def test_schema_mismatch_is_rejected(llm_ready, monkeypatch):
    class _Response:
        status_code = 200

        def json(self):
            # fields 가 요구 형태가 아니다.
            return {"output_text": json.dumps({"fields": [{"wrong": 1}]})}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(llm.httpx, "AsyncClient", _Client)

    with pytest.raises(llm.LLMError, match="llm_output_schema_mismatch"):
        await llm.generate_structured(
            instructions="x",
            input_text="y",
            schema=ReportDraftOutput,
            schema_name="report_draft",
        )
