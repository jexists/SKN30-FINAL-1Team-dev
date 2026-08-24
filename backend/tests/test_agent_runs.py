import json
from datetime import UTC, date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents import meeting_analysis, report_writing, schedule_management
from app.agents.report_writing import ReportDraftOutput
from app.api import agent_runs
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.agent import AgentApproval, AgentRun
from app.models.content import Report
from app.models.crm import Activity, CustomerCompany, SupportRequest
from app.models.sales import SalesDeal, SalesPipelineStage
from app.models.workspace import Member
from app.schemas.agent_runs import AgentApprovalCreate, AgentRunCreate
from app.services import agent_runs as agent_run_service
from app.services import llm

_SEOUL = ZoneInfo("Asia/Seoul")
_KST = timezone(timedelta(hours=9))

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


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=_MISSING, scalar_values=None):
        self.scalar = scalar
        self.scalar_values = [] if scalar_values is None else scalar_values

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalars(self):
        return _Scalars(self.scalar_values)


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


def test_meeting_analysis_run_snapshots_transcript(llm_ready, monkeypatch):
    scheduled: list[UUID] = []

    async def _fake_execute(run_id: UUID) -> None:
        scheduled.append(run_id)

    monkeypatch.setattr(agent_run_service, "execute", _fake_execute)

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
    assert created.input_snapshot == {"transcript": report.transcript}
    assert scheduled == [created.id]


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

    assert response.status_code == 422
    assert response.json() == {"detail": "transcript_required"}


@pytest.mark.anyio
async def test_execute_dispatches_meeting_analysis_and_saves_result(monkeypatch):
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
            "model_version": "deal-dummy-uniform-v0",
        }
    }

    async def fake_run(snapshot):
        assert snapshot == run.input_snapshot
        return SimpleNamespace(
            deal_assessment=SimpleNamespace(model_version="deal-dummy-uniform-v0"),
            model_dump=lambda: output_snapshot,
        )

    monkeypatch.setattr(meeting_analysis, "run", fake_run)

    await agent_run_service.execute(run.id)

    assert run.status_code == "completed"
    assert run.output_snapshot == output_snapshot
    assert run.evidence == {
        "prompt_version": meeting_analysis.PROMPT_VERSION,
        "model_version": "deal-dummy-uniform-v0",
    }
    assert first.commit_count == 1
    assert second.commit_count == 1


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


def _company(member: Member) -> CustomerCompany:
    return CustomerCompany(
        id=uuid4(),
        team_id=member.team_id,
        name="합성 고객사",
        region_code=None,
        created_at=NOW,
    )


def _stage(*, phase_code: str = "sales") -> SalesPipelineStage:
    return SalesPipelineStage(
        id=uuid4(),
        sales_pipeline_id=uuid4(),
        stage_code="needs_validation",
        name="니즈 검증",
        tone="gray",
        phase_code=phase_code,
        outcome_code="in_progress",
        position=0,
        created_at=NOW,
        updated_at=NOW,
    )


def _deal(member: Member, **overrides) -> SalesDeal:
    base = dict(
        id=uuid4(),
        team_id=member.team_id,
        deal_no="D-0001",
        customer_company_id=uuid4(),
        customer_contact_id=None,
        owner_member_id=member.id,
        product_id=None,
        sales_pipeline_id=uuid4(),
        sales_pipeline_stage_id=uuid4(),
        title="합성 딜",
        description=None,
        sales_deal_type_id=uuid4(),
        deal_amount=1_000_000,
        opened_on=date(2026, 1, 1),
        closed_on=None,
        quote_no=None,
        quote_issued_on=None,
        quote_valid_until=None,
        contract_no=None,
        contract_signed_on=None,
        contract_ends_on=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        stage_position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(overrides)
    return SalesDeal(**base)


def _support_request(member: Member, *, is_urgent: bool, status_code: str) -> SupportRequest:
    return SupportRequest(
        id=uuid4(),
        team_id=member.team_id,
        customer_contact_id=uuid4(),
        assignee_member_id=member.id,
        title="긴급 문의",
        body="설치 오류가 발생합니다.",
        is_urgent=is_urgent,
        status_code=status_code,
        registered_at=NOW,
    )


def _activity(member: Member, **overrides) -> Activity:
    base = dict(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        customer_contact_id=None,
        end_user_contact_id=None,
        activity_type="meeting",
        activity_category_id=uuid4(),
        title="합성 활동",
        starts_at=NOW,
        ends_at=NOW,
        all_day=False,
        due_at=None,
        location=None,
        activity_action_tag_id=None,
        completed_at=None,
        note=None,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
        product_id=None,
        sales_deal_id=None,
        purchase_order_id=None,
    )
    base.update(overrides)
    return Activity(**base)


def _schedule_run(
    member: Member, *, status_code: str = "completed", parent_run_id: UUID | None = None
) -> tuple[AgentRun, UUID]:
    deal_id = uuid4()
    run = AgentRun(
        id=uuid4(),
        team_id=member.team_id,
        parent_run_id=parent_run_id,
        requested_by_member_id=member.id,
        agent_code="schedule_management",
        trigger_code="user",
        idempotency_key=uuid4(),
        status_code=status_code,
        llm_model_name="test-model",
        prompt_version=schedule_management.PROMPT_VERSION,
        source_refs={"sales_deal_id": str(deal_id), "activity_ids": []},
        input_snapshot={
            "request": {
                "owner_member_id": str(member.id),
                "companion_member_ids": [],
                "preferred_starts_at": "2026-08-25T09:00:00+09:00",
                "preferred_ends_at": "2026-08-25T18:00:00+09:00",
                "duration_minutes": 60,
                "activity_type": "meeting",
            }
        },
        output_snapshot={"schedule_candidates": [], "conflicts": []},
        evidence=None,
        error_message=None,
        started_at=NOW,
        finished_at=NOW,
    )
    return run, deal_id


def _approval_payload(**overrides) -> AgentApprovalCreate:
    base = dict(
        idempotency_key=uuid4(),
        title="다음 계약 협의",
        category_code="meeting",
        starts_at=datetime(2026, 8, 25, 14, tzinfo=_KST),
        ends_at=datetime(2026, 8, 25, 15, tzinfo=_KST),
    )
    base.update(overrides)
    return AgentApprovalCreate(**base)


@pytest.mark.anyio
async def test_contract_source_blocks_other_team_company():
    member = _member()
    db = _Db(_Result(scalar=None))
    payload = AgentRunCreate(
        agent_code="contract_management",
        idempotency_key=uuid4(),
        customer_company_id=uuid4(),
    )

    with pytest.raises(HTTPException) as caught:
        await agent_run_service._contract_source(db, member, payload)

    assert caught.value.status_code == 404
    assert caught.value.detail == "customer_company_not_found"


@pytest.mark.anyio
async def test_schedule_source_blocks_other_team_deal():
    member = _member()
    db = _Db(_Result(scalar=None))
    payload = AgentRunCreate(
        agent_code="schedule_management",
        idempotency_key=uuid4(),
        sales_deal_id=uuid4(),
        owner_member_id=uuid4(),
        preferred_starts_at=datetime(2026, 8, 25, 9, tzinfo=_KST),
        preferred_ends_at=datetime(2026, 8, 25, 18, tzinfo=_KST),
        duration_minutes=60,
        activity_type="meeting",
    )

    with pytest.raises(HTTPException) as caught:
        await agent_run_service._schedule_source(db, member, payload)

    assert caught.value.status_code == 404
    assert caught.value.detail == "sales_deal_not_found"


@pytest.mark.anyio
async def test_contract_source_computes_deterministic_risk_signals():
    member = _member()
    today = datetime.now(UTC).astimezone(_SEOUL).date()
    stage = _stage(phase_code="sales")
    deal_overdue = _deal(
        member,
        sales_pipeline_stage_id=stage.id,
        contract_ends_on=today - timedelta(days=2),
    )
    deal_soon = _deal(
        member,
        sales_pipeline_stage_id=stage.id,
        quote_valid_until=today + timedelta(days=3),
    )
    urgent_support = _support_request(member, is_urgent=True, status_code="in_progress")
    company = _company(member)

    db = _Db(
        _Result(scalar=company),
        _Result(scalar_values=[deal_overdue, deal_soon]),
        _Result(scalar_values=[]),  # activities
        _Result(scalar_values=[]),  # reports
        _Result(scalar_values=[urgent_support]),  # support_requests
        _Result(scalar_values=[stage]),  # pipeline stages
    )
    payload = AgentRunCreate(
        agent_code="contract_management",
        idempotency_key=uuid4(),
        customer_company_id=company.id,
    )

    snapshot, _ = await agent_run_service._contract_source(db, member, payload)

    signals = {(item["code"], item["severity"]) for item in snapshot["risk_signals"]}
    assert ("contract_expiring", "high") in signals
    assert ("quote_expiring", "medium") in signals
    assert ("unresolved_support", "high") in signals
    assert not any(code == "missing_contract_information" for code, _ in signals)


@pytest.mark.anyio
async def test_approve_schedule_creates_activity_report_and_approval():
    member = _member()
    run, deal_id = _schedule_run(member)
    deal = _deal(member, id=deal_id)
    category = SimpleNamespace(id=uuid4())

    db = _Db(
        _Result(scalar=None),  # existing approval lookup
        _Result(scalar=run),  # run lock
        _Result(scalar=deal),  # deal re-fetch
        _Result(scalar_values=[member.id]),  # owner/companion membership
        _Result(scalar=category),  # category
        _Result(scalar_values=[]),  # candidate activities (no conflicts)
    )
    payload = _approval_payload()

    result = await agent_run_service.approve_schedule(run.id, payload, member, db)

    assert result.agent_run_id == run.id
    assert db.commit_count == 1
    assert db.rollback_count == 0

    activity = next(obj for obj in db.added if isinstance(obj, Activity))
    report = next(obj for obj in db.added if isinstance(obj, Report))
    approval = next(obj for obj in db.added if isinstance(obj, AgentApproval))

    assert activity.sales_deal_id == deal.id
    assert activity.owner_member_id == member.id
    assert report.report_kind == "contract_status_briefing"
    assert report.status_code == "draft"
    assert report.source_activity_id == activity.id
    assert approval.result_refs == {
        "activity_id": str(activity.id),
        "report_id": str(report.id),
    }
    assert result.activity_id == activity.id
    assert result.report_id == report.id


@pytest.mark.anyio
async def test_approve_schedule_is_idempotent():
    member = _member()
    key = uuid4()
    existing = AgentApproval(
        id=uuid4(),
        agent_run_id=uuid4(),
        team_id=member.team_id,
        requested_by_member_id=member.id,
        idempotency_key=key,
        decision_snapshot={},
        result_refs={"activity_id": str(uuid4()), "report_id": str(uuid4())},
        created_at=NOW,
    )
    db = _Db(_Result(scalar=existing))
    payload = _approval_payload(idempotency_key=key)

    result = await agent_run_service.approve_schedule(uuid4(), payload, member, db)

    assert result.id == existing.id
    assert db.commit_count == 0
    assert db.added == []


@pytest.mark.anyio
async def test_approve_schedule_rejects_when_run_not_completed():
    member = _member()
    run, _ = _schedule_run(member, status_code="running")
    db = _Db(_Result(scalar=None), _Result(scalar=run))
    payload = _approval_payload()

    with pytest.raises(HTTPException) as caught:
        await agent_run_service.approve_schedule(run.id, payload, member, db)

    assert caught.value.status_code == 409
    assert caught.value.detail == "agent_run_not_completed"
    assert db.rollback_count == 1


@pytest.mark.anyio
async def test_approve_schedule_rejects_stale_deal():
    member = _member()
    run, _ = _schedule_run(member)
    db = _Db(_Result(scalar=None), _Result(scalar=run), _Result(scalar=None))
    payload = _approval_payload()

    with pytest.raises(HTTPException) as caught:
        await agent_run_service.approve_schedule(run.id, payload, member, db)

    assert caught.value.status_code == 409
    assert caught.value.detail == "stale_agent_result"
    assert db.rollback_count == 1


@pytest.mark.anyio
async def test_approve_schedule_rejects_time_conflict():
    member = _member()
    run, deal_id = _schedule_run(member)
    deal = _deal(member, id=deal_id)
    category = SimpleNamespace(id=uuid4())
    conflicting = _activity(
        member,
        sales_deal_id=deal_id,
        starts_at=datetime(2026, 8, 25, 14, 30, tzinfo=_KST),
        ends_at=datetime(2026, 8, 25, 15, 30, tzinfo=_KST),
    )

    db = _Db(
        _Result(scalar=None),
        _Result(scalar=run),
        _Result(scalar=deal),
        _Result(scalar_values=[member.id]),
        _Result(scalar=category),
        _Result(scalar_values=[conflicting]),
    )
    payload = _approval_payload()

    with pytest.raises(HTTPException) as caught:
        await agent_run_service.approve_schedule(run.id, payload, member, db)

    assert caught.value.status_code == 409
    assert caught.value.detail == "schedule_conflict"
    assert db.rollback_count == 1
