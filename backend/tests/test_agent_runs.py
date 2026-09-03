import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.agents import contract_management, meeting_analysis, report_writing, schedule_management
from app.agents.report_writing import ReportDraftOutput
from app.api import agent_runs
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.ml.deal_baseline import DealModelError
from app.models.agent import AgentRun
from app.models.content import Report
from app.models.workspace import Member
from app.schemas.agent_runs import AgentRunCreate
from app.services import agent_runs as agent_run_service
from app.services import agent_worker, contract_schedule_snapshots, llm
from app.services.agent_logging import log_agent_event

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
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _report(
    member: Member,
    *,
    status_code: str = "draft",
    transcript: str | None = None,
) -> Report:
    return Report(
        id=uuid4(),
        team_id=member.team_id,
        author_member_id=member.id,
        recipient_member_id=None,
        template_snapshot=TEMPLATE,
        source_activity_id=None,
        sales_deal_id=None,
        report_kind="daily",
        report_date=date(2026, 8, 17),
        period_start=None,
        period_end=None,
        status_code=status_code,
        content={"summary": ""},
        transcript=transcript,
        source_snapshot=None,
        ai_evidence=None,
        note=None,
        reviewed_by_member_id=None,
        reviewed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _run(member: Member, *, status_code: str = "queued", key: UUID | None = None) -> AgentRun:
    now = datetime.now(UTC)
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
        prompt_version=report_writing.PROMPT_VERSION,
        request_snapshot={},
        request_hash=None,
        source_refs={"report_id": str(uuid4())},
        input_snapshot={},
        output_snapshot=None,
        evidence=None,
        error_message=None,
        error_code=None,
        apply_status="not_applicable",
        current_stage_code=status_code,
        attempt_count=0,
        base_report_version=None,
        base_generation_input_version=None,
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=None,
        next_attempt_at=now,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        created_at=now,
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
        AgentRunCreate(agent_code="unknown", report_id=report_id, idempotency_key=key)
    with pytest.raises(ValidationError):
        AgentRunCreate(
            agent_code="meeting_analysis",
            report_id=report_id,
            idempotency_key=key,
            guidance="이 지시는 보고서 작성에만 쓴다",
        )
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


def test_queue_migration_does_not_expire_legacy_running_jobs():
    migration = Path(__file__).parents[1] / "sql/20260901_0018_agent_run_queue.sql"
    sql = migration.read_text(encoding="utf-8")

    assert "SET lease_expires_at = now()" not in sql
    active_index = sql.split("agent_run_meeting_active_report_key", 1)[1].split(";", 1)[0]
    assert "request_hash IS NOT NULL" in active_index


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
    member = _member()
    report = _report(member)
    report.sales_deal_id = uuid4()
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
    created = db.added[0]
    assert created.source_refs == {"report_id": str(report.id)}
    assert created.request_snapshot["report_id"] == str(report.id)
    # CRM/보고서 입력 구성 전에 queued 행부터 커밋한다.
    assert created.input_snapshot == {}
    assert db.commit_count == 1


def test_meeting_analysis_run_snapshots_transcript(llm_ready, monkeypatch):
    member = _member()
    report = _report(member, transcript="고객은 다음 달 예산 승인을 검토합니다.")
    db = _Db(_Result(scalar=None), _Result(scalar=report))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "meeting_analysis",
                "report_id": str(report.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 202
    created = db.added[0]
    assert created.agent_code == "meeting_analysis"
    assert created.prompt_version == meeting_analysis.PROMPT_VERSION
    assert created.input_snapshot == {}
    assert created.request_snapshot["report_id"] == str(report.id)


def test_meeting_analysis_requires_transcript(llm_ready):
    member = _member()
    report = _report(member)
    db = _Db(_Result(scalar=None), _Result(scalar=report))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "meeting_analysis",
                "report_id": str(report.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 202
    created = db.added[0]
    assert created.status_code == "queued"
    assert created.input_snapshot == {}


@pytest.mark.anyio
async def test_execute_dispatches_meeting_analysis_and_saves_result(monkeypatch):
    """미팅 분석 결과와 모델 버전이 실행 이력에 저장되는지 검증한다."""
    member = _member()
    run = _run(member)
    run.agent_code = "meeting_analysis"
    run.input_snapshot = {"transcript": "고객이 다음 달 예산 승인을 검토합니다."}
    first = _Db(_Result(scalar=run))
    second = _Db(_Result(scalar=run))
    sessions = iter((first, second))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )

    output_snapshot = {
        "deal_assessment": {
            "features": {},
            "label": "watch",
            "high_probability": 0.5,
            "model_version": "test-deal-model-v1",
        }
    }

    async def fake_run(snapshot):
        """입력 스냅샷을 확인하고 고정된 미팅 분석 결과를 반환한다."""
        assert snapshot == run.input_snapshot
        log_agent_event(
            "meeting_analysis.model",
            input_tokens=21,
            output_tokens=9,
            total_tokens=30,
        )
        return SimpleNamespace(
            deal_assessment=SimpleNamespace(model_version="test-deal-model-v1"),
            model_dump=lambda **kwargs: output_snapshot,
        )

    monkeypatch.setattr(meeting_analysis, "run", fake_run)

    await agent_run_service.execute(run.id)

    assert run.status_code == "completed"
    assert run.output_snapshot == output_snapshot
    assert run.evidence == {
        "prompt_version": meeting_analysis.PROMPT_VERSION,
        "model_version": "test-deal-model-v1",
    }
    assert (run.input_tokens, run.output_tokens, run.total_tokens) == (21, 9, 30)
    assert first.commit_count == 1
    assert second.commit_count == 1


@pytest.mark.anyio
async def test_execute_records_model_failure_separately_from_llm_failure(monkeypatch, caplog):
    """모델 로드 실패가 LLM 오류와 구분되어 기록되는지 검증한다."""
    member = _member()
    run = _run(member)
    run.agent_code = "meeting_analysis"
    first = _Db(_Result(scalar=run))
    second = _Db(_Result(scalar=run))
    sessions = iter((first, second))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )

    async def fake_run(_snapshot):
        """모델을 사용할 수 없는 상황을 재현한다."""
        raise DealModelError("deal_model_unavailable")

    monkeypatch.setattr(meeting_analysis, "run", fake_run)

    await agent_run_service.execute(run.id)

    assert run.status_code == "failed"
    assert run.error_message == "deal_model_unavailable"
    assert str(run.id) in caplog.text
    assert '"type": "DealModelError"' in caplog.text
    assert '"stage": "meeting_analysis"' in caplog.text


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


def test_manager_cannot_generate_a_teammate_report(llm_ready):
    manager = _member(role="manager")
    teammate = _member()
    teammate.team_id = manager.team_id
    report = _report(teammate)
    db = _Db(_Result(scalar=None), _Result(scalar=report))

    with _client(db, manager) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "report_writing",
                "report_id": str(report.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "report_not_owned"}
    assert db.added == []


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
async def test_provider_errors_never_leak_url_or_key(llm_ready, monkeypatch, caplog):
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
    assert '"type": "ConnectError"' in caplog.text
    assert '"stage": "llm.request"' in caplog.text
    assert "provider.invalid" not in caplog.text
    assert "super-secret-key" not in caplog.text


@pytest.mark.anyio
async def test_schema_mismatch_is_rejected(llm_ready, monkeypatch, caplog):
    class _Response:
        status_code = 200
        headers = {"x-request-id": "req_schema_mismatch"}

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

    assert '"stage": "llm.output_validation"' in caplog.text
    assert '"request_id": "req_schema_mismatch"' in caplog.text
    assert '"status_code": 200' in caplog.text


def test_contract_management_select_candidates_run_uses_portfolio_snapshot(llm_ready, monkeypatch):
    fixed_snapshot = {"candidates": []}
    captured_args = {}

    async def _fake_build_candidate_selection_snapshot(db, member):
        captured_args["member"] = member
        return fixed_snapshot

    monkeypatch.setattr(
        contract_schedule_snapshots,
        "build_candidate_selection_snapshot",
        _fake_build_candidate_selection_snapshot,
    )

    member = _member()
    db = _Db(_Result(scalar=None))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "contract_management_select_candidates",
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 202
    created = db.added[0]
    assert created.agent_code == "contract_management_select_candidates"
    assert created.prompt_version == contract_management.SELECT_CANDIDATES_PROMPT_VERSION
    assert created.input_snapshot == {}
    assert created.source_refs == {}
    assert created.parent_run_id is None
    assert captured_args == {}


def test_contract_management_select_candidates_rejects_target_id():
    """대상을 지정하지 않는 실행이다 — 다른 agent_code 용 식별 필드를 섞어 보내면 거절한다."""
    with pytest.raises(ValidationError):
        AgentRunCreate(
            agent_code="contract_management_select_candidates",
            customer_company_id=uuid4(),
            idempotency_key=uuid4(),
        )


def test_contract_management_next_meeting_run_uses_company_snapshot(llm_ready, monkeypatch):
    fixed_snapshot = {"customer_company": {"id": "company-1"}, "risk_signals": []}

    async def _fake_build_next_meeting_snapshot(db, member, customer_company_id):
        return fixed_snapshot

    monkeypatch.setattr(
        contract_schedule_snapshots,
        "build_next_meeting_snapshot",
        _fake_build_next_meeting_snapshot,
    )

    member = _member()
    company_id = uuid4()
    db = _Db(_Result(scalar=None))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "contract_management_next_meeting",
                "customer_company_id": str(company_id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 202
    created = db.added[0]
    assert created.agent_code == "contract_management_next_meeting"
    assert created.prompt_version == contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION
    assert created.input_snapshot == {}
    assert created.source_refs == {"customer_company_id": str(company_id)}
    assert created.parent_run_id is None


def test_contract_management_briefing_requires_completed_schedule_parent(llm_ready):
    member = _member()
    other_agent_parent = _run(member, status_code="completed")
    other_agent_parent.agent_code = "meeting_analysis"  # 기대하는 agent_code 가 아니다.
    db = _Db(_Result(scalar=None), _Result(scalar=other_agent_parent))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "contract_management_briefing",
                "activity_id": str(uuid4()),
                "parent_run_id": str(other_agent_parent.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "parent_run_not_usable"}


def test_contract_management_briefing_without_parent_run(llm_ready, monkeypatch):
    """AI 제안을 거치지 않은 일정(캘린더 직접 입력, 팀장 대리 입력 등)도 parent_run_id 없이
    브리핑을 만들 수 있다 — activity_id만으로 충분하다."""
    fixed_snapshot = {
        "customer_company": {"id": "company-1"},
        "sales_deals": [],
        "approved_next_meeting": None,
        "document_summaries": [],
    }

    async def _fake_build_briefing_snapshot(db, member, activity_id):
        return fixed_snapshot

    monkeypatch.setattr(
        contract_schedule_snapshots, "build_briefing_snapshot", _fake_build_briefing_snapshot
    )

    member = _member()
    activity_id = uuid4()
    db = _Db(_Result(scalar=None))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "contract_management_briefing",
                "activity_id": str(activity_id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 202
    created = db.added[0]
    assert created.agent_code == "contract_management_briefing"
    assert created.parent_run_id is None
    assert created.source_refs == {"activity_id": str(activity_id)}
    assert created.input_snapshot == {}


def test_schedule_management_run_uses_parent_next_meeting_suggestion(llm_ready, monkeypatch):
    fixed_snapshot = {"sales_deal_id": "deal-1", "activities": []}

    async def _fake_build_schedule_snapshot(
        db, member, sales_deal_id, parent_run, starts_at, ends_at, duration
    ):
        assert parent_run is not None
        assert starts_at is None and ends_at is None and duration is None
        return fixed_snapshot

    monkeypatch.setattr(
        contract_schedule_snapshots, "build_schedule_snapshot", _fake_build_schedule_snapshot
    )

    member = _member()
    parent = _run(member, status_code="completed")
    parent.agent_code = "contract_management_next_meeting"
    db = _Db(_Result(scalar=None), _Result(scalar=parent))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "schedule_management",
                "sales_deal_id": str(uuid4()),
                "parent_run_id": str(parent.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == 202
    created = db.added[0]
    assert created.prompt_version == schedule_management.PROMPT_VERSION
    assert created.input_snapshot == {}
    assert created.parent_run_id == parent.id


def test_schedule_management_requires_preferred_window_without_parent_run():
    with pytest.raises(ValidationError):
        AgentRunCreate(
            agent_code="schedule_management",
            sales_deal_id=uuid4(),
            idempotency_key=uuid4(),
        )


@pytest.mark.anyio
async def test_execute_dispatches_contract_management_select_candidates(monkeypatch):
    member = _member()
    run = _run(member)
    run.agent_code = "contract_management_select_candidates"
    run.input_snapshot = {"candidates": []}
    first = _Db(_Result(scalar=run))
    second = _Db(_Result(scalar=run))
    sessions = iter((first, second))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )

    output_snapshot = {"candidates": []}

    async def fake_select(snapshot):
        assert snapshot == run.input_snapshot
        return SimpleNamespace(candidates=[], model_dump=lambda **kwargs: output_snapshot)

    monkeypatch.setattr(contract_management, "select_next_meeting_candidates", fake_select)

    await agent_run_service.execute(run.id)

    assert run.status_code == "completed"
    assert run.output_snapshot == output_snapshot
    assert run.evidence == {
        "prompt_version": contract_management.SELECT_CANDIDATES_PROMPT_VERSION,
        "candidate_count": 0,
    }
    assert first.commit_count == 1
    assert second.commit_count == 1


@pytest.mark.anyio
async def test_execute_dispatches_contract_management_next_meeting(monkeypatch):
    member = _member()
    run = _run(member)
    run.agent_code = "contract_management_next_meeting"
    run.input_snapshot = {"customer_company": {"id": "company-1"}, "risk_signals": []}
    first = _Db(_Result(scalar=run))
    second = _Db(_Result(scalar=run))
    sessions = iter((first, second))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )

    output_snapshot = {
        "risks": [],
        "missing_information": [],
        "recommended_actions": [],
        "next_meeting_suggestion": None,
    }

    async def fake_propose(snapshot):
        assert snapshot == run.input_snapshot
        return SimpleNamespace(risks=[], model_dump=lambda **kwargs: output_snapshot)

    monkeypatch.setattr(contract_management, "propose_next_meeting", fake_propose)

    await agent_run_service.execute(run.id)

    assert run.status_code == "completed"
    assert run.output_snapshot == output_snapshot
    assert run.evidence == {
        "prompt_version": contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
        "risk_count": 0,
    }
    assert first.commit_count == 1
    assert second.commit_count == 1


@pytest.mark.anyio
async def test_execute_dispatches_schedule_management(monkeypatch):
    member = _member()
    run = _run(member)
    run.agent_code = "schedule_management"
    run.input_snapshot = {"sales_deal_id": "deal-1", "activities": []}
    first = _Db(_Result(scalar=run))
    second = _Db(_Result(scalar=run))
    sessions = iter((first, second))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )

    output_snapshot = {"schedule_candidates": [], "conflicts": []}

    async def fake_run(snapshot):
        assert snapshot == run.input_snapshot
        return SimpleNamespace(schedule_candidates=[], model_dump=lambda **kwargs: output_snapshot)

    monkeypatch.setattr(schedule_management, "run", fake_run)

    await agent_run_service.execute(run.id)

    assert run.status_code == "completed"
    assert run.output_snapshot == output_snapshot
    assert run.evidence == {
        "prompt_version": schedule_management.PROMPT_VERSION,
        "candidate_count": 0,
    }


def test_meeting_generation_domain_routes_create_and_resume_latest(llm_ready):
    member = _member()
    report = _report(member, transcript="고객이 예산 검토 일정을 공유했다.")
    report.report_kind = "meeting"
    report.version = 7
    report.generation_input_version = 3
    create_db = _Db(_Result(scalar=None), _Result(scalar=report))

    with _client(create_db, member) as client:
        response = client.post(
            f"/api/reports/{report.id}/generations",
            headers={"Origin": ORIGIN},
            json={"idempotency_key": str(uuid4())},
        )

    assert response.status_code == 202
    run = create_db.added[0]
    assert run.agent_code == "meeting_processing"
    assert run.report_id == report.id
    assert run.base_report_version == 7
    assert run.base_generation_input_version == 3
    assert run.apply_status == "pending"
    assert run.input_snapshot == {}

    latest_db = _Db(_Result(scalar=report.id), _Result(scalar=run))
    with _client(latest_db, member) as client:
        latest = client.get(f"/api/reports/{report.id}/generations/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == str(run.id)
    assert latest.json()["current_stage_code"] == "queued"


def test_second_active_meeting_generation_returns_conflict(llm_ready):
    member = _member()
    report = _report(member, transcript="고객이 예산 검토 일정을 공유했다.")
    report.report_kind = "meeting"
    cause = RuntimeError("duplicate")
    cause.constraint_name = "agent_run_meeting_active_report_key"
    original = RuntimeError("adapter")
    original.__cause__ = cause
    error = IntegrityError("insert", {}, original)

    class ConflictDb(_Db):
        async def flush(self):
            raise error

    db = ConflictDb(_Result(scalar=None), _Result(scalar=report), _Result(scalar=None))
    with _client(db, member) as client:
        response = client.post(
            f"/api/reports/{report.id}/generations",
            headers={"Origin": ORIGIN},
            json={"idempotency_key": str(uuid4())},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "meeting_generation_in_progress"}


@pytest.mark.anyio
async def test_applied_partial_meeting_run_can_be_reassigned():
    member = _member()
    parent = _run(member, status_code="partial")
    parent.agent_code = "meeting_processing"
    parent.apply_status = "applied"

    found = await agent_run_service._parent_run_or_409(
        _Db(_Result(scalar=parent)),
        member,
        parent.id,
        expected_agent_code="meeting_processing",
    )

    assert found is parent


@pytest.mark.anyio
async def test_manual_apply_endpoint_commits_only_in_meeting_processing(monkeypatch):
    member = _member()
    db = _Db()
    expected = object()

    async def apply(current_db, current_member, run_id):
        assert (current_db, current_member) == (db, member)
        assert isinstance(run_id, UUID)
        return expected

    monkeypatch.setattr(agent_runs.meeting_processing, "apply", apply)

    assert await agent_runs.apply_meeting_run(uuid4(), member, db) is expected


@pytest.mark.anyio
async def test_worker_requeues_only_transient_provider_errors(monkeypatch):
    member = _member()
    run = _run(member)
    run.request_hash = "0" * 64
    run.input_snapshot = {"template_snapshot": TEMPLATE}
    claim_db = _Db(_Result(scalar=run))
    finish_db = _Db(_Result(scalar=run))
    sessions = iter((claim_db, finish_db))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )

    async def fail(_snapshot):
        raise llm.LLMError("llm_request_failed:ReadTimeout")

    monkeypatch.setattr(report_writing, "run", fail)
    await agent_run_service.execute(run.id)

    assert run.status_code == "queued"
    assert run.current_stage_code == "retry_wait"
    assert run.attempt_count == 1
    assert run.error_code == "llm_request_failed:ReadTimeout"
    assert run.finished_at is None
    assert run.next_attempt_at > datetime.now(UTC)


@pytest.mark.anyio
async def test_direct_legacy_run_does_not_enter_unclaimed_retry_queue(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")
    run.attempt_count = 1
    run.lease_owner = "direct-bridge"
    run.request_hash = None
    db = _Db(SimpleNamespace(rowcount=1))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )

    await agent_worker._fail(
        run,
        "direct-bridge",
        "llm_request_failed:ReadTimeout",
    )

    assert run.status_code == "failed"
    assert run.current_stage_code == "failed"
    assert run.finished_at is not None


@pytest.mark.anyio
async def test_worker_fails_non_retryable_validation_once(monkeypatch):
    member = _member()
    run = _run(member)
    run.input_snapshot = {"template_snapshot": TEMPLATE}
    claim_db = _Db(_Result(scalar=run))
    finish_db = _Db(_Result(scalar=run))
    sessions = iter((claim_db, finish_db))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )

    async def fail(_snapshot):
        raise llm.LLMError("llm_output_schema_mismatch")

    monkeypatch.setattr(report_writing, "run", fail)
    await agent_run_service.execute(run.id)

    assert run.status_code == "failed"
    assert run.attempt_count == 1
    assert run.error_code == "llm_output_schema_mismatch"
    assert run.finished_at is not None


@pytest.mark.anyio
async def test_worker_completion_rejects_lost_lease(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")
    run.agent_code = "meeting_analysis"
    run.lease_owner = "old-worker"
    db = _Db(SimpleNamespace(rowcount=0))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )
    output = SimpleNamespace(
        deal_assessment=SimpleNamespace(model_version="test-model"),
        model_dump=lambda **_kwargs: {"deal_assessment": {}},
    )

    with pytest.raises(RuntimeError, match="agent_run_lease_lost"):
        await agent_worker._complete(run, "old-worker", output)

    assert run.status_code == "running"
    assert db.commit_count == 0


@pytest.mark.anyio
async def test_expired_lease_is_reclaimed_with_skip_locked(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")
    run.request_hash = "a" * 64
    run.attempt_count = 1
    run.lease_owner = "dead-worker"
    run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db = _Db(_Result(scalar=run))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )

    claimed = await agent_worker.claim("replacement-worker")

    assert claimed is run
    assert run.attempt_count == 2
    assert run.lease_owner == "replacement-worker"
    assert run.lease_expires_at > datetime.now(UTC)
    assert "FOR UPDATE" in str(db.statements[0])
    assert db.statements[0]._for_update_arg.skip_locked is True


@pytest.mark.anyio
async def test_general_worker_only_claims_durable_requests(monkeypatch):
    db = _Db(_Result(scalar=None))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )

    assert await agent_worker.claim("general-worker") is None

    statement = str(db.statements[0])
    assert "agent_run.request_hash IS NOT NULL" in statement


@pytest.mark.anyio
async def test_direct_bridge_can_claim_legacy_system_run(monkeypatch):
    member = _member()
    run = _run(member)
    run.requested_by_member_id = None
    run.request_hash = None
    db = _Db(_Result(scalar=run))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )

    claimed = await agent_worker.claim("direct-bridge", run.id)

    assert claimed is run
    assert "agent_run.request_hash IS NOT NULL" not in str(db.statements[0])


@pytest.mark.anyio
async def test_worker_schema_check_is_read_only(monkeypatch):
    rows = [
        (table_name, column_name)
        for table_name, columns in agent_worker.REQUIRED_SCHEMA.items()
        for column_name in (columns or {"id"})
    ]
    db = _Db(SimpleNamespace(all=lambda: rows))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )

    await agent_worker.check_schema()

    assert db.commit_count == 0
    assert len(db.statements) == 1


@pytest.mark.anyio
async def test_worker_schema_check_reports_missing_table(monkeypatch):
    rows = [
        (table_name, column_name)
        for table_name, columns in agent_worker.REQUIRED_SCHEMA.items()
        if table_name != "report_source"
        for column_name in (columns or {"id"})
    ]
    db = _Db(SimpleNamespace(all=lambda: rows))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )

    with pytest.raises(RuntimeError, match="agent_worker_schema_incomplete:report_source"):
        await agent_worker.check_schema()


@pytest.mark.anyio
async def test_meeting_output_resume_skips_llm_and_finishes_apply_atomically(monkeypatch):
    member = _member()
    run = _run(member)
    run.agent_code = "meeting_processing"
    run.apply_status = "pending"
    run.output_snapshot = {"already": "persisted"}
    output = SimpleNamespace(errors={}, model_dump=lambda **kwargs: run.output_snapshot)
    claim_db = _Db(_Result(scalar=run))
    apply_db = _Db(_Result(scalar=run))
    sessions = iter((claim_db, apply_db))
    monkeypatch.setattr(
        agent_run_service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )
    monkeypatch.setattr(
        agent_run_service.meeting_processing.MeetingProcessingOutput,
        "model_validate",
        staticmethod(lambda value: output),
    )

    async def not_called(*_args):
        pytest.fail("저장된 출력을 재개할 때 LLM을 다시 호출하면 안 됩니다.")

    async def apply_output(db, current):
        assert db is apply_db
        assert current.output_snapshot == {"already": "persisted"}
        return "applied"

    monkeypatch.setattr(agent_run_service, "dispatch", not_called)
    monkeypatch.setattr(
        agent_run_service.meeting_processing, "apply_output", apply_output, raising=False
    )

    await agent_run_service.execute(run.id)

    assert run.status_code == "completed"
    assert run.apply_status == "applied"
    assert run.lease_owner is None
    assert apply_db.commit_count == 1


@pytest.mark.anyio
async def test_prepare_claimed_refreshes_the_run_input_snapshot(monkeypatch):
    """worker 가 만든 입력을 run 에 반영하지 않으면 evidence 가 늘 0 을 기록한다."""
    member_id, team_id = uuid4(), uuid4()
    built = {"document_context": {"summaries": [{"file_id": "f"}], "sources": [{"chunk_id": "c"}]}}
    request_snapshot = {
        "agent_code": "contract_management_briefing",
        "activity_id": str(uuid4()),
        "idempotency_key": str(uuid4()),
    }
    run = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        agent_code="contract_management_briefing",
        requested_by_member_id=member_id,
        request_snapshot=request_snapshot,
        request_hash=agent_run_service._request_hash(request_snapshot),
        input_snapshot={},
        base_report_version=None,
        base_generation_input_version=None,
    )

    class _Session:
        async def execute(self, _statement):
            if not hasattr(self, "_seen"):
                self._seen = True
                return SimpleNamespace(
                    scalar_one_or_none=lambda: SimpleNamespace(id=member_id, team_id=team_id)
                )
            return SimpleNamespace(rowcount=1)

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    async def _build(_payload, _member, _session):
        return ("v4", built, {}, None, None, None)

    monkeypatch.setattr(agent_run_service, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(agent_run_service, "_build_run_input", _build)

    _code, input_snapshot, _requester = await agent_run_service.prepare_claimed(run, "worker-1")

    assert input_snapshot == built
    # 호출자가 든 run 도 같은 입력을 봐야 한다.
    assert run.input_snapshot == built
    evidence = agent_run_service.evidence(
        "contract_management_briefing",
        SimpleNamespace(risks=[]),
        run.input_snapshot,
    )
    assert evidence["document_count"] == 1
    assert evidence["chunk_count"] == 1
