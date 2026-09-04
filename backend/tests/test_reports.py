from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException, Response
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api import reports as reports_api
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.agent import AgentRun
from app.models.content import Report, ReportDeal, ReportSubmission
from app.models.crm import Activity
from app.models.workspace import Member
from app.schemas.reports import (
    REPORT_JSON_MAX_BYTES,
    REPORT_TITLE_MAX_LENGTH,
    ReportDealWrite,
    ReportFinalize,
    ReportPageParams,
)
from app.services import report_sources, report_submissions

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
START = datetime(2026, 8, 17, 1, tzinfo=UTC)
TEMPLATE = {"fields": [{"id": "body", "label": "본문"}]}
CONTENT = {"values": {"body": "합성 보고 내용"}}
_MISSING = object()


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None, scalar_values=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows
        self.scalar_values = [] if scalar_values is None else scalar_values

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result, flush_error: Exception | None = None):
        self.results = list(results)
        self.flush_error = flush_error
        self.statements = []
        self.added = []
        self.deleted = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        statement_text = str(statement).lower()
        if "max(" in statement_text and "report_submission.revision_no" in statement_text:
            revisions = [
                value.revision_no for value in self.added if isinstance(value, ReportSubmission)
            ]
            return _Result(scalar=max(revisions, default=0))
        if "from public.report_source" in statement_text:
            return _Result(scalar_values=[])
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def delete(self, value):
        self.deleted.append(value)

    async def flush(self):
        self.flush_count += 1
        if self.flush_error is not None:
            raise self.flush_error
        for value in self.added:
            if isinstance(value, (Report, ReportDeal)):
                value.created_at = value.created_at or NOW
                value.updated_at = value.updated_at or NOW

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _report(member: Member, *, kind: str = "daily", status_code: str = "draft") -> Report:
    return Report(
        id=uuid4(),
        team_id=member.team_id,
        author_member_id=member.id,
        recipient_member_id=None,
        template_snapshot=TEMPLATE,
        source_activity_id=None,
        sales_deal_id=None,
        customer_company_id=None,
        report_kind=kind,
        report_date=date(2026, 8, 17),
        period_start=None,
        period_end=None,
        status_code=status_code,
        content=CONTENT,
        title=None,
        body="합성 보고 내용",
        common_body=None,
        unassigned_body=None,
        structured_values={},
        transcript=None,
        source_snapshot=None,
        ai_evidence=None,
        version=1,
        generation_input_version=1,
        current_submission_id=None,
        note=None,
        reviewed_by_member_id=None,
        reviewed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _activity(member: Member) -> Activity:
    return Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        customer_contact_id=None,
        end_user_contact_id=None,
        activity_category_id=uuid4(),
        title="합성 미팅",
        starts_at=START,
        ends_at=None,
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


def _section(report: Report, sales_deal_id: UUID | None = None) -> ReportDeal:
    deal_id = sales_deal_id or uuid4()
    return ReportDeal(
        report_id=report.id,
        sales_deal_id=deal_id,
        deal_snapshot={"id": str(deal_id), "label": "D-1", "note": "합성 딜"},
        content={"title": "합성 딜", "values": {"body": "딜별 본문"}},
        position=0,
        deal_no_snapshot="D-1",
        deal_title_snapshot="합성 딜",
        title="합성 딜",
        body="딜별 본문",
        structured_values={},
        ai_evidence=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _meeting_generation_run(member: Member, deal_id: UUID, transcript: str) -> AgentRun:
    features = {
        "Authority": "High",
        "Competitors": "Unknown",
        "Purch_dept": "Unknown",
        "Budgt_alloc": "Yes",
        "Forml_tend": "Unknown",
        "RFP": "Unknown",
        "Posit_statm": "Yes",
        "Source": "Unknown",
        "Client": "Current",
        "Scope": "Clear",
        "Cross_sale": "Unknown",
        "Deal_type": "Solution",
        "Needs_def": "Yes",
    }
    return AgentRun(
        id=uuid4(),
        team_id=member.team_id,
        parent_run_id=None,
        requested_by_member_id=member.id,
        agent_code="meeting_processing",
        trigger_code="user",
        idempotency_key=uuid4(),
        report_id=None,
        status_code="completed",
        llm_model_name="test-model",
        prompt_version="meeting_processing.v10",
        request_snapshot={},
        request_hash="0" * 64,
        scope_key=f"meeting:{uuid4()}",
        source_refs={},
        input_snapshot={
            "source": {
                "transcript": transcript,
                "selected_deal_ids": [str(deal_id)],
            }
        },
        output_snapshot={
            "reports": None,
            "analyses": [
                {
                    "sales_deal_id": str(deal_id),
                    "features": features,
                    "assessment": {
                        "features": features,
                        "label": "high",
                        "high_probability": 0.91,
                        "model_version": "test.v1",
                    },
                    "error": None,
                }
            ],
            "evidence": {
                "schema_version": "meeting_content.v1",
                "transcript_sha256": "0" * 64,
                "selected_deal_ids": [str(deal_id)],
                "items": [
                    {
                        "segment": {
                            "segment_id": "S0001",
                            "start": 0,
                            "end": len(transcript),
                            "text": transcript,
                        },
                        "applicability": {
                            "scope": "deal",
                            "deal_ids": [str(deal_id)],
                        },
                    }
                ],
            },
            "errors": {},
            "context_lookups": [],
        },
        evidence={"prompt_version": "meeting_processing.v10"},
        error_message=None,
        error_code=None,
        current_stage_code="completed",
        attempt_count=1,
        payload_expires_at=NOW,
        payload_redacted_at=None,
        lease_owner=None,
        lease_expires_at=None,
        heartbeat_at=NOW,
        next_attempt_at=NOW,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )


def _row(report: Report, author: Member, recipient_display_name: str | None = None):
    return (report, author.display_name, recipient_display_name)


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_legacy_report_content_write_routes_are_not_registered():
    paths = app.openapi()["paths"]

    assert "post" not in paths["/api/reports"]
    assert "patch" not in paths["/api/reports/{report_id}"]
    assert "/api/reports/{report_id}/submit" not in paths
    assert "post" in paths["/api/reports/finalize"]
    assert "post" in paths["/api/reports/{report_id}/review"]
    assert "delete" in paths["/api/reports/{report_id}"]


@pytest.mark.parametrize(
    "invalid",
    [
        {"report_kind": "weekly"},
        {"report_kind": "monthly"},
        {
            "report_kind": "weekly",
            "period_start": "2026-08-17",
            "period_end": "2026-08-10",
        },
        {"report_kind": "meeting"},
        {"report_kind": "meeting", "source_activity_id": uuid4()},
        {"sales_deal_id": uuid4()},
        {"activity_ids": [UUID(int=1), UUID(int=1)]},
        {"status_code": "submitted"},
        {"author_member_id": uuid4()},
    ],
)
def test_finalize_request_rejects_unsafe_values(invalid):
    payload = {
        "idempotency_key": uuid4(),
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "template_snapshot": TEMPLATE,
        "content": CONTENT,
        "body": "합성 보고 내용",
        **invalid,
    }
    with pytest.raises(ValidationError):
        ReportFinalize(**payload)

    with pytest.raises(ValidationError):
        ReportPageParams(start_date="2026-08-17", end_date="2026-08-10")


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"template_snapshot": {"fields": [{"id": "summary"}]}}, "report_template_body_only"),
        ({"content": {"values": {"summary": "구형 요약"}}}, "report_values_body_only"),
        ({"structured_values": {"summary": "구형 요약"}}, "structured_values_not_supported"),
        ({"body": None}, "report_body_required"),
    ],
)
def test_period_finalize_rejects_non_body_contract(override, error):
    payload = {
        "idempotency_key": uuid4(),
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "template_snapshot": TEMPLATE,
        "content": CONTENT,
        "body": "합성 보고 내용",
        **override,
    }
    with pytest.raises(ValidationError, match=error):
        ReportFinalize(**payload)


@pytest.mark.parametrize(
    ("kind", "override", "error"),
    [
        ("meeting", {"body": "숨은 상위 본문"}, "report_body_not_supported"),
        ("meeting", {"activity_ids": [uuid4()]}, "activity_ids_not_supported"),
        ("daily", {"source_activity_id": uuid4()}, "source_activity_not_supported"),
        ("daily", {"common_body": "숨은 공통 본문"}, "meeting_shared_not_supported"),
        ("daily", {"unassigned_body": "숨은 미지정 본문"}, "meeting_shared_not_supported"),
    ],
)
def test_finalize_rejects_hidden_fields_for_the_other_report_kind(kind, override, error):
    if kind == "meeting":
        deal_id = uuid4()
        payload = {
            "idempotency_key": uuid4(),
            "report_kind": "meeting",
            "report_date": "2026-08-17",
            "source_activity_id": uuid4(),
            "deal_sections": [
                {
                    "sales_deal_id": deal_id,
                    "deal_snapshot": {"id": deal_id, "label": "D-1"},
                    "content": {"values": {"body": "본문"}},
                    "body": "본문",
                }
            ],
            "template_snapshot": TEMPLATE,
            "content": CONTENT,
            "body": None,
            "activity_ids": [],
        }
    else:
        payload = {
            "idempotency_key": uuid4(),
            "report_kind": "daily",
            "report_date": "2026-08-17",
            "source_activity_id": None,
            "template_snapshot": TEMPLATE,
            "content": CONTENT,
            "body": "본문",
            "common_body": None,
            "unassigned_body": None,
        }
    ReportFinalize(**payload)

    with pytest.raises(ValidationError, match=error):
        ReportFinalize(**{**payload, **override})


@pytest.mark.parametrize("field_name", ["template_snapshot", "content"])
def test_finalize_reuses_the_generation_json_byte_limit(field_name):
    oversized = {"value": "가" * REPORT_JSON_MAX_BYTES}
    if field_name == "template_snapshot":
        oversized["fields"] = [{"id": "body"}]
    payload = {
        "idempotency_key": uuid4(),
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "template_snapshot": TEMPLATE,
        "content": CONTENT,
        "body": "본문",
        field_name: oversized,
    }

    with pytest.raises(ValidationError, match=f"{field_name}_too_large"):
        ReportFinalize(**payload)


def test_deal_content_reuses_the_generation_json_byte_limit():
    deal_id = uuid4()
    with pytest.raises(ValidationError, match="content_too_large"):
        ReportDealWrite(
            sales_deal_id=deal_id,
            deal_snapshot={"id": deal_id, "label": "D-1"},
            content={"value": "가" * REPORT_JSON_MAX_BYTES},
            body="본문",
        )


@pytest.mark.parametrize("target", ["finalize", "deal"])
def test_content_title_cannot_bypass_the_canonical_title_limit(target):
    accepted = "가" * REPORT_TITLE_MAX_LENGTH
    rejected = accepted + "가"

    def build(title):
        if target == "finalize":
            return ReportFinalize(
                idempotency_key=uuid4(),
                report_kind="daily",
                report_date="2026-08-17",
                template_snapshot=TEMPLATE,
                content={"title": title, "values": {"body": "본문"}},
                body="본문",
            )
        deal_id = uuid4()
        return ReportDealWrite(
            sales_deal_id=deal_id,
            deal_snapshot={"id": deal_id, "label": "D-1"},
            content={"title": title},
            body="본문",
        )

    assert len(build(accepted).content["title"]) == REPORT_TITLE_MAX_LENGTH
    with pytest.raises(ValidationError, match="report_title_invalid"):
        build(rejected)


def test_finalize_accepts_a_valid_meeting():
    activity_id, deal_id = uuid4(), uuid4()
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_kind="meeting",
        report_date="2026-08-17",
        source_activity_id=activity_id,
        deal_sections=[
            {
                "sales_deal_id": deal_id,
                "deal_snapshot": {"id": deal_id, "label": "D-1"},
                "content": {"values": {"body": "딜별 본문"}},
                "body": "딜별 본문",
            }
        ],
        template_snapshot=TEMPLATE,
        content=CONTENT,
    )

    assert payload.sales_deal_id is None
    assert payload.deal_sections[0].sales_deal_id == deal_id
    content, normalized = reports_api._finalize_values(payload)
    assert normalized["body"] is None
    assert "values" not in content


def test_finalize_hash_preserves_omitted_vs_explicit_null():
    values = {
        "idempotency_key": uuid4(),
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "template_snapshot": TEMPLATE,
        "content": {"values": {"body": "legacy body"}},
        "body": "본문",
    }
    omitted = ReportFinalize(**values)
    cleared = ReportFinalize(**values, title=None)

    assert reports_api._finalize_request_hash(omitted) != reports_api._finalize_request_hash(
        cleared
    )
    assert reports_api._finalize_values(omitted)[1]["body"] == "본문"
    assert reports_api._finalize_values(cleared)[1]["title"] is None


def test_deal_snapshot_requires_matching_id_and_safe_fields():
    deal_id = uuid4()
    valid = ReportDealWrite(
        sales_deal_id=deal_id,
        deal_snapshot={"id": str(deal_id), "label": "  D-1  ", "note": "  합성 딜  "},
        content={},
        body="본문",
    )
    assert valid.deal_snapshot.model_dump(mode="json") == {
        "id": str(deal_id),
        "label": "D-1",
        "note": "합성 딜",
    }
    for snapshot in (
        {"id": str(uuid4()), "label": "D-1"},
        {"id": str(deal_id), "label": "   "},
        {"id": str(deal_id), "label": "D-1", "unknown": "unsafe"},
    ):
        with pytest.raises(ValidationError):
            ReportDealWrite(sales_deal_id=deal_id, deal_snapshot=snapshot, content={}, body="본문")


@pytest.mark.parametrize("expected_status", ["draft", "submitted", "changes_requested"])
def test_finalize_accepts_cas_for_existing_editable_reports(expected_status):
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_id=uuid4(),
        expected_version=1,
        expected_status_code=expected_status,
        report_kind="daily",
        report_date=date(2026, 8, 17),
        template_snapshot=TEMPLATE,
        content=CONTENT,
        body="합성 보고 내용",
    )

    assert payload.expected_status_code == expected_status


def test_deal_positions_validate_the_effective_default_positions():
    first, second = uuid4(), uuid4()
    sections = [
        {
            "sales_deal_id": str(first),
            "position": 1,
            "deal_snapshot": {"id": str(first), "label": "D-1"},
            "content": {},
            "body": "첫 본문",
        },
        {
            "sales_deal_id": str(second),
            "deal_snapshot": {"id": str(second), "label": "D-2"},
            "content": {},
            "body": "둘째 본문",
        },
    ]

    with pytest.raises(ValidationError, match="duplicate_deal_positions"):
        ReportFinalize(
            idempotency_key=uuid4(),
            report_kind="meeting",
            report_date="2026-08-17",
            source_activity_id=uuid4(),
            deal_sections=sections,
            template_snapshot=TEMPLATE,
            content=CONTENT,
        )


@pytest.mark.anyio
async def test_deal_section_replace_preserves_server_ai_fields_and_ml_evidence():
    member = _member()
    report = _report(member, kind="meeting")
    section = _section(report)
    section.content.update(
        ai_values={"body": "서버 AI 초안"},
        ai_evidence="S0001",
        ai_generated_at=NOW.isoformat(),
    )
    section.ai_evidence = {"deal_assessment": {"label": "watch"}}
    db = _Db(_Result(scalar_values=[section]))
    payload = ReportDealWrite(
        sales_deal_id=section.sales_deal_id,
        deal_snapshot={"id": str(section.sales_deal_id), "label": "D-1", "note": "수정"},
        content={
            "values": {"body": "사람이 수정한 본문"},
            "ai_values": {"body": "위조"},
            "ai_evidence": "위조",
            "ai_generated_at": "위조",
        },
        body="사람이 수정한 본문",
    )

    await reports_api._replace_report_deals(db, report.id, [payload])

    assert section.content == {
        "values": {"body": "사람이 수정한 본문"},
        "ai_values": {"body": "서버 AI 초안"},
        "ai_evidence": "S0001",
        "ai_generated_at": NOW.isoformat(),
    }
    assert section.ai_evidence == {"deal_assessment": {"label": "watch"}}
    with pytest.raises(ValidationError):
        ReportDealWrite(
            sales_deal_id=section.sales_deal_id,
            deal_snapshot={"id": str(section.sales_deal_id), "label": "D-1"},
            content={},
            body="본문",
            ai_evidence={"deal_assessment": {"label": "spoofed"}},
        )


def test_submitted_report_is_not_deletable():
    member = _member()
    submitted = _report(member, status_code="submitted")
    delete_db = _Db(_Result(scalar=submitted))
    with _client(delete_db, member) as client:
        removed = client.delete(
            f"/api/reports/{submitted.id}",
            headers={"Origin": ORIGIN},
        )
    assert removed.status_code == 409
    assert removed.json() == {"detail": "report_not_editable"}
    assert delete_db.deleted == []
    assert delete_db.commit_count == 0


def test_changes_requested_report_with_submission_history_is_not_deletable():
    member = _member()
    report = _report(member, status_code="changes_requested")
    report.current_submission_id = uuid4()
    db = _Db(_Result(scalar=report))

    with _client(db, member) as client:
        response = client.delete(
            f"/api/reports/{report.id}",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "report_has_submission_history"}
    assert db.deleted == []
    assert db.rollback_count == 1


def test_deal_write_rejects_non_body_values():
    deal_id = uuid4()
    base = {
        "sales_deal_id": deal_id,
        "deal_snapshot": {"id": deal_id, "label": "D-1"},
        "body": "딜 본문",
    }
    with pytest.raises(ValidationError, match="report_values_body_only"):
        ReportDealWrite(**base, content={"values": {"body": "딜 본문", "old": "value"}})
    with pytest.raises(ValidationError, match="structured_values_not_supported"):
        ReportDealWrite(**base, content={}, structured_values={"next": "value"})


def test_legacy_meeting_values_do_not_replace_normalized_body():
    member = _member()
    report = _report(member, kind="meeting")
    section = _section(report)
    section.body = None
    section.content = {"values": {"body": "구버전 본문"}}
    section.structured_values = {"attendees": "기존 참석자", "reaction": "기존 반응"}

    with pytest.raises(HTTPException) as caught:
        report_submissions.validate_submission_content(report, [section])
    assert caught.value.detail == "report_deal_body_required"


@pytest.mark.anyio
async def test_structured_pre_v2_meeting_without_body_is_not_materialized():
    member = _member()
    report = _report(member, kind="meeting", status_code="submitted")
    report.current_submission_id = None
    section = _section(report)
    section.body = None
    section.content = {"values": {"attendees": "기존 참석자", "decision": "기존 결정"}}
    section.structured_values = {"attendees": "기존 참석자", "decision": "기존 결정"}

    class LegacyDb(_Db):
        async def get(self, *_args):
            return member

    db = LegacyDb(_Result(scalar_values=[section]))

    with pytest.raises(HTTPException) as caught:
        await report_sources.materialize_legacy_submission(db, report)
    assert caught.value.detail == "report_deal_body_required"
    assert report.current_submission_id is None


def test_blank_meeting_section_still_cannot_be_finalized():
    member = _member()
    report = _report(member, kind="meeting")
    section = _section(report)
    section.body = None
    section.content = {"values": {"reaction": "  "}}
    section.structured_values = {"reaction": "  "}

    with pytest.raises(HTTPException) as caught:
        report_submissions.validate_submission_content(report, [section])

    assert caught.value.detail == "report_deal_body_required"


@pytest.mark.anyio
async def test_reordering_report_deals_clears_positions_before_swapping():
    member = _member()
    report = _report(member, kind="meeting")
    first = _section(report)
    second = _section(report)
    second.position = 1

    class ReorderDb(_Db):
        async def flush(self):
            self.positions_at_flush = (first.position, second.position)
            await super().flush()

    db = ReorderDb(_Result(scalar_values=[first, second]))
    payloads = [
        ReportDealWrite(
            sales_deal_id=second.sales_deal_id,
            position=0,
            deal_snapshot=second.deal_snapshot,
            content=second.content,
            body=second.body,
        ),
        ReportDealWrite(
            sales_deal_id=first.sales_deal_id,
            position=1,
            deal_snapshot=first.deal_snapshot,
            content=first.content,
            body=first.body,
        ),
    ]

    changed, deal_ids_changed = await reports_api._replace_report_deals(db, report.id, payloads)

    assert db.positions_at_flush == (None, None)
    assert (first.position, second.position) == (1, 0)
    assert changed is True and deal_ids_changed is False


@pytest.mark.anyio
async def test_resubmit_creates_an_immutable_second_revision():
    class SubmissionDb:
        def __init__(self):
            self.added = []
            self.provenance_at_flush = []

        async def execute(self, _statement):
            revisions = [item.revision_no for item in self.added]
            return _Result(scalar=max(revisions, default=0))

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            submission = self.added[-1]
            self.provenance_at_flush.append(
                (
                    submission.agent_run_id,
                    submission.idempotency_key,
                    submission.request_hash,
                )
            )

    member = _member()
    report = _report(member, kind="meeting")
    report.source_activity_id = uuid4()
    report.transcript = "스냅샷에 원문을 중복 저장하지 않는다."
    section = _section(report)
    db = SubmissionDb()

    agent_run_id = uuid4()
    idempotency_key = uuid4()
    request_hash = "1" * 64
    first = await report_submissions.create_submission(
        db,
        report,
        member,
        [section],
        agent_run_id=agent_run_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    first_snapshot = dict(first.snapshot)
    section.body = "수정된 두 번째 본문"
    section.content = {"title": "합성 딜", "values": {"body": section.body}}
    report.version = 3
    second = await report_submissions.create_submission(db, report, member, [section])

    assert (first.revision_no, second.revision_no) == (1, 2)
    assert first.report_version == 1 and second.report_version == 3
    assert first.snapshot == first_snapshot
    assert first.snapshot["deals"][0]["body"] == "딜별 본문"
    assert second.snapshot["deals"][0]["body"] == "수정된 두 번째 본문"
    assert first.snapshot_sha256 != second.snapshot_sha256
    assert db.provenance_at_flush[0] == (agent_run_id, idempotency_key, request_hash)
    assert "transcript" not in first.snapshot
    assert first.snapshot["transcript_sha256"] is not None


@pytest.mark.parametrize("field_id", ["transcript", "Attachments", "AI-Values", "Output-Snapshot"])
def test_submission_rejects_reserved_legacy_values(field_id):
    member = _member()
    report = _report(member)
    report.content = {"values": {field_id: {"raw": "민감 원문"}}}

    with pytest.raises(HTTPException) as caught:
        report_submissions.build_submission_snapshot(report, [])

    assert caught.value.status_code == 422
    assert caught.value.detail == "report_submission_reserved_field"


@pytest.mark.parametrize(
    "template_snapshot",
    [
        {"fields": [{"id": "body"}], "request_snapshot": {"transcript": "원문"}},
        {
            "fields": [
                {
                    "id": "body",
                    "config": {"Output-Snapshot": {"rawTranscript": "원문"}},
                }
            ]
        },
    ],
)
def test_submission_rejects_reserved_fields_anywhere_in_the_template(template_snapshot):
    member = _member()
    report = _report(member)
    report.template_snapshot = template_snapshot

    with pytest.raises(HTTPException) as caught:
        report_submissions.build_submission_snapshot(report, [])

    assert caught.value.status_code == 422
    assert caught.value.detail == "report_submission_reserved_field"


@pytest.mark.parametrize("target", ["report", "deal"])
def test_submission_rejects_reserved_normalized_values_at_any_depth(target):
    member = _member()
    report = _report(member, kind="meeting")
    section = _section(report)
    malicious = {"summary": {"safe": "확정 본문", "rawTranscript": "민감 원문"}}
    if target == "report":
        report.structured_values = malicious
    else:
        section.structured_values = malicious

    with pytest.raises(HTTPException) as caught:
        report_submissions.build_submission_snapshot(report, [section])

    assert caught.value.status_code == 422
    assert caught.value.detail == "report_submission_reserved_field"


def test_submission_does_not_restore_legacy_top_level_template_fields():
    member = _member()
    report = _report(member)
    report.template_snapshot = {"fields": [{"id": "summary", "label": "요약"}]}
    report.content = {"summary": "사람이 승인한 요약", "body": "구버전 본문"}
    report.body = "정규 본문"

    snapshot = report_submissions.build_submission_snapshot(report, [])

    assert snapshot["structured_values"] == {}
    assert snapshot["body"] == "정규 본문"


def test_submission_rejects_reserved_top_level_legacy_values():
    member = _member()
    report = _report(member, kind="meeting")
    section = _section(report)
    report.content = {"values": {"summary": "사람이 승인한 요약", "transcript": "구버전 원문"}}
    section.content = {
        "values": {"body": "사람이 승인한 본문", "ai_values": {"body": "구버전 초안"}}
    }

    with pytest.raises(HTTPException) as caught:
        report_submissions.build_submission_snapshot(report, [section])
    assert caught.value.detail == "report_submission_reserved_field"


def test_meeting_run_evidence_is_matched_by_server_deal_id():
    member = _member()
    deal_id = uuid4()
    run = _meeting_generation_run(member, deal_id, "예산이 승인되었습니다.")

    extracted = reports_api.agent_run_service.meeting_deal_evidence(run, [deal_id])

    assert extracted[deal_id]["deal_assessment"]["label"] == "high"
    assert extracted[deal_id]["deal_assessment"]["high_probability"] == 0.91
    assert extracted[deal_id]["features"]["Authority"] == "High"
    assert "evidence" not in extracted[deal_id]


def test_meeting_run_keeps_features_when_ml_prediction_failed():
    member = _member()
    deal_id = uuid4()
    run = _meeting_generation_run(member, deal_id, "예산을 검토했습니다.")
    [analysis] = run.output_snapshot["analyses"]
    analysis["assessment"] = None
    analysis["error"] = "deal_prediction_failed"

    extracted = reports_api.agent_run_service.meeting_deal_evidence(run, [deal_id])

    assert extracted[deal_id]["features"]["Budgt_alloc"] == "Yes"
    assert extracted[deal_id]["deal_assessment"] is None
    assert extracted[deal_id]["analysis_error"] == "deal_prediction_failed"


@pytest.mark.anyio
async def test_finalize_rejects_an_expired_generation_run():
    member = _member()
    activity_id = uuid4()
    deal_id = uuid4()
    transcript = "예산을 검토했습니다."
    run = _meeting_generation_run(member, deal_id, transcript)
    run.scope_key = f"meeting:{activity_id}"
    run.payload_expires_at = NOW
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        agent_run_id=run.id,
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        source_activity_id=activity_id,
        deal_sections=[
            {
                "sales_deal_id": deal_id,
                "deal_snapshot": {"id": deal_id, "label": "D-1"},
                "content": {"values": {"body": "최종 본문"}},
                "body": "최종 본문",
            }
        ],
        template_snapshot=TEMPLATE,
        content={},
        transcript=transcript,
    )

    with pytest.raises(HTTPException) as caught:
        await reports_api._finalize_run(_Db(_Result(scalar=run)), member, payload)

    assert caught.value.status_code == 409
    assert caught.value.detail == "report_generation_not_usable"


@pytest.mark.anyio
async def test_period_finalize_rejects_a_different_source_revision_before_submission(
    monkeypatch,
):
    member = _member()
    source_report_id = uuid4()
    generated_submission_id = uuid4()
    current_submission_id = uuid4()
    run = _meeting_generation_run(member, uuid4(), "생성 입력")
    run.agent_code = "report_writing"
    run.scope_key = "daily:2026-08-17"
    run.request_snapshot = {
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "period_start": None,
        "period_end": None,
        "template_snapshot": TEMPLATE,
        "content": {"values": {"body": "생성 당시 본문"}},
        "guidance": None,
    }
    run.source_refs = {
        "report_kind": "daily",
        "report_date": "2026-08-17",
        "period_start": None,
        "period_end": None,
        "report_sources": [
            {
                "position": 0,
                "source_activity_id": None,
                "source_report_submission_id": str(generated_submission_id),
            }
        ],
    }
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        agent_run_id=run.id,
        report_kind="daily",
        report_date=date(2026, 8, 17),
        template_snapshot=TEMPLATE,
        content={
            "values": {"body": "사람이 확정한 본문"},
            "activities": [
                {
                    "source": "업무보고서",
                    "included": True,
                    "refId": str(source_report_id),
                }
            ],
        },
        body="사람이 확정한 본문",
    )
    db = _Db()
    create_submission = AsyncMock()
    monkeypatch.setattr(reports_api, "_existing_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(
        reports_api, "_existing_finalize_after_rollback", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(reports_api, "_finalize_run", AsyncMock(return_value=run))
    monkeypatch.setattr(reports_api, "_own_activity_ids", AsyncMock(return_value=()))
    monkeypatch.setattr(
        reports_api.report_sources,
        "sync_report_sources_from_legacy_content",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        reports_api.report_sources,
        "current_source_ref_snapshot",
        AsyncMock(
            return_value=[
                {
                    "position": 0,
                    "source_activity_id": None,
                    "source_report_submission_id": str(current_submission_id),
                }
            ]
        ),
    )
    monkeypatch.setattr(reports_api.report_submissions, "create_submission", create_submission)

    with pytest.raises(HTTPException) as caught:
        await reports_api.finalize_report(
            payload,
            Response(),
            BackgroundTasks(),
            member,
            db,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "report_generation_source_changed"
    create_submission.assert_not_awaited()
    assert run.report_id is None
    assert run.input_snapshot and run.output_snapshot is not None
    assert db.commit_count == 0 and db.rollback_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize("changed", ["guidance", "attachments", "template", "report_date"])
async def test_period_finalize_rejects_changed_noneditable_generation_input(
    monkeypatch,
    changed,
):
    member = _member()
    report = _report(member)
    attachment = {
        "id": "attachment-1",
        "name": "memo.txt",
        "state": "done",
        "extract": "생성에 사용한 첨부",
    }
    run = _meeting_generation_run(member, uuid4(), "생성 입력")
    run.agent_code = "report_writing"
    run.request_snapshot = {
        "report_kind": "daily",
        "report_date": report.report_date.isoformat(),
        "period_start": None,
        "period_end": None,
        "template_snapshot": TEMPLATE,
        "content": {
            "values": {"body": "생성 당시 본문"},
            "attachments": [attachment],
        },
        "guidance": "생성 당시 직접 입력",
    }
    run.source_refs = {"report_sources": []}
    template = TEMPLATE
    content = {
        "values": {"body": "사람이 수정한 본문"},
        "attachments": [attachment],
    }
    transcript = "생성 당시 직접 입력"
    report_date = report.report_date
    if changed == "guidance":
        transcript = "생성 뒤 바꾼 직접 입력"
    elif changed == "attachments":
        content = {
            **content,
            "attachments": [{**attachment, "extract": "생성 뒤 바꾼 첨부"}],
        }
    elif changed == "template":
        template = {**TEMPLATE, "name": "생성 뒤 바꾼 양식"}
    else:
        report_date += timedelta(days=1)
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_kind="daily",
        report_date=report_date,
        template_snapshot=template,
        content=content,
        title="사람이 정한 제목",
        body="사람이 수정한 본문",
        transcript=transcript,
    )
    monkeypatch.setattr(
        reports_api.report_sources,
        "current_source_ref_snapshot",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(HTTPException) as caught:
        await reports_api._validate_generation_source_refs(AsyncMock(), report, payload, run)

    assert caught.value.status_code == 409
    assert caught.value.detail == "report_generation_source_changed"


@pytest.mark.anyio
async def test_period_finalize_allows_human_title_and_body_edits_after_generation(monkeypatch):
    member = _member()
    report = _report(member)
    run = _meeting_generation_run(member, uuid4(), "생성 입력")
    run.agent_code = "report_writing"
    run.request_snapshot = {
        "report_kind": "daily",
        "report_date": report.report_date.isoformat(),
        "period_start": None,
        "period_end": None,
        "template_snapshot": TEMPLATE,
        "content": {"title": "생성 전 제목", "values": {"body": "생성 전 본문"}},
        "guidance": None,
    }
    run.source_refs = {"report_sources": []}
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_kind="daily",
        report_date=report.report_date,
        template_snapshot=TEMPLATE,
        content={"title": "최종 제목", "values": {"body": "최종 본문"}},
        title="최종 제목",
        body="최종 본문",
    )
    monkeypatch.setattr(
        reports_api.report_sources,
        "current_source_ref_snapshot",
        AsyncMock(return_value=[]),
    )

    await reports_api._validate_generation_source_refs(AsyncMock(), report, payload, run)


@pytest.mark.anyio
async def test_finalize_atomically_persists_server_ml_and_redacts_run(monkeypatch):
    class FinalizeDb(_Db):
        async def execute(self, statement):
            if "from public.report_deal" in str(statement).lower():
                return _Result(
                    scalar_values=[item for item in self.added if isinstance(item, ReportDeal)]
                )
            return await super().execute(statement)

    member = _member()
    activity_id = uuid4()
    deal_id = uuid4()
    transcript = "예산이 승인되었습니다."
    run = _meeting_generation_run(member, deal_id, transcript)
    run.scope_key = f"meeting:{activity_id}"
    db = FinalizeDb()
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        agent_run_id=run.id,
        report_kind="meeting",
        report_date=date(2026, 8, 17),
        source_activity_id=activity_id,
        deal_sections=[
            {
                "sales_deal_id": deal_id,
                "deal_snapshot": {"id": deal_id, "label": "D-1"},
                "content": {"values": {"body": "사람이 확정한 본문"}},
                "body": "사람이 확정한 본문",
            }
        ],
        template_snapshot=TEMPLATE,
        content={
            "ai_values": {"body": "클라이언트 위조 초안"},
            "ai_evidence": "클라이언트 위조 근거",
            "ai_generated_at": NOW.isoformat(),
            "meeting_shared": {"common_report": {"body": "클라이언트 위조 공통"}},
        },
        transcript=transcript,
    )

    monkeypatch.setattr(reports_api, "_existing_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(reports_api, "_finalize_run", AsyncMock(return_value=run))
    monkeypatch.setattr(reports_api, "_own_activity_ids", AsyncMock(return_value=()))
    monkeypatch.setattr(reports_api, "_validate_meeting_deals", AsyncMock(return_value=uuid4()))

    async def detail(_db, _member_value, report_id):
        return SimpleNamespace(id=report_id)

    queued = []

    def queue(_background, selected_deal_id, trigger):
        assert db.commit_count == 1
        queued.append((selected_deal_id, trigger))

    monkeypatch.setattr(reports_api, "_detail", detail)
    monkeypatch.setattr(reports_api.contract_next_meeting_pipeline, "queue", queue)
    response = Response()

    result = await reports_api.finalize_report(
        payload,
        response,
        BackgroundTasks(),
        member,
        db,
    )

    report = next(item for item in db.added if isinstance(item, Report))
    section = next(item for item in db.added if isinstance(item, ReportDeal))
    submission = next(item for item in db.added if isinstance(item, ReportSubmission))
    assert result.id == report.id
    assert report.status_code == "submitted"
    assert not set(reports_api._SERVER_OWNED_CONTENT_KEYS) & report.content.keys()
    assert report.current_submission_id == submission.id
    assert submission.agent_run_id == run.id
    assert section.ai_evidence["deal_assessment"]["label"] == "high"
    assert "ai_evidence" not in submission.snapshot["deals"][0]
    assert run.report_id == report.id
    assert run.input_snapshot == {} and run.output_snapshot is None
    assert db.commit_count == 1 and db.rollback_count == 0
    assert queued[0][0] == deal_id


@pytest.mark.anyio
async def test_finalize_existing_report_checks_version_before_mutation(monkeypatch):
    member = _member()
    report = _report(member, status_code="changes_requested")
    report.version = 2
    db = _Db()
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_id=report.id,
        expected_version=1,
        expected_status_code="changes_requested",
        report_kind="daily",
        report_date=report.report_date,
        template_snapshot=TEMPLATE,
        content={"values": {"body": "수정본"}},
        body="수정본",
    )
    monkeypatch.setattr(reports_api, "_existing_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(
        reports_api, "_existing_finalize_after_rollback", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(reports_api, "_own_activity_ids", AsyncMock(return_value=()))
    monkeypatch.setattr(reports_api, "_locked_report", AsyncMock(return_value=report))

    with pytest.raises(HTTPException) as caught:
        await reports_api.finalize_report(
            payload,
            Response(),
            BackgroundTasks(),
            member,
            db,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "report_version_conflict"
    assert report.status_code == "changes_requested"
    assert db.commit_count == 0 and db.rollback_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize("editable_status", ["submitted", "changes_requested"])
async def test_resubmit_without_generation_keeps_existing_ai_provenance(
    monkeypatch, editable_status
):
    member = _member()
    report = _report(member, status_code=editable_status)
    previous_submission_id = uuid4()
    report.current_submission_id = previous_submission_id
    report.source_snapshot = {"agent_run_id": str(uuid4())}
    report.ai_evidence = {"prompt_version": "report_writing.v1"}
    original_source = dict(report.source_snapshot)
    original_evidence = dict(report.ai_evidence)
    db = _Db(_Result(scalar_values=[]))
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_id=report.id,
        expected_version=1,
        expected_status_code=editable_status,
        report_kind="daily",
        report_date=report.report_date,
        template_snapshot=TEMPLATE,
        content={"values": {"body": "사람이 수정한 확정본"}},
        body="사람이 수정한 확정본",
    )
    monkeypatch.setattr(reports_api, "_existing_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(reports_api, "_finalize_run", AsyncMock(return_value=None))
    monkeypatch.setattr(reports_api, "_own_activity_ids", AsyncMock(return_value=()))
    monkeypatch.setattr(reports_api, "_locked_report", AsyncMock(return_value=report))
    monkeypatch.setattr(reports_api, "_replace_report_activities", AsyncMock())
    monkeypatch.setattr(
        reports_api.report_sources, "sync_report_sources_from_legacy_content", AsyncMock()
    )
    monkeypatch.setattr(
        reports_api,
        "_detail",
        AsyncMock(return_value=SimpleNamespace(id=report.id)),
    )

    await reports_api.finalize_report(payload, Response(), BackgroundTasks(), member, db)

    assert report.source_snapshot == original_source
    assert report.ai_evidence == original_evidence
    assert report.status_code == "submitted"
    assert report.version == 2
    submission = next(item for item in db.added if isinstance(item, ReportSubmission))
    assert report.current_submission_id == submission.id
    assert report.current_submission_id != previous_submission_id


@pytest.mark.anyio
async def test_finalize_existing_report_cannot_change_its_logical_date(monkeypatch):
    member = _member()
    report = _report(member, status_code="draft")
    db = _Db()
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_id=report.id,
        expected_version=1,
        expected_status_code="draft",
        report_kind="daily",
        report_date=report.report_date + timedelta(days=1),
        template_snapshot=TEMPLATE,
        content={"values": {"body": "확정본"}},
        body="확정본",
    )
    monkeypatch.setattr(reports_api, "_existing_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(
        reports_api, "_existing_finalize_after_rollback", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(reports_api, "_own_activity_ids", AsyncMock(return_value=()))
    monkeypatch.setattr(reports_api, "_locked_report", AsyncMock(return_value=report))

    with pytest.raises(HTTPException) as caught:
        await reports_api.finalize_report(
            payload,
            Response(),
            BackgroundTasks(),
            member,
            db,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "report_identity_changed"
    assert report.report_date != payload.report_date
    assert db.commit_count == 0 and db.rollback_count == 1


@pytest.mark.anyio
async def test_finalize_idempotent_replay_returns_existing_submission(monkeypatch):
    member = _member()
    report = _report(member, status_code="submitted")
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_kind="daily",
        report_date=report.report_date,
        template_snapshot=TEMPLATE,
        content={"values": {"body": "확정본"}},
        body="확정본",
    )
    submission = ReportSubmission(
        id=uuid4(),
        report_id=report.id,
        revision_no=1,
        report_version=1,
        team_id=member.team_id,
        submitted_by_member_id=member.id,
        agent_run_id=None,
        idempotency_key=payload.idempotency_key,
        request_hash=reports_api._finalize_request_hash(payload),
        snapshot={},
        snapshot_sha256="0" * 64,
        review_status="pending",
        reviewed_by_member_id=None,
        reviewed_at=None,
        review_note=None,
        submitted_at=NOW,
    )
    db = _Db(_Result(scalar=submission))

    async def detail(_db, _member_value, report_id):
        return SimpleNamespace(id=report_id)

    monkeypatch.setattr(reports_api, "_detail", detail)
    response = Response()
    result = await reports_api.finalize_report(
        payload,
        response,
        BackgroundTasks(),
        member,
        db,
    )

    assert result.id == report.id
    assert response.headers["Location"] == f"/api/reports/{report.id}"
    assert db.added == []
    assert db.commit_count == 0 and db.rollback_count == 0


@pytest.mark.anyio
async def test_finalize_concurrent_replay_returns_winning_submission(monkeypatch):
    member = _member()
    member_id = member.id
    refreshed_member = _member(team_id=member.team_id)
    report = _report(member, status_code="submitted")
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_kind="daily",
        report_date=report.report_date,
        template_snapshot=TEMPLATE,
        content={"values": {"body": "확정본"}},
        body="확정본",
    )
    existing = SimpleNamespace(id=report.id)
    seen_members = []

    async def existing_finalize(_db, current_member, *_args):
        seen_members.append(current_member)
        return None if len(seen_members) == 1 else existing

    async def refreshed(_db, current_member_id):
        assert current_member_id == member_id
        return refreshed_member

    monkeypatch.setattr(reports_api, "_existing_finalize", existing_finalize)
    monkeypatch.setattr(reports_api, "active_member", refreshed)
    monkeypatch.setattr(
        reports_api,
        "_finalize_run",
        AsyncMock(side_effect=HTTPException(409, "report_generation_not_usable")),
    )
    db = _Db()
    response = Response()

    result = await reports_api.finalize_report(
        payload,
        response,
        BackgroundTasks(),
        member,
        db,
    )

    assert result is existing
    assert seen_members == [member, refreshed_member]
    assert response.headers["Location"] == f"/api/reports/{report.id}"
    assert db.rollback_count == 1


def test_member_scope_hides_other_authors_report():
    member = _member()
    hidden_db = _Db(_Result(rows=[]))
    report_id = uuid4()
    with _client(hidden_db, member) as client:
        hidden = client.get(f"/api/reports/{report_id}")
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "report_not_found"}

    sql = str(hidden_db.statements[0])
    assert "report.author_member_id" in sql


@pytest.mark.anyio
@pytest.mark.parametrize("role", ["member", "manager"])
async def test_report_activities_must_belong_to_the_author(role):
    member = _member(role=role)
    foreign = _activity(_member(team_id=member.team_id))
    db = _Db(_Result(rows=[(foreign.id, foreign.owner_member_id)]))

    with pytest.raises(HTTPException) as caught:
        await reports_api._own_activity_ids(db, member, [foreign.id])

    assert caught.value.status_code == 403
    assert caught.value.detail == "activity_not_owned"


@pytest.mark.anyio
async def test_unknown_report_activity_is_hidden():
    member = _member()
    with pytest.raises(HTTPException) as caught:
        await reports_api._own_activity_ids(_Db(_Result(rows=[])), member, [uuid4()])

    assert caught.value.status_code == 404
    assert caught.value.detail == "activity_not_found"


def test_meeting_source_ownership_cannot_be_bypassed_with_empty_activity_ids():
    manager = _member(role="manager")
    teammate = _activity(_member(team_id=manager.team_id))
    deal_id = uuid4()
    db = _Db(
        _Result(scalar=None),
        _Result(rows=[(teammate.id, teammate.owner_member_id)]),
    )

    with _client(db, manager) as client:
        response = client.post(
            "/api/reports/finalize",
            headers={"Origin": ORIGIN},
            json={
                "idempotency_key": str(uuid4()),
                "report_kind": "meeting",
                "report_date": "2026-08-17",
                "source_activity_id": str(teammate.id),
                "deal_sections": [
                    {
                        "sales_deal_id": str(deal_id),
                        "deal_snapshot": {"id": str(deal_id), "label": "D-1"},
                        "content": {"values": {"body": "본문"}},
                        "body": "본문",
                    }
                ],
                "activity_ids": [],
                "template_snapshot": TEMPLATE,
                "content": CONTENT,
            },
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "activity_not_owned"}
    assert db.added == []
    assert db.commit_count == 0


@pytest.mark.anyio
async def test_manager_cannot_write_a_teammate_report():
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    report = _report(teammate)

    with pytest.raises(HTTPException) as caught:
        await reports_api._locked_report(_Db(_Result(scalar=report)), manager, report.id)

    assert caught.value.status_code == 403
    assert caught.value.detail == "report_not_owned"


def test_manager_author_filter_is_limited_to_same_team():
    member = _member(role="member")
    denied_db = _Db()
    with _client(denied_db, member) as client:
        denied = client.get(f"/api/reports?author_member_id={uuid4()}")
    assert denied.status_code == 403
    assert denied.json() == {"detail": "scope_not_allowed"}

    manager = _member(role="manager")
    unknown_db = _Db(_Result(scalar_values=[]))
    with _client(unknown_db, manager) as client:
        unknown = client.get(f"/api/reports?author_member_id={uuid4()}")
    assert unknown.status_code == 403
    assert unknown.json() == {"detail": "scope_not_allowed"}


def test_source_activity_and_sales_deal_filters_reach_the_query():
    """이 일정으로 쓴 보고서가 있는지를 서버가 직접 답해야 한다.

    이 조건이 쿼리에 실리지 않으면 저장 화면이 목록 첫 페이지만 보고 없다고 판단해,
    이미 보고서가 있는 일정에 같은 보고서를 하나 더 만든다.
    """
    member = _member()
    activity_id = uuid4()
    sales_deal_id = uuid4()
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        response = client.get(
            "/api/reports",
            params={
                "report_kind": "meeting",
                "source_activity_id": str(activity_id),
                "sales_deal_id": str(sales_deal_id),
                "limit": 1,
            },
        )

    assert response.status_code == 200
    assert response.json()["total"] == 0
    # 개수 쿼리와 행 쿼리 모두 같은 조건으로 좁혀야 총계와 목록이 어긋나지 않는다.
    for statement in db.statements:
        sql = str(statement)
        # 일정은 여러 개를 받을 수 있어 IN 으로 나간다.
        assert "report.source_activity_id IN " in sql
        assert "report.sales_deal_id = " in sql
        assert "report_deal.sales_deal_id = " in sql


@pytest.mark.anyio
async def test_meeting_deal_must_belong_to_the_meeting_company(monkeypatch):
    member = _member()
    activity_id = uuid4()
    sales_deal_id = uuid4()
    company_id = uuid4()

    async def activity_row(_db, _member, _activity_id):
        return (None, None, None, company_id)

    async def deal_row(_db, _member, _sales_deal_id):
        return (SimpleNamespace(customer_company_id=company_id),)

    monkeypatch.setattr(reports_api, "_activity_row", activity_row)
    monkeypatch.setattr(reports_api, "_sales_deal_row", deal_row)
    await reports_api._validate_meeting_sales_deal_ids(_Db(), member, activity_id, [sales_deal_id])

    async def other_company_deal(_db, _member, _sales_deal_id):
        return (SimpleNamespace(customer_company_id=uuid4()),)

    monkeypatch.setattr(reports_api, "_sales_deal_row", other_company_deal)
    with pytest.raises(HTTPException) as caught:
        await reports_api._validate_meeting_sales_deal_ids(
            _Db(), member, activity_id, [sales_deal_id]
        )
    assert caught.value.status_code == 404
    assert caught.value.detail == "sales_deal_not_found"


def test_asyncpg_unique_constraint_name_is_read():
    cause = RuntimeError("duplicate")
    cause.constraint_name = reports_api._MEETING_UNIQUE_INDEX
    original = RuntimeError("adapter")
    original.__cause__ = cause
    error = IntegrityError("insert", {}, original)

    assert reports_api._integrity_constraint(error) == reports_api._MEETING_UNIQUE_INDEX


def test_approver_and_hospital_filters_reach_the_query():
    """보고 대상과 고객사는 컬럼이 아니라 content 안에 있다.

    예전에는 전건을 받아 화면에서 걸렀다. 한 쪽만 받는 지금 이 조건이 쿼리에 실리지
    않으면 첫 쪽에 없는 일치 항목이 통째로 빠진다.
    """
    member = _member(role="manager")
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        response = client.get(
            "/api/reports",
            params={"approver": "김팀장", "hospital": "한빛대학교병원"},
        )

    assert response.status_code == 200
    # 개수 쿼리와 행 쿼리 모두 같은 조건으로 좁혀야 총계와 목록이 어긋나지 않는다.
    for statement in db.statements:
        text = str(statement)
        assert "coalesce" in text.lower()
        assert "report.content -> " in text or "report.content ->> " in text


def test_search_also_looks_inside_the_report_body():
    """보고 본문은 content 에 있다. 여기를 빼면 검색이 메모 검색이 되어 버린다."""
    member = _member(role="manager")
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        response = client.get("/api/reports", params={"q": "한빛"})

    assert response.status_code == 200
    for statement in db.statements:
        sql = str(statement)
        assert "CAST(public.report.content AS TEXT)) LIKE" in sql
        assert "report_deal.title" in sql
        assert "report_deal.body" in sql
        assert "CAST(public.report_deal.content AS TEXT)" in sql


def test_filter_options_only_count_values_in_scope():
    """선택지는 목록에 실제로 있는 값만 내놓아야 고르고도 0 건이 되지 않는다."""
    member = _member(role="manager")
    db = _Db(
        _Result(scalar_values=["김팀장", "박이사"]),
        _Result(scalar_values=["한빛대학교병원"]),
    )

    with _client(db, member) as client:
        response = client.get("/api/report-filter-options")

    assert response.status_code == 200
    assert response.json() == {
        "approvers": ["김팀장", "박이사"],
        "hospitals": ["한빛대학교병원"],
    }
    # 목록과 같은 범위를 봐야 한다. 범위 밖 작성자의 값이 선택지에 서면 고르고도 0 건이다.
    for statement in db.statements:
        assert "report.team_id = " in str(statement)


def test_unknown_report_filter_is_rejected():
    """오타 난 조건이 조용히 무시되면 화면은 걸렀다고 믿고 전건을 보여 준다."""
    with pytest.raises(ValidationError):
        ReportPageParams(hospitals=["한빛대학교병원"])
