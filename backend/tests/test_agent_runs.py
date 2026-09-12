import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import openai
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from langchain_openai import StreamChunkTimeoutError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from test_report_deepagents_runtime import ScriptedModel
from test_report_writing_deep import sample

from app.agents import (
    contract_management,
    schedule_management,
)
from app.agents.meeting import features as meeting_analysis
from app.agents.reports import harness, review_delivery
from app.agents.reports import meeting as report_writing_deep
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
from app.schemas.reports import REPORT_BODY_MAX_LENGTH
from app.services import agent_runs as service
from app.services import agent_worker, contract_schedule_snapshots

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
TEMPLATE = {"fields": [{"id": "body", "label": "본문"}]}
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
        if "from public.report_attachment" in str(statement).lower():
            return _Result(scalars=[])
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


@pytest.mark.parametrize(
    ("agent_code", "identifying", "expected_prompt", "expected_refs"),
    [
        (
            "contract_management_select_candidates",
            {},
            contract_management.SELECT_CANDIDATES_PROMPT_VERSION,
            {},
        ),
        (
            "contract_management_next_meeting",
            {"customer_company_id": uuid4()},
            contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
            None,
        ),
        (
            "contract_management_briefing",
            {"activity_id": uuid4()},
            contract_management.GENERATE_BRIEFING_PROMPT_VERSION,
            None,
        ),
        (
            "schedule_management",
            {
                "sales_deal_id": uuid4(),
                "preferred_starts_at": "2026-08-18T09:00:00+09:00",
                "preferred_ends_at": "2026-08-18T12:00:00+09:00",
                "duration_minutes": 60,
            },
            schedule_management.PROMPT_VERSION,
            None,
        ),
    ],
)
def test_generic_agent_requests_are_queued(
    llm_ready, agent_code, identifying, expected_prompt, expected_refs
):
    member = _member()
    db = _Db(_Result(scalar=None))
    payload = {
        "agent_code": agent_code,
        "idempotency_key": str(uuid4()),
        **{
            key: str(value) if isinstance(value, UUID) else value
            for key, value in identifying.items()
        },
    }

    with _client(db, member) as client:
        response = client.post("/api/agent-runs", headers={"Origin": ORIGIN}, json=payload)

    assert response.status_code == 202
    run = db.added[0]
    assert run.agent_code == agent_code
    assert run.prompt_version == expected_prompt
    assert run.report_id is None and run.input_snapshot == {}
    assert run.source_refs == (
        expected_refs
        if expected_refs is not None
        else {
            key: str(value)
            for key, value in identifying.items()
            if key in {"customer_company_id", "sales_deal_id", "activity_id"}
        }
    )
    assert run.parent_run_id is None
    assert db.commit_count == 1


@pytest.mark.parametrize(
    ("agent_code", "parent_code", "identifying"),
    [
        ("contract_management_briefing", "schedule_management", {"activity_id": uuid4()}),
        (
            "schedule_management",
            "contract_management_next_meeting",
            {"sales_deal_id": uuid4()},
        ),
    ],
)
def test_parented_agent_requests_keep_valid_parent(llm_ready, agent_code, parent_code, identifying):
    member = _member()
    parent = _run(member, status_code="completed")
    parent.agent_code = parent_code
    db = _Db(_Result(scalar=None), _Result(scalar=parent))
    payload = {
        "agent_code": agent_code,
        "parent_run_id": str(parent.id),
        "idempotency_key": str(uuid4()),
        **{key: str(value) for key, value in identifying.items()},
    }

    with _client(db, member) as client:
        response = client.post("/api/agent-runs", headers={"Origin": ORIGIN}, json=payload)

    assert response.status_code == 202
    assert db.added[0].parent_run_id == parent.id
    assert db.added[0].source_refs["parent_run_id"] == str(parent.id)


@pytest.mark.parametrize(
    ("parent_code", "parent_status", "parent_result", "expected_status"),
    [
        ("contract_management_next_meeting", "completed", "parent", 409),
        ("schedule_management", "running", "parent", 409),
        ("schedule_management", "completed", None, 404),
    ],
)
def test_parent_run_requires_expected_type_completed_status_and_scope(
    llm_ready, parent_code, parent_status, parent_result, expected_status
):
    member = _member()
    parent = _run(member, status_code=parent_status)
    parent.agent_code = parent_code
    db = _Db(
        _Result(scalar=None),
        _Result(scalar=parent if parent_result == "parent" else None),
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json={
                "agent_code": "contract_management_briefing",
                "activity_id": str(uuid4()),
                "parent_run_id": str(parent.id),
                "idempotency_key": str(uuid4()),
            },
        )

    assert response.status_code == expected_status
    assert db.added == []
    if expected_status == 404:
        parent_query = str(db.statements[1])
        assert "agent_run.team_id" in parent_query
        assert "agent_run.requested_by_member_id" in parent_query


def test_same_generic_idempotency_key_returns_existing_run(llm_ready):
    member = _member()
    key = uuid4()
    payload = AgentRunCreate(
        agent_code="contract_management_select_candidates",
        idempotency_key=key,
    )
    existing = _run(member, status_code="running", key=key)
    existing.agent_code = payload.agent_code
    existing.request_snapshot = payload.model_dump(mode="json")
    existing.request_hash = service._request_hash(existing.request_snapshot)
    db = _Db(_Result(scalar=existing))

    with _client(db, member) as client:
        response = client.post(
            "/api/agent-runs",
            headers={"Origin": ORIGIN},
            json=payload.model_dump(mode="json"),
        )

    assert response.status_code == 202
    assert response.json()["id"] == str(existing.id)
    assert response.json()["status_code"] == "running"
    assert db.added == [] and db.commit_count == 0


def test_schedule_management_requires_preferred_window_without_parent_run():
    with pytest.raises(ValidationError):
        AgentRunCreate(
            agent_code="schedule_management",
            sales_deal_id=uuid4(),
            idempotency_key=uuid4(),
        )


def test_report_generation_input_has_one_typed_scope():
    attachment_id = uuid4()
    meeting = ReportGenerationCreate(
        idempotency_key=uuid4(),
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        source_activity_id=uuid4(),
        sales_deal_ids=[uuid4()],
        template_snapshot=TEMPLATE,
        content={},
        transcript="고객이 다음 달 예산을 검토합니다.",
        attachments=[
            {
                "id": attachment_id,
                "kind": "pdf",
                "name": "memo.pdf",
                "byte_size": 123,
                "extract": "서버가 추출한 메모",
            }
        ],
    )
    assert service.generation_scope_key(meeting).startswith("meeting:")
    assert meeting.attachments[0].id == attachment_id
    audio_only = ReportGenerationCreate(
        idempotency_key=uuid4(),
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        source_activity_id=uuid4(),
        template_snapshot=TEMPLATE,
        content={},
        attachments=[
            {
                "id": uuid4(),
                "kind": "audio",
                "name": "memo.m4a",
                "byte_size": 123,
                "extract": "음성에서 추출한 원문",
            }
        ],
    )
    assert audio_only.transcript is None
    assert audio_only.effective_meeting_transcript() == "음성에서 추출한 원문"
    no_deal_meeting = ReportGenerationCreate(
        idempotency_key=uuid4(),
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        source_activity_id=uuid4(),
        sales_deal_ids=[],
        template_snapshot=TEMPLATE,
        content={},
        transcript="고객사가 신규 사업 방향을 공유했습니다.",
    )
    assert no_deal_meeting.sales_deal_ids == []
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
    with pytest.raises(ValidationError, match="transcript_required"):
        ReportGenerationCreate(
            idempotency_key=uuid4(),
            report_kind="meeting",
            report_date=date(2026, 8, 17),
            source_activity_id=uuid4(),
            template_snapshot=TEMPLATE,
            content={},
            attachments=[
                {
                    "id": uuid4(),
                    "kind": "pdf",
                    "name": "memo.pdf",
                    "byte_size": 123,
                    "extract": "PDF에서 추출한 자료",
                }
            ],
        )
    with pytest.raises(ValidationError):
        ReportGenerationScope(report_kind="weekly", period_start=date(2026, 8, 1))


@pytest.mark.parametrize("kind", ["audio", "image", "pdf"])
def test_meeting_source_purpose_accepts_extraction_without_direct_input(kind):
    values = {
        **_daily_payload(),
        "report_kind": "meeting",
        "source_activity_id": str(uuid4()),
        "attachments": [
            {
                "id": str(uuid4()),
                "kind": kind,
                "name": "미팅 기록",
                "byte_size": 1,
                "extract": "확인한 미팅 원문",
                "purpose": "meeting_source",
            }
        ],
    }
    payload = ReportGenerationCreate.model_validate(values)
    assert payload.transcript is None
    assert payload.effective_meeting_transcript() == "확인한 미팅 원문"
    values["attachments"][0]["purpose"] = "reference"
    with pytest.raises(ValidationError, match="transcript_required"):
        ReportGenerationCreate.model_validate(values)


@pytest.mark.parametrize("kind", ["audio", "image", "pdf"])
def test_period_generation_rejects_source_purpose_but_keeps_legacy_attachments(kind):
    attachment = {
        "id": str(uuid4()),
        "kind": kind,
        "name": "배경 자료",
        "byte_size": 1,
        "extract": "미팅 발언이 아닌 참고자료",
    }
    for purpose in (None, "reference"):
        value = attachment if purpose is None else {**attachment, "purpose": purpose}
        payload = ReportGenerationCreate.model_validate(_daily_payload(attachments=[value]))
        assert payload.transcript is None
        assert payload.attachments[0].extract == attachment["extract"]
    with pytest.raises(ValidationError, match="meeting_attachment_not_supported"):
        ReportGenerationCreate.model_validate(
            _daily_payload(attachments=[{**attachment, "purpose": "meeting_source"}])
        )


@pytest.mark.anyio
async def test_legacy_generation_reconnect_and_replay_preserve_attachment_hash(llm_ready):
    member = _member()
    legacy = {
        "idempotency_key": str(uuid4()),
        "report_kind": "meeting",
        "report_date": "2026-08-17",
        "period_start": None,
        "period_end": None,
        "source_activity_id": str(uuid4()),
        "sales_deal_ids": [],
        "attachments": [
            {
                "id": str(uuid4()),
                "kind": "audio",
                "name": "legacy.m4a",
                "byte_size": 1,
                "extract": "이전 음성 원문",
            }
        ],
        "template_snapshot": TEMPLATE,
        "content": {},
        "transcript": None,
        "guidance": None,
    }
    existing = _run(member, key=UUID(legacy["idempotency_key"]), status_code="running")
    existing.agent_code = "meeting_processing"
    existing.scope_key = f"meeting:{legacy['source_activity_id']}"
    existing.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    existing.request_snapshot = {
        key: value for key, value in legacy.items() if key != "idempotency_key"
    }
    existing.request_hash = service._request_hash(legacy)
    restored = service._generation_input_read(existing, member.id)
    assert restored is not None
    assert restored.model_dump(mode="json") == existing.request_snapshot
    payload = ReportGenerationCreate.model_validate(
        {
            **restored.model_dump(mode="json"),
            "idempotency_key": legacy["idempotency_key"],
        }
    )
    db = _Db(_Result(scalar=existing))
    result, queued = await service.create_report_generation(payload, member, db)
    assert result.id == existing.id and queued is None
    assert db.added == []


@pytest.mark.parametrize("field_name", ["template_snapshot", "content"])
def test_report_generation_rejects_oversized_json_fields(field_name):
    oversized = (
        {"fields": [{"id": "body"}], "value": "가" * REPORT_GENERATION_JSON_MAX_BYTES}
        if field_name == "template_snapshot"
        else {"value": "가" * REPORT_GENERATION_JSON_MAX_BYTES}
    )
    payload = _daily_payload(**{field_name: oversized})

    with pytest.raises(ValidationError, match=f"{field_name}_too_large"):
        ReportGenerationCreate.model_validate(payload)
    db = _Db()
    with _client(db, _member()) as client:
        response = client.post("/api/report-generations", headers={"Origin": ORIGIN}, json=payload)
    assert response.status_code == 422
    assert f"{field_name}_too_large" in response.text
    assert all("input" not in error for error in response.json()["detail"])
    assert not db.statements and not db.added and db.commit_count == 0


def test_report_generation_rejects_oversized_body_before_queue():
    body = "private submitted body " + "가" * REPORT_BODY_MAX_LENGTH
    payload = _daily_payload(content={"values": {"body": body}})
    db = _Db()
    with _client(db, _member()) as client:
        response = client.post("/api/report-generations", headers={"Origin": ORIGIN}, json=payload)
    assert response.status_code == 422
    assert "report_body_too_large" in response.text
    assert "private submitted body" not in response.text
    assert all("input" not in error for error in response.json()["detail"])
    assert not db.statements and not db.added and db.commit_count == 0


def test_report_generation_rejects_oversized_aggregate_attachments():
    attachments = [
        {
            "id": str(uuid4()),
            "kind": "pdf",
            "name": f"memo-{index}.pdf",
            "byte_size": 1,
            "extract": "가" * 50_000,
        }
        for index in range(2)
    ]

    with pytest.raises(ValidationError, match="attachments_too_large"):
        ReportGenerationCreate.model_validate(_daily_payload(attachments=attachments))


def test_meeting_generation_rejects_oversized_effective_transcript():
    with pytest.raises(ValidationError, match="meeting_transcript_too_large"):
        ReportGenerationCreate(
            idempotency_key=uuid4(),
            report_kind="meeting",
            report_date=date(2026, 8, 17),
            source_activity_id=uuid4(),
            template_snapshot=TEMPLATE,
            content={},
            transcript="수" * 1_000,
            attachments=[
                {
                    "id": uuid4(),
                    "kind": "audio",
                    "name": "memo.m4a",
                    "byte_size": 123,
                    "extract": "음" * 49_100,
                }
            ],
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        (
            "template_snapshot",
            {"fields": [{"id": "summary"}]},
            "report_template_body_only",
        ),
        ("content", {"values": {"summary": "구형 요약"}}, "report_values_body_only"),
        ("content", {"title": "가" * 255}, "report_title_invalid"),
    ],
)
def test_new_report_generation_rejects_non_body_contract(field_name, value, error):
    with pytest.raises(ValidationError, match=error):
        ReportGenerationCreate.model_validate(_daily_payload(**{field_name: value}))


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


def test_daily_generation_rejects_unavailable_selected_calendar_activity(llm_ready):
    member = _member()
    activity_id = uuid4()
    db = _Db(
        _Result(scalar=None),
        _Result(scalars=[]),
    )
    payload = _daily_payload(
        content={
            "values": {},
            "activities": [
                {
                    "refId": str(activity_id),
                    "source": "캘린더",
                    "included": True,
                }
            ],
        }
    )

    with _client(db, member) as client:
        response = client.post("/api/report-generations", headers={"Origin": ORIGIN}, json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "activity_not_found"
    assert db.added == []


@pytest.mark.anyio
async def test_period_generation_restores_validated_attachments_and_current_body(monkeypatch):
    member = _member()
    attachment_id = uuid4()
    attachment = {
        "id": str(attachment_id),
        "kind": "pdf",
        "name": "proposal.pdf",
        "byte_size": 123,
        "extract": "서버가 추출한 계약 조건",
    }
    payload = ReportGenerationCreate.model_validate(
        _daily_payload(
            attachments=[attachment],
            content={
                "values": {},
                "activities": [],
                "attachments": [{"extract": "클라이언트 content 위조 값"}],
            },
        )
    )

    async def freeze_reports(_db, owner, report):
        assert owner is member and report.report_kind == "daily"
        assert "attachments" not in report.content
        return {"reports": [], "meetings": []}, []

    monkeypatch.setattr(service.report_sources, "freeze_report_sources", freeze_reports)

    agent_code, snapshot, refs = await service._report_generation_input(payload, member, _Db())

    assert agent_code == "report_writing"
    assert snapshot["attachments"] == [attachment]
    assert snapshot["content"] == payload.content
    assert "클라이언트 content 위조 값" not in str(snapshot)
    assert "attachment_files" not in refs


@pytest.mark.anyio
async def test_meeting_generation_combines_manual_and_audio_only_for_agent_input(monkeypatch):
    member = _member()
    activity_id = uuid4()
    attachment = {
        "id": str(uuid4()),
        "kind": "audio",
        "name": "memo.m4a",
        "byte_size": 123,
        "extract": "음성에서 추출한 원문",
    }
    payload = ReportGenerationCreate(
        idempotency_key=uuid4(),
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        source_activity_id=activity_id,
        template_snapshot=TEMPLATE,
        content={},
        transcript="사용자가 직접 입력한 원문",
        attachments=[
            attachment,
            {
                **attachment,
                "id": str(uuid4()),
                "kind": "image",
                "purpose": "meeting_source",
                "extract": "교정한 현장 기록",
            },
            {**attachment, "id": str(uuid4()), "purpose": "reference", "extract": "배경 음성"},
        ],
    )

    async def snapshot(_db, owner, source_activity_id, deal_ids, transcript, attachments):
        assert (owner, source_activity_id, deal_ids) == (member, activity_id, [])
        return {"source": {"transcript": transcript}, "attachments": attachments}

    monkeypatch.setattr(service.meeting_processing, "input_snapshot", snapshot)

    agent_code, input_snapshot, _refs = await service._report_generation_input(
        payload, member, _Db()
    )

    assert agent_code == "meeting_processing"
    assert input_snapshot["source"]["transcript"] == (
        "사용자가 직접 입력한 원문\n\n음성에서 추출한 원문\n\n교정한 현장 기록"
    )
    assert payload.model_dump(mode="json")["transcript"] == "사용자가 직접 입력한 원문"


def test_generation_input_restores_only_requesters_ui_values():
    team_id = uuid4()
    owner = _member(team_id=team_id)
    run = _run(owner, status_code="running")
    deal_id = uuid4()
    activity_id = uuid4()
    attachment_id = uuid4()
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
        "attachments": [
            {
                "id": str(attachment_id),
                "kind": "pdf",
                "name": "memo.pdf",
                "byte_size": 123,
                "extract": "서버가 추출한 메모",
            }
        ],
        "template_snapshot": TEMPLATE,
        "content": {
            "title": "방문 미팅",
            "attachments": [
                {
                    "id": "local-preview-id",
                    "fileId": str(attachment_id),
                    "kind": "pdf",
                    "name": "memo.pdf",
                    "size": "1KB",
                    "state": "done",
                }
            ],
        },
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

    with _client(_Db(_Result(scalar=run), _Result(scalars=[])), owner) as client:
        restored = client.get(f"/api/agent-runs/{run.id}")

    assert restored.status_code == 200
    generation_input = restored.json()["generation_input"]
    assert generation_input["transcript"] == "고객이 예산을 승인했습니다."
    assert generation_input["attachments"] == [
        {
            "id": str(attachment_id),
            "kind": "pdf",
            "name": "memo.pdf",
            "byte_size": 123,
            "extract": "서버가 추출한 메모",
        }
    ]
    assert "attachments" not in generation_input["content"]
    assert "crm_context" not in generation_input
    assert "context_lookups" not in restored.json()["output_snapshot"]

    manager = _member(role="manager", team_id=team_id)
    with _client(_Db(_Result(scalar=run), _Result(scalars=[])), manager) as client:
        hidden = client.get(f"/api/agent-runs/{run.id}")
    assert hidden.status_code == 200
    assert hidden.json()["generation_input"] is None
    assert hidden.json()["output_snapshot"] is None


def test_meeting_run_exposes_independent_child_statuses_and_outputs():
    member = _member()
    parent = _run(member, status_code="completed")
    parent.agent_code = "meeting_processing"
    report = _run(member, status_code="completed")
    report.agent_code = "meeting_report_writing"
    report.parent_run_id = parent.id
    report.scope_key = "meeting:source"
    report.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    report.request_snapshot = {"parent_run_id": str(parent.id), "kind": "report"}
    report.output_snapshot = {"deal_reports": [], "common_report": None}
    analysis = _run(member, status_code="running")
    analysis.agent_code = "meeting_analysis"
    analysis.parent_run_id = parent.id
    analysis.request_snapshot = {"parent_run_id": str(parent.id), "kind": "analysis"}

    with _client(
        _Db(_Result(scalar=parent), _Result(scalars=[report, analysis])), member
    ) as client:
        response = client.get(f"/api/agent-runs/{parent.id}")

    assert response.status_code == 200
    children = {item["agent_code"]: item for item in response.json()["child_runs"]}
    assert children["meeting_report_writing"]["status_code"] == "completed"
    assert children["meeting_report_writing"]["output_snapshot"] == report.output_snapshot
    assert children["meeting_report_writing"]["generation_input"] is None
    assert children["meeting_analysis"]["status_code"] == "running"
    assert children["meeting_analysis"]["generation_input"] is None


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
@pytest.mark.parametrize(
    "agent_code",
    [
        "contract_management_select_candidates",
        "contract_management_next_meeting",
        "contract_management_briefing",
        "schedule_management",
    ],
)
async def test_prepare_claimed_routes_generic_inputs_and_persists_snapshot(monkeypatch, agent_code):
    member = _member()
    target_id = uuid4()
    identifying = {
        "contract_management_select_candidates": {},
        "contract_management_next_meeting": {"customer_company_id": target_id},
        "contract_management_briefing": {"activity_id": target_id},
        "schedule_management": {
            "sales_deal_id": target_id,
            "preferred_starts_at": "2026-08-18T09:00:00+09:00",
            "preferred_ends_at": "2026-08-18T12:00:00+09:00",
            "duration_minutes": 60,
        },
    }[agent_code]
    payload = AgentRunCreate(
        agent_code=agent_code,
        idempotency_key=uuid4(),
        **identifying,
    )
    snapshots = {
        "contract_management_select_candidates": {"candidates": []},
        "contract_management_next_meeting": {
            "customer_company": {"id": str(target_id)},
            "risk_signals": [],
        },
        "contract_management_briefing": {
            "customer_company": {"id": "company-1"},
            "document_context": {"summaries": [], "sources": []},
        },
        "schedule_management": {"sales_deal_id": str(target_id), "activities": []},
    }
    builders = {
        "contract_management_select_candidates": "build_candidate_selection_snapshot",
        "contract_management_next_meeting": "build_next_meeting_snapshot",
        "contract_management_briefing": "build_briefing_snapshot",
        "schedule_management": "build_schedule_snapshot",
    }
    prompts = {
        "contract_management_select_candidates": (
            contract_management.SELECT_CANDIDATES_PROMPT_VERSION
        ),
        "contract_management_next_meeting": (
            contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION
        ),
        "contract_management_briefing": contract_management.GENERATE_BRIEFING_PROMPT_VERSION,
        "schedule_management": schedule_management.PROMPT_VERSION,
    }
    calls = []

    async def build(*args):
        calls.append(args)
        return snapshots[agent_code]

    monkeypatch.setattr(contract_schedule_snapshots, builders[agent_code], build)
    request_snapshot = payload.model_dump(mode="json")
    run = SimpleNamespace(
        id=uuid4(),
        team_id=member.team_id,
        agent_code=agent_code,
        requested_by_member_id=member.id,
        request_snapshot=request_snapshot,
        request_hash=service._request_hash(request_snapshot),
        input_snapshot={},
    )
    db = _Db(_Result(scalar=member), SimpleNamespace(rowcount=1))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    code, input_snapshot, requester_id = await service.prepare_claimed(run, "worker-1")

    assert (code, input_snapshot, requester_id) == (
        agent_code,
        snapshots[agent_code],
        member.id,
    )
    assert run.input_snapshot == snapshots[agent_code]
    assert len(calls) == 1 and calls[0][:2] == (db, member)
    if agent_code != "contract_management_select_candidates":
        assert calls[0][2] == target_id
    values = db.statements[1].compile().params
    assert values["prompt_version"] == prompts[agent_code]
    assert values["input_snapshot"] == snapshots[agent_code]
    assert values["current_stage_code"] == "running_agent"
    assert "agent_run.status_code" in str(db.statements[1])
    assert "agent_run.lease_owner" in str(db.statements[1])
    assert db.commit_count == 1


@pytest.mark.anyio
async def test_prepare_claimed_rejects_lost_lease_before_exposing_snapshot(monkeypatch):
    member = _member()
    payload = AgentRunCreate(
        agent_code="contract_management_select_candidates",
        idempotency_key=uuid4(),
    )
    request_snapshot = payload.model_dump(mode="json")
    run = SimpleNamespace(
        id=uuid4(),
        team_id=member.team_id,
        agent_code=payload.agent_code,
        requested_by_member_id=member.id,
        request_snapshot=request_snapshot,
        request_hash=service._request_hash(request_snapshot),
        input_snapshot={},
    )
    db = _Db(_Result(scalar=member), SimpleNamespace(rowcount=0))

    async def build(*_args):
        return "v1", {"candidates": []}, {}, None

    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))
    monkeypatch.setattr(service, "_build_run_input", build)

    with pytest.raises(RuntimeError, match="agent_run_lease_lost"):
        await service.prepare_claimed(run, "old-worker")

    assert run.input_snapshot == {}
    assert db.commit_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("agent_code", "agent_attribute", "output_values", "expected_evidence"),
    [
        (
            "contract_management_select_candidates",
            "select_next_meeting_candidates",
            {"candidates": []},
            {
                "prompt_version": contract_management.SELECT_CANDIDATES_PROMPT_VERSION,
                "candidate_count": 0,
            },
        ),
        (
            "contract_management_next_meeting",
            "propose_next_meeting",
            {"risks": []},
            {
                "prompt_version": contract_management.PROPOSE_NEXT_MEETING_PROMPT_VERSION,
                "risk_count": 0,
            },
        ),
        (
            "contract_management_briefing",
            "generate_briefing",
            {"risks": []},
            {
                "prompt_version": contract_management.GENERATE_BRIEFING_PROMPT_VERSION,
                "risk_count": 0,
                "document_count": 1,
                "chunk_count": 2,
            },
        ),
        (
            "schedule_management",
            "run",
            {"schedule_candidates": []},
            {
                "prompt_version": schedule_management.PROMPT_VERSION,
                "candidate_count": 0,
            },
        ),
    ],
)
async def test_generic_dispatch_completion_and_evidence(
    monkeypatch, agent_code, agent_attribute, output_values, expected_evidence
):
    member = _member()
    run = _run(member, status_code="running")
    run.agent_code = agent_code
    run.lease_owner = "worker-1"
    run.input_snapshot = {"document_context": {"summaries": [{}], "sources": [{}, {}]}}
    output_snapshot = {"agent_code": agent_code}
    output = SimpleNamespace(
        **output_values,
        model_dump=lambda **_kwargs: output_snapshot,
    )
    called = []

    async def execute(snapshot):
        called.append(snapshot)
        return output

    module = schedule_management if agent_code == "schedule_management" else contract_management
    monkeypatch.setattr(module, agent_attribute, execute)

    dispatched = await service.dispatch(agent_code, run.input_snapshot, member.id)
    db = _Db(SimpleNamespace(rowcount=1))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))
    await agent_worker._complete(run, run.lease_owner, dispatched)

    assert called == [run.input_snapshot]
    assert run.status_code == "completed"
    assert run.output_snapshot == output_snapshot
    assert run.evidence == expected_evidence
    assert run.lease_owner is None and db.commit_count == 1


@pytest.mark.anyio
async def test_report_review_metadata_is_evidence_not_output(monkeypatch):
    member = _member()
    run = _run(member, status_code="running")
    run.agent_code = "report_writing"
    run.lease_owner = "worker-1"
    output_snapshot = {"fields": [{"field_id": "body", "value": "검토할 초안"}]}
    output = SimpleNamespace(model_dump=lambda **_kwargs: output_snapshot)
    issue = harness.ReviewIssue(
        location="body",
        evidence="근거와 표현을 다시 확인해야 함",
        action="확인되지 않은 표현을 수정하세요.",
    )
    with review_delivery.capture() as review_evidence:
        review_delivery.record(harness.WorkflowResult(output, 2, True, 3, 2, 1, (issue,), True))

    db = _Db(SimpleNamespace(rowcount=1))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))
    await agent_worker._complete(run, run.lease_owner, output, review_evidence=review_evidence)

    assert run.output_snapshot == output_snapshot
    assert run.evidence["report_review"] == {
        "selected_version": 2,
        "initial_review_conducted": True,
        "repair_completed": None,
        "review_required": True,
        "review_incomplete": True,
        "review_notes_may_predate_draft": True,
        "issues": [issue.model_dump(mode="json")],
    }


@pytest.mark.anyio
async def test_worker_completes_meeting_output_without_an_apply_phase(monkeypatch):
    member = _member()
    run = _run(member)
    run.agent_code = "meeting_processing"
    run.input_snapshot = {"source": {"transcript": "원문"}}
    run.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    claim_db = _Db(_Result(scalar=run))
    complete_db = _Db(SimpleNamespace(rowcount=1), _Result(scalars=[]))
    sessions = iter((claim_db, complete_db))
    monkeypatch.setattr(
        service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(next(sessions)),
    )
    output = SimpleNamespace(
        errors={},
        analyses=[],
        evidence=SimpleNamespace(
            items=[],
            selected_deal_ids=[],
            transcript_sha256="a" * 64,
            model_dump=lambda **_kwargs: {"items": []},
        ),
        crm_context={},
        model_dump=lambda **_kwargs: {"reports": None, "analyses": [], "errors": {}},
    )

    async def dispatch(*_args):
        return output

    async def not_cancelled(_run_id):
        return False

    monkeypatch.setattr(agent_worker, "_is_cancelled", not_cancelled)
    monkeypatch.setattr(service, "dispatch", dispatch)
    await service.execute(run.id)

    assert run.status_code == "completed"
    assert run.current_stage_code == "completed"
    assert run.output_snapshot == {"reports": None, "analyses": [], "errors": {}}
    assert not hasattr(run, "apply_status")
    assert {child.agent_code for child in complete_db.added} == {
        "meeting_report_writing",
        "meeting_analysis",
    }
    assert all(child.parent_run_id == run.id for child in complete_db.added)


@pytest.mark.anyio
async def test_worker_claim_excludes_expired_or_redacted_report_payloads(monkeypatch):
    db = _Db(_Result(scalar=None))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    assert await agent_worker.claim("worker-1") is None

    statement = str(db.statements[0])
    params = repr(db.statements[0].compile().params)
    assert "agent_run.payload_expires_at" in statement
    assert "agent_run.payload_redacted_at IS NULL" in statement
    assert "agent_run.request_hash IS NOT NULL" in statement
    assert "schedule_management" in params
    assert "meeting_analysis" in params


@pytest.mark.anyio
async def test_meeting_children_are_not_duplicated_for_a_completed_parent(monkeypatch):
    parent = _run(_member(), status_code="completed")
    parent.agent_code = "meeting_processing"
    parent.input_snapshot = {"source": {}, "deals": []}
    parent.source_refs = {"source_activity_id": str(uuid4())}
    parent.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    db = _Db(
        _Result(
            scalars=[
                SimpleNamespace(agent_code="meeting_report_writing"),
                SimpleNamespace(agent_code="meeting_analysis"),
            ]
        )
    )
    monkeypatch.setattr(
        service,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )
    output = SimpleNamespace(
        evidence=SimpleNamespace(
            model_dump=lambda **_kwargs: {"items": []},
            transcript_sha256="a" * 64,
        ),
        crm_context={},
    )

    await agent_worker._enqueue_meeting_children(db, parent, output)

    assert db.added == []


@pytest.mark.anyio
@pytest.mark.parametrize("code", ["meeting_analysis", "meeting_report_writing"])
async def test_child_retry_preserves_frozen_source_and_attachment_roles(code):
    member = _member()
    parent = _run(member, status_code="completed")
    parent.report_id = uuid4() if code == "meeting_analysis" else None
    parent.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    child = _run(member, status_code="partial")
    child.agent_code = code
    child.parent_run_id = parent.id
    child.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    child.input_snapshot = {
        "source": {"transcript": "직접 원문\n\n교정한 OCR 원문"},
        "evidence": {"transcript_sha256": "a" * 64},
    }
    if code == "meeting_report_writing":
        child.input_snapshot["attachments"] = [
            {
                "id": str(uuid4()),
                "kind": "audio",
                "purpose": "reference",
                "name": "배경 음성",
                "byte_size": 1,
                "extract": "제품 참고자료",
            }
        ]
    child.request_hash = service._request_hash(child.input_snapshot)
    db = _Db(
        _Result(scalar=child),
        _Result(scalar=parent),
        _Result(scalar=child),
        _Result(scalar=None),
    )

    read, retry_id = await service.retry_meeting_child(child.id, member, db)

    retry = db.added[0]
    assert retry_id == retry.id == read.id
    assert retry.agent_code == child.agent_code
    assert retry.input_snapshot == child.input_snapshot
    assert retry.request_hash == child.request_hash
    assert retry.parent_run_id == parent.id


@pytest.mark.anyio
async def test_meeting_retry_reuses_active_sibling_and_rejects_expired_or_finalized_report():
    member = _member()
    parent = _run(member, status_code="completed")
    parent.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    child = _run(member, status_code="failed")
    child.agent_code = "meeting_analysis"
    child.parent_run_id = parent.id
    child.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    child.input_snapshot = {"evidence": {"transcript_sha256": "a" * 64}}
    active = _run(member, status_code="running")
    active.agent_code = child.agent_code
    active.parent_run_id = parent.id
    active_db = _Db(
        _Result(scalar=child),
        _Result(scalar=parent),
        _Result(scalar=child),
        _Result(scalar=active),
    )
    read, retry_id = await service.retry_meeting_child(child.id, member, active_db)
    assert retry_id == active.id and read.id == active.id and active_db.added == []

    expired_parent = _run(member, status_code="completed")
    expired_parent.payload_expires_at = NOW
    expired = _run(member, status_code="failed")
    expired.agent_code = "meeting_analysis"
    expired.parent_run_id = expired_parent.id
    with pytest.raises(HTTPException, match="meeting_child_retry_not_allowed"):
        await service.retry_meeting_child(
            expired.id,
            member,
            _Db(_Result(scalar=expired), _Result(scalar=expired_parent)),
        )

    finalized_parent = _run(member, status_code="completed")
    finalized_parent.report_id = uuid4()
    report_child = _run(member, status_code="failed")
    report_child.agent_code = "meeting_report_writing"
    report_child.parent_run_id = finalized_parent.id
    with pytest.raises(HTTPException, match="meeting_child_retry_not_allowed"):
        await service.retry_meeting_child(
            report_child.id,
            member,
            _Db(_Result(scalar=report_child), _Result(scalar=finalized_parent)),
        )


@pytest.mark.anyio
async def test_meeting_retry_reuses_latest_terminal_sibling_without_new_cost():
    member = _member()
    parent = _run(member, status_code="completed")
    parent.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    failed = _run(member, status_code="failed")
    failed.agent_code = "meeting_analysis"
    failed.parent_run_id = parent.id
    failed.payload_expires_at = datetime.now(UTC) + timedelta(hours=1)
    failed.input_snapshot = {"evidence": {"transcript_sha256": "a" * 64}}
    completed = _run(member, status_code="completed")
    completed.agent_code = failed.agent_code
    completed.parent_run_id = parent.id
    completed.output_snapshot = {"analyses": []}
    db = _Db(
        _Result(scalar=failed),
        _Result(scalar=parent),
        _Result(scalar=failed),
        _Result(scalar=completed),
    )

    read, retry_id = await service.retry_meeting_child(failed.id, member, db)

    assert retry_id == completed.id
    assert read.id == completed.id
    assert db.added == []


@pytest.mark.anyio
async def test_worker_persists_analysis_list_output_without_model_dump(monkeypatch):
    run = _run(_member(), status_code="running")
    run.agent_code = "meeting_analysis"
    run.lease_owner = "worker-1"
    result = meeting_analysis.DealFeatureResult(sales_deal_id=uuid4(), error=None)
    db = _Db(SimpleNamespace(rowcount=1))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    await agent_worker._complete(run, "worker-1", [result])

    assert run.status_code == "completed"
    assert run.output_snapshot == {"analyses": [result.model_dump(mode="json")]}


@pytest.mark.anyio
async def test_expired_generic_lease_is_reclaimed_with_skip_locked(monkeypatch):
    run = _run(_member(), status_code="running")
    run.agent_code = "schedule_management"
    run.request_hash = "a" * 64
    run.attempt_count = 1
    run.lease_owner = "dead-worker"
    run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db = _Db(_Result(scalar=run))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    claimed = await agent_worker.claim("replacement-worker")

    assert claimed is run
    assert run.attempt_count == 2
    assert run.lease_owner == "replacement-worker"
    assert run.lease_expires_at > datetime.now(UTC)
    assert db.statements[0]._for_update_arg.skip_locked is True
    assert db.commit_count == 1


@pytest.mark.anyio
async def test_direct_bridge_can_claim_legacy_system_run(monkeypatch):
    run = _run(_member())
    run.agent_code = "schedule_management"
    run.requested_by_member_id = None
    run.request_hash = None
    db = _Db(_Result(scalar=run))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    claimed = await agent_worker.claim("direct-bridge", run.id)

    assert claimed is run
    assert "agent_run.request_hash IS NOT NULL" not in str(db.statements[0])


@pytest.mark.anyio
async def test_worker_completion_rejects_lost_lease(monkeypatch):
    run = _run(_member(), status_code="running")
    run.agent_code = "schedule_management"
    run.lease_owner = "old-worker"
    db = _Db(SimpleNamespace(rowcount=0), SimpleNamespace(rowcount=0))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))
    output = SimpleNamespace(
        schedule_candidates=[],
        model_dump=lambda **_kwargs: {"schedule_candidates": []},
    )

    with pytest.raises(RuntimeError, match="agent_run_lease_lost"):
        await agent_worker._complete(run, "old-worker", output)
    assert run.status_code == "running"
    assert db.commit_count == 0


@pytest.mark.anyio
async def test_worker_does_not_dispatch_after_claim_is_cancelled(monkeypatch):
    run_id = uuid4()
    dispatched = False

    async def dispatch(*_args):
        nonlocal dispatched
        dispatched = True

    monkeypatch.setattr(agent_worker, "_is_cancelled", lambda _run_id: _already_cancelled())
    monkeypatch.setattr(agent_worker.agent_runs, "dispatch", dispatch)

    async def _already_cancelled():
        return True

    with pytest.raises(asyncio.CancelledError):
        await agent_worker._dispatch_until_cancelled(run_id, "report_writing", {}, None)
    assert dispatched is False


@pytest.mark.anyio
async def test_cancel_service_locks_requester_lineage_and_preserves_terminal_runs():
    member = _member()
    root = _run(member, status_code="completed")
    child = _run(member, status_code="running")
    child.parent_run_id = root.id
    terminal = _run(member, status_code="completed")
    terminal.parent_run_id = root.id
    db = _Db(
        _Result(scalar=root),
        _Result(scalar=root),
        _Result(scalars=[child, terminal]),
        _Result(scalars=[]),
    )

    result = await service.cancel(root.id, member, db)

    assert result.root_run_id == root.id
    assert result.cancelled_run_ids == [child.id]
    assert result.terminal_run_ids == [root.id, terminal.id]
    assert child.status_code == "cancelled"
    assert terminal.status_code == "completed"


@pytest.mark.anyio
async def test_cancelled_worker_failure_does_not_persist_analysis_side_effect(monkeypatch):
    member = _member()
    parent = _run(member, status_code="completed")
    parent.report_id = uuid4()
    run = _run(member, status_code="cancelled")
    run.agent_code = "meeting_analysis"
    run.parent_run_id = parent.id
    run.lease_owner = "worker-1"
    side_effect_called = False

    async def no_side_effect(*_args, **_kwargs):
        nonlocal side_effect_called
        side_effect_called = True

    monkeypatch.setattr(agent_worker, "_persist_late_meeting_analysis", no_side_effect)
    db = _Db(_Result(scalar=parent), SimpleNamespace(rowcount=0))
    monkeypatch.setattr(
        agent_worker.agent_runs,
        "get_sessionmaker",
        lambda: lambda: _SessionContext(db),
    )
    await agent_worker._fail(run, "worker-1", "llm_provider_error:503")
    assert db.commit_count == 1
    assert side_effect_called is False


@pytest.mark.anyio
async def test_worker_schema_check_is_read_only(monkeypatch):
    rows = [
        (table_name, column_name)
        for table_name, columns in agent_worker.REQUIRED_SCHEMA.items()
        for column_name in (columns or {"id"})
    ]
    db = _Db(SimpleNamespace(all=lambda: rows))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

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
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))

    with pytest.raises(RuntimeError, match="agent_worker_schema_incomplete:report_source"):
        await agent_worker.check_schema()


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
    async def not_cancelled(_run_id):
        return False

    monkeypatch.setattr(agent_worker, "_is_cancelled", not_cancelled)
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
    run.source_refs = {"report_source_contract": service.report_sources.SOURCE_CONTRACT}
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

    class FailedModel(ScriptedModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            response = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            if response.generations[0].message.tool_calls[0]["name"] == "task":
                return response
            raise _provider_failure(failure_kind)

    model = FailedModel(writer_role="sales-meeting-report")
    monkeypatch.setattr(report_writing_deep.harness, "configured_chat_model", lambda: model)

    async def prepare(*_args):
        return "report_writing", {}, member.id

    async def dispatch(*_args):
        return await report_writing_deep.run(sample())

    async def not_cancelled(_run_id):
        return False

    monkeypatch.setattr(agent_worker, "_is_cancelled", not_cancelled)
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
        assert len(model._seen) == attempt * 2  # Supervisor delegation, then failed child call.


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
        request_hash=service._request_hash(request_snapshot),
        input_snapshot={},
    )
    member = SimpleNamespace(id=member_id, team_id=team_id)
    db = _Db(_Result(scalar=member), SimpleNamespace(rowcount=1))

    async def _build(_payload, _member, _session):
        return ("v4", built, {}, None)

    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: _SessionContext(db))
    monkeypatch.setattr(service, "_build_run_input", _build)

    _code, input_snapshot, _requester = await service.prepare_claimed(run, "worker-1")

    assert input_snapshot == built
    # 호출자가 든 run 도 같은 입력을 봐야 한다.
    assert run.input_snapshot == built
    evidence = service.evidence(
        "contract_management_briefing",
        SimpleNamespace(risks=[]),
        run.input_snapshot,
    )
    assert evidence["document_count"] == 1
    assert evidence["chunk_count"] == 1
