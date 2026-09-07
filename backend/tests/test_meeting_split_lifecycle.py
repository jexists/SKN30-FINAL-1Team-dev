from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.agent import AgentRun
from app.models.content import Report, ReportDeal
from app.services import agent_worker

NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)


class _Result:
    def __init__(self, *, scalar=None, rows=()):
        self.scalar = scalar
        self.rows = list(rows)
        self.rowcount = 1

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self.rows)


class _Db:
    def __init__(self, *results):
        self.results = list(results)
        self.statements = []
        self.commit_count = 0
        self.added = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.results.pop(0)

    async def commit(self):
        self.commit_count += 1

    def add(self, value):
        self.added.append(value)


class _Session:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return False


def _run(*, code, parent_id=None, report_id=None):
    return AgentRun(
        id=uuid4(),
        team_id=uuid4(),
        parent_run_id=parent_id,
        requested_by_member_id=uuid4(),
        agent_code=code,
        trigger_code="user",
        idempotency_key=uuid4(),
        report_id=report_id,
        status_code="running",
        llm_model_name="test-model",
        prompt_version="test.v1",
        request_snapshot={},
        request_hash="a" * 64,
        scope_key="meeting:test",
        source_refs={"parent_run_id": str(parent_id)} if parent_id else {},
        input_snapshot={},
        output_snapshot=None,
        evidence=None,
        error_message=None,
        error_code=None,
        current_stage_code="running",
        attempt_count=1,
        payload_expires_at=NOW + timedelta(hours=1),
        payload_redacted_at=None,
        lease_owner="worker-1",
        lease_expires_at=NOW + timedelta(minutes=1),
        heartbeat_at=NOW,
        next_attempt_at=NOW,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
    )


def _report(report_id, report_child_id, generation=1):
    return Report(
        id=report_id,
        team_id=uuid4(),
        author_member_id=uuid4(),
        recipient_member_id=None,
        template_snapshot={},
        source_activity_id=None,
        sales_deal_id=None,
        customer_company_id=None,
        report_kind="meeting",
        report_date=NOW.date(),
        period_start=None,
        period_end=None,
        status_code="submitted",
        content={"values": {"body": "사람이 확정한 본문"}},
        title=None,
        body="사람이 확정한 본문",
        common_body=None,
        unassigned_body=None,
        structured_values={},
        transcript="원문",
        source_snapshot={
            "agent_run_id": str(report_child_id),
            "generation_input_version": generation,
        },
        ai_evidence={"prompt_version": "meeting_processing.v14"},
        version=1,
        generation_input_version=generation,
        current_submission_id=None,
        note=None,
        review_note=None,
        reviewed_by_member_id=None,
        reviewed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _deal(report_id, deal_id):
    return ReportDeal(
        report_id=report_id,
        sales_deal_id=deal_id,
        deal_snapshot={"id": str(deal_id)},
        content={"values": {"body": "사람이 확정한 딜 본문"}},
        position=0,
        deal_no_snapshot="D-1",
        deal_title_snapshot="딜",
        title="딜",
        body="사람이 확정한 딜 본문",
        structured_values={},
        ai_evidence={"analysis_status": "pending"},
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.anyio
async def test_late_analysis_persists_partial_features_and_preserves_submission(monkeypatch):
    parent = _run(code="meeting_processing")
    report_child = _run(code="meeting_report_writing", parent_id=parent.id)
    report = _report(uuid4(), report_child.id)
    parent.report_id = report.id
    report_child.report_id = report.id
    report_child.source_refs = {"parent_run_id": str(parent.id)}
    deal_id = uuid4()
    section = _deal(report.id, deal_id)
    pending_section = _deal(report.id, uuid4())
    submission = SimpleNamespace(
        snapshot={"body": "사람이 확정한 본문", "deals": [{"body": "사람이 확정한 딜 본문"}]},
    )
    original_snapshot = dict(submission.snapshot)
    output = {
        "analyses": [
            {
                "sales_deal_id": str(deal_id),
                "features": {"Budgt_alloc": "Yes"},
                "assessment": None,
                "error": "deal_prediction_failed",
            }
        ]
    }
    db = _Db(
        _Result(scalar=report),
        _Result(scalar=report_child),
        _Result(scalar=report),
        _Result(rows=[section, pending_section]),
    )
    monkeypatch.setattr(agent_worker.agent_runs, "get_sessionmaker", lambda: lambda: _Session(db))

    await agent_worker._persist_late_meeting_analysis(
        db,
        _run(code="meeting_analysis", parent_id=parent.id),
        output,
        parent=parent,
    )

    assert section.ai_evidence["meeting_run_id"] == str(report_child.id)
    assert section.ai_evidence["analysis_run_id"]
    assert section.ai_evidence["analysis_status"] == "failed"
    assert section.ai_evidence["features"] == {"Budgt_alloc": "Yes"}
    assert section.ai_evidence["analysis_error"] == "deal_prediction_failed"
    assert pending_section.ai_evidence["analysis_status"] == "pending"
    assert pending_section.ai_evidence["analysis_run_id"] == section.ai_evidence["analysis_run_id"]
    assert submission.snapshot == original_snapshot


@pytest.mark.anyio
async def test_late_analysis_skips_when_report_child_is_from_another_generation():
    parent = _run(code="meeting_processing")
    current_child = _run(code="meeting_report_writing", parent_id=parent.id)
    report = _report(uuid4(), current_child.id)
    report.source_snapshot["generation_input_version"] = 2
    parent.report_id = report.id
    current_child.report_id = report.id
    current_child.source_refs = {"parent_run_id": str(parent.id)}
    section = _deal(report.id, uuid4())
    original = dict(section.ai_evidence)
    db = _Db(
        _Result(scalar=report),
        _Result(scalar=current_child),
        _Result(scalar=report),
    )

    await agent_worker._persist_late_meeting_analysis(
        db,
        _run(code="meeting_analysis", parent_id=parent.id),
        {"analyses": []},
        parent=parent,
    )

    assert db.statements[2]._execution_options["populate_existing"] is True
    assert section.ai_evidence == original


@pytest.mark.anyio
async def test_analysis_completion_locks_parent_before_child_update(monkeypatch):
    parent = _run(code="meeting_processing")
    run = _run(code="meeting_analysis", parent_id=parent.id)
    run.report_id = None
    item = SimpleNamespace(
        sales_deal_id=uuid4(),
        error=None,
        assessment=None,
        features=None,
        model_dump=lambda **_kwargs: {"sales_deal_id": str(uuid4()), "error": None},
    )
    db = _Db(_Result(scalar=parent), _Result())
    monkeypatch.setattr(agent_worker.agent_runs, "get_sessionmaker", lambda: lambda: _Session(db))

    await agent_worker._complete(run, "worker-1", [item])

    assert "FROM PUBLIC.AGENT_RUN" in str(db.statements[0]).upper()
    assert str(db.statements[1]).upper().startswith("UPDATE PUBLIC.AGENT_RUN")
    assert db.commit_count == 1


@pytest.mark.anyio
async def test_enqueue_children_keeps_audio_in_effective_source_and_routes_documents_to_report():
    parent = _run(code="meeting_processing")
    parent.input_snapshot = {
        "source": {"transcript": "사용자 원문\n\n오디오 전사"},
        "deals": [],
        "attachments": [
            {"id": "audio-1", "kind": "audio", "extract": "오디오 전사"},
            {"id": "pdf-1", "kind": "pdf", "extract": "계약 조건"},
            {"id": "image-1", "kind": "image", "extract": "명함 메모"},
        ],
    }
    output = SimpleNamespace(
        evidence=SimpleNamespace(
            transcript_sha256="a" * 64,
            model_dump=lambda **_kwargs: {"transcript_sha256": "a" * 64, "items": []},
        ),
        crm_context={"company": {"name": "고객사"}},
    )
    db = _Db(_Result(rows=[]))

    await agent_worker._enqueue_meeting_children(db, parent, output)

    children = {child.agent_code: child for child in db.added}
    assert children["meeting_report_writing"].input_snapshot["source"]["transcript"] == (
        "사용자 원문\n\n오디오 전사"
    )
    assert children["meeting_report_writing"].input_snapshot["attachments"] == [
        {"id": "pdf-1", "kind": "pdf", "extract": "계약 조건"},
        {"id": "image-1", "kind": "image", "extract": "명함 메모"},
    ]
    assert "attachments" not in children["meeting_analysis"].input_snapshot
    assert (
        children["meeting_report_writing"].request_hash != children["meeting_analysis"].request_hash
    )
