from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from test_reports import _Db, _member, _report, _Result

from app.api import reports as api
from app.models.content import Report, ReportAttachment, ReportSubmission
from app.schemas.agent_runs import ReportGenerationCreate
from app.schemas.reports import ReportAttachmentRead, ReportFinalize, effective_meeting_transcript
from app.services import agent_runs, agent_worker, storage
from app.services import report_attachments as service


class Db(_Db):
    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "unexpected query"
        return self.results.pop(0)


class Session:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return False


def original(member, **changes):
    values = {
        "id": uuid4(),
        "team_id": member.team_id,
        "uploaded_by_member_id": member.id,
        "report_id": None,
        "file_name": "합성 기록.pdf",
        "storage_key": f"{member.team_id}/{uuid4()}.pdf",
        "media_type": "application/pdf",
        "byte_size": 5,
        "extracted_text": "원래 추출문",
        "uploaded_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(hours=24),
    }
    return ReportAttachment(**(values | changes))


def attachment(row, **changes):
    return ReportAttachmentRead.model_validate(
        {
            "id": row.id,
            "name": row.file_name,
            "byte_size": row.byte_size,
            "kind": "pdf",
            "extract": "교정한 문장",
            "purpose": "meeting_source",
            "original_stored": True,
        }
        | changes
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "fault,expected",
    [
        ("foreign_owner", 404),
        ("foreign_team", 404),
        ("another_report", 409),
        ("expired", 409),
        ("unfinished", 409),
        ("missing_stored", 409),
        ("name", 422),
        ("kind", 422),
        ("byte_size", 422),
    ],
)
async def test_original_identity_and_metadata_are_server_validated(fault, expected):
    member = _member()
    row = original(member)
    item = attachment(row)
    if fault == "foreign_owner":
        row.uploaded_by_member_id = uuid4()
    elif fault == "foreign_team":
        row.team_id = uuid4()
    elif fault == "another_report":
        row.report_id, row.expires_at = uuid4(), None
    elif fault == "expired":
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif fault == "unfinished":
        row.extracted_text = None
    elif fault in {"name", "kind", "byte_size"}:
        item = item.model_copy(
            update={fault: {"name": "spoof.pdf", "kind": "audio", "byte_size": 99}[fault]}
        )
    db = Db(_Result(scalar_values=[] if fault == "missing_stored" else [row]))
    with pytest.raises(HTTPException) as caught:
        await service.validate_inputs(db, member, [item], report_id=uuid4())
    assert caught.value.status_code == expected
    statement = str(db.statements[0])
    assert "FOR UPDATE" in statement and "ORDER BY public.report_attachment.id" in statement


@pytest.mark.anyio
async def test_legacy_unknown_is_metadata_only_but_existing_foreign_id_is_rejected():
    member = _member()
    row = original(member, uploaded_by_member_id=uuid4())
    legacy = attachment(row, original_stored=None)
    assert "original_stored" not in legacy.model_dump(mode="json")
    assert await service.validate_inputs(Db(_Result(scalar_values=[])), member, [legacy]) == {}
    with pytest.raises(HTTPException) as caught:
        await service.validate_inputs(Db(_Result(scalar_values=[row])), member, [legacy])
    assert caught.value.status_code == 404


@pytest.mark.anyio
async def test_generation_extends_locked_pending_until_run_expiry_and_same_report_can_regenerate():
    member = _member()
    row = original(member)
    deadline = datetime.now(UTC) + timedelta(hours=25)
    await service.validate_inputs(
        Db(_Result(scalar_values=[row])), member, [attachment(row)], expires_at=deadline
    )
    assert row.expires_at == deadline
    report = _report(member, kind="meeting")
    row.report_id, row.expires_at = report.id, None
    generation = SimpleNamespace(
        **{
            field: getattr(report, field)
            for field in (
                "report_kind",
                "report_date",
                "source_activity_id",
                "period_start",
                "period_end",
            )
        }
    )
    result = await service.validate_inputs(
        Db(_Result(scalar_values=[row]), _Result(scalar=report)),
        member,
        [attachment(row)],
        generation=generation,
        expires_at=deadline,
    )
    assert result[row.id] is row and row.expires_at is None
    generation.report_date = report.report_date + timedelta(days=1)
    with pytest.raises(HTTPException, match="report_attachment_already_linked"):
        await service.validate_inputs(
            Db(_Result(scalar_values=[row]), _Result(scalar=report)),
            member,
            [attachment(row)],
            generation=generation,
        )


def test_revisions_share_original_but_keep_corrected_text_and_purpose_separate():
    member = _member()
    row, report = original(member), _report(member)
    first = service.bind_to_report(report, [attachment(row)], {row.id: row})
    second = service.bind_to_report(
        report, [attachment(row, extract="", purpose="reference")], {row.id: row}
    )
    assert first[0]["extract"] == "교정한 문장" and first[0]["purpose"] == "meeting_source"
    assert second[0]["extract"] == "" and second[0]["purpose"] == "reference"
    assert first[0]["id"] == second[0]["id"] == str(row.id)
    assert (
        row.extracted_text == "원래 추출문"
        and row.report_id == report.id
        and row.expires_at is None
    )


def test_empty_correction_keeps_original_without_becoming_meeting_evidence():
    item = attachment(original(_member()), extract="")
    assert effective_meeting_transcript(None, [item]) == ""
    assert effective_meeting_transcript("직접 원문", [item]) == "직접 원문"
    with pytest.raises(ValidationError, match="report_attachment_extract_empty"):
        attachment(original(_member()), extract="", original_stored=None)
    with pytest.raises(ValidationError, match="transcript_required"):
        ReportGenerationCreate(
            idempotency_key=uuid4(),
            report_kind="meeting",
            report_date="2026-09-07",
            source_activity_id=uuid4(),
            template_snapshot={"fields": [{"id": "body", "label": "본문"}]},
            content={},
            attachments=[item],
        )


@pytest.mark.anyio
@pytest.mark.parametrize("remove_result", [True, False, "error"])
async def test_cleanup_locks_only_expired_unbound_rows_and_keeps_failed_deletes(
    monkeypatch, remove_result
):
    row = original(_member(), expires_at=datetime.now(UTC) - timedelta(seconds=1))
    db = Db(_Result(scalar_values=[row]))
    monkeypatch.setattr(service, "get_sessionmaker", lambda: lambda: Session(db))
    remove = AsyncMock(
        return_value=remove_result,
        side_effect=storage.StorageError("unavailable") if remove_result == "error" else None,
    )
    monkeypatch.setattr(storage, "remove", remove)
    assert await service.cleanup_expired() == (1 if remove_result is True else 0)
    assert bool(db.deleted) is (remove_result is True)
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "report_id IS NULL" in sql and "expires_at <=" in sql and "FOR UPDATE SKIP LOCKED" in sql
    assert db.commit_count == 1


@pytest.mark.anyio
async def test_worker_existing_sweep_also_cleans_pending_originals(monkeypatch):
    cleanup = AsyncMock()
    monkeypatch.setattr(agent_worker, "_fail_exhausted_leases", AsyncMock())
    monkeypatch.setattr(agent_runs, "redact_expired_payloads", AsyncMock())
    monkeypatch.setattr(service, "cleanup_expired", cleanup)
    monkeypatch.setattr(agent_worker, "claim", AsyncMock(return_value=None))
    assert await agent_worker.run_once("synthetic") is False
    cleanup.assert_awaited_once()


@pytest.mark.anyio
async def test_download_reuses_report_scope_and_selected_immutable_revision(monkeypatch):
    member = _member(role="manager")
    author = _member(team_id=member.team_id)
    report = _report(author)
    row = original(author, report_id=report.id, expires_at=None)
    old_submission = ReportSubmission(
        id=uuid4(),
        report_id=report.id,
        team_id=member.team_id,
        attachments_snapshot=[attachment(row).model_dump(mode="json")],
    )
    report.current_submission_id = uuid4()
    db = Db(
        _Result(rows=[(report, "작성자", "팀장")]),
        _Result(scalar=old_submission),
        _Result(scalar=row),
    )
    download = AsyncMock(return_value=b"%PDF-")
    monkeypatch.setattr(storage, "download", download)
    response = await api.download_report_attachment(
        report.id, row.id, member, db, old_submission.id
    )
    assert response.body == b"%PDF-" and response.media_type == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert row.storage_key not in str(dict(response.headers))
    download.assert_awaited_once_with(storage_key=row.storage_key, max_bytes=row.byte_size)
    scope_sql = str(db.statements[0])
    assert "report.team_id =" in scope_sql and ".active IS true" in scope_sql
    file_sql = str(db.statements[2])
    assert "report_attachment.report_id =" in file_sql and "report_attachment.id =" in file_sql
    assert old_submission.id in db.statements[1].compile().params.values()


@pytest.mark.anyio
@pytest.mark.parametrize("boundary", ["report", "submission", "attachment", "original"])
async def test_download_denies_inaccessible_report_or_unlinked_id_before_storage(
    monkeypatch, boundary
):
    member = _member()
    report = _report(member)
    report.current_submission_id = uuid4()
    row = original(member, report_id=report.id, expires_at=None)
    submission = SimpleNamespace(attachments_snapshot=[attachment(row).model_dump(mode="json")])
    results = [_Result(rows=[] if boundary == "report" else [(report, "작성자", None)])]
    if boundary != "report":
        results.append(_Result(scalar=None if boundary == "submission" else submission))
    if boundary == "original":
        results.append(_Result(scalar=None))
    download = AsyncMock()
    monkeypatch.setattr(storage, "download", download)
    db = Db(*results)
    with pytest.raises(HTTPException) as caught:
        await api.download_report_attachment(
            report.id, uuid4() if boundary == "attachment" else row.id, member, db
        )
    assert caught.value.status_code == 404
    download.assert_not_awaited()
    if boundary != "report":
        scope_sql = str(db.statements[0])
        assert "report.author_member_id =" in scope_sql


@pytest.mark.anyio
async def test_only_official_submission_attachments_are_returned():
    member = _member()
    report = _report(member)
    report.content = {"attachments": [attachment(original(member)).model_dump(mode="json")]}
    assert (await service.for_reports(Db(), [report]))[report.id] == []
    report.current_submission_id = uuid4()
    snapshot = [attachment(original(member), extract="").model_dump(mode="json")]
    submission = SimpleNamespace(id=report.current_submission_id, attachments_snapshot=snapshot)
    assert (await service.for_reports(Db(_Result(scalar_values=[submission])), [report]))[
        report.id
    ][0].extract == ""


@pytest.mark.anyio
@pytest.mark.parametrize("direct", [None, "직접 미팅 원문"])
@pytest.mark.parametrize("kind", ["meeting", "daily", "weekly", "monthly"])
async def test_finalize_binds_original_and_saves_replayable_input(monkeypatch, direct, kind):
    member = _member()
    row = original(member)

    class FinalizeDb(_Db):
        async def execute(self, statement):
            if "from public.report_attachment" in str(statement).lower():
                self.statements.append(statement)
                return _Result(scalar_values=[row])
            if "from public.report_deal" in str(statement).lower():
                return _Result(scalar_values=[])
            return await super().execute(statement)

    db = FinalizeDb()
    monkeypatch.setattr(api, "_existing_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(api, "_own_activity_ids", AsyncMock(return_value=()))
    monkeypatch.setattr(api, "_validate_meeting_deals", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(api.report_sources, "sync_report_sources_from_legacy_content", AsyncMock())
    monkeypatch.setattr(api, "_detail", AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    item = attachment(row, purpose="meeting_source" if kind == "meeting" else "reference")
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_kind=kind,
        report_date="2026-09-07",
        period_start="2026-09-01" if kind in {"weekly", "monthly"} else None,
        period_end="2026-09-07" if kind in {"weekly", "monthly"} else None,
        source_activity_id=uuid4() if kind == "meeting" else None,
        template_snapshot={"fields": [{"id": "body", "label": "본문"}]},
        content={},
        common_body="최종 미팅 보고서" if kind == "meeting" else None,
        body="최종 기간 보고서" if kind != "meeting" else None,
        transcript=direct,
        attachments=[item],
    )
    await api.finalize_report(payload, Response(), BackgroundTasks(), member, db)
    report = next(item for item in db.added if isinstance(item, Report))
    submission = next(item for item in db.added if isinstance(item, ReportSubmission))
    assert row.report_id == report.id and row.expires_at is None
    assert row.extracted_text == "원래 추출문"
    assert submission.attachments_snapshot[0]["extract"] == "교정한 문장"
    assert submission.attachments_snapshot[0]["original_stored"] is True
    assert "attachments" not in submission.snapshot
    assert db.commit_count == 1 and db.rollback_count == 0
    if kind == "meeting":
        read = api._report_read(report, "작성자", None, [], [], [item])
        assert read.direct_transcript == (direct or "")
        assert (
            effective_meeting_transcript(read.direct_transcript, read.attachments)
            == report.transcript
        )
    else:
        assert report.transcript == direct


@pytest.mark.anyio
async def test_finalize_failure_rolls_back_binding_without_deleting_storage(monkeypatch):
    member = _member()
    row = original(member)
    original_expiry = row.expires_at

    class RollbackDb(_Db):
        async def execute(self, statement):
            if "from public.report_attachment" in str(statement).lower():
                return _Result(scalar_values=[row])
            if "from public.report_deal" in str(statement).lower():
                return _Result(scalar_values=[])
            return await super().execute(statement)

        async def commit(self):
            assert row.report_id is not None
            raise RuntimeError("synthetic commit failure")

        async def rollback(self):
            await super().rollback()
            # The fake transaction restores the original as PostgreSQL rollback would.
            row.report_id, row.expires_at = None, original_expiry

    db = RollbackDb()
    monkeypatch.setattr(api, "_existing_finalize", AsyncMock(return_value=None))
    monkeypatch.setattr(api, "_own_activity_ids", AsyncMock(return_value=()))
    monkeypatch.setattr(api, "_validate_meeting_deals", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(api, "_detail", AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    remove = AsyncMock()
    monkeypatch.setattr(storage, "remove", remove)
    payload = ReportFinalize(
        idempotency_key=uuid4(),
        report_kind="meeting",
        report_date="2026-09-07",
        source_activity_id=uuid4(),
        template_snapshot={"fields": [{"id": "body", "label": "본문"}]},
        content={},
        common_body="최종 보고서",
        attachments=[attachment(row)],
    )
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        await api.finalize_report(payload, Response(), BackgroundTasks(), member, db)
    assert db.rollback_count == 1 and row.report_id is None and row.expires_at == original_expiry
    assert await service.validate_inputs(
        Db(_Result(scalar_values=[row])), member, payload.attachments
    ) == {row.id: row}
    remove.assert_not_awaited()
