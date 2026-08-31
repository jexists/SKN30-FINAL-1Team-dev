from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.agents.document_summary import DocumentSummaryOutput
from app.core.config import settings
from app.models.content import Document
from app.models.content import File as FileRow
from app.services import document_processing, storage
from app.services.document_extraction import ExtractedDocument


class _Result:
    def __init__(self, value):
        self.value = value

    def one_or_none(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, results):
        self.results = iter(results)
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return next(self.results)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True


@pytest.mark.anyio
async def test_execute_auto_saves_summary_and_rag_chunks(monkeypatch):
    team_id = uuid4()
    document = Document(
        id=uuid4(),
        team_id=team_id,
        created_by_member_id=uuid4(),
        document_no="SL-DC-2026-0001",
        category_code="contract",
        title="합성 계약서",
        description=None,
        customer_company_id=None,
        customer_contact_id=None,
        sales_deal_id=None,
        purchase_order_id=None,
        tags=[],
        created_at=datetime.now(UTC),
    )
    row = FileRow(
        id=uuid4(),
        report_id=None,
        document_id=document.id,
        version_no=1,
        file_name="contract.txt",
        storage_key="team/contract.txt",
        media_type="text/plain",
        byte_size=32,
        processing_status="processing",
        extracted_text=None,
        uploaded_by_member_id=document.created_by_member_id,
        note=None,
    )
    first = _Session([_Result((row, team_id))])
    second = _Session([_Result(row), _Result(None)])
    sessions = iter([first, second])

    def _sessionmaker():
        return lambda: next(sessions)

    async def _download(*, storage_key):
        assert storage_key == row.storage_key
        return b"\xea\xb3\x84\xec\x95\xbd\xea\xb8\xb0\xea\xb0\x84: 1\xeb\x85\x84"

    def _extract(*, file_name, media_type, content):
        assert (file_name, media_type) == ("contract.txt", "text/plain")
        assert content
        return ExtractedDocument(
            plain_text="계약기간: 1년",
            markdown="## 계약 조건\n\n계약기간: 1년",
            payload={
                "source_type": "text",
                "pages": [{"page_number": 1, "markdown": "## 계약 조건\n\n계약기간: 1년"}],
            },
        )

    async def _summary(_snapshot):
        return DocumentSummaryOutput(
            summary="계약기간은 1년이다.",
            key_points=["계약기간: 1년"],
            source_refs=["계약서 1쪽"],
        )

    monkeypatch.setattr(document_processing, "get_sessionmaker", _sessionmaker)
    monkeypatch.setattr(type(settings), "embedding_configured", property(lambda self: False))
    monkeypatch.setattr(storage, "download", _download)
    monkeypatch.setattr(document_processing, "extract_document", _extract)
    monkeypatch.setattr(document_processing.document_summary, "run", _summary)

    await document_processing.execute(row.id)

    assert first.committed
    assert second.committed
    assert row.processing_status == "completed"
    assert row.extracted_text == "계약기간: 1년"
    assert "계약기간은 1년이다." in row.summary_markdown
    chunks = [item for item in second.added if item.__class__.__name__ == "DocumentChunk"]
    audits = [item for item in second.added if item.__class__.__name__ == "DocumentFileAudit"]
    assert len(chunks) == 1
    assert chunks[0].page_start == 1
    assert audits[0].action_code == "summary_completed"


@pytest.mark.anyio
async def test_execute_batch_continues_after_one_file_fails(monkeypatch):
    first_id, second_id = uuid4(), uuid4()
    executed = []
    marked_failed = []

    async def _execute(file_id):
        executed.append(file_id)
        if file_id == first_id:
            raise RuntimeError("synthetic_failure")

    async def _mark_failed(file_id, error):
        marked_failed.append((file_id, str(error)))

    monkeypatch.setattr(document_processing, "execute", _execute)
    monkeypatch.setattr(document_processing, "_mark_failed", _mark_failed)

    await document_processing.execute_batch([first_id, second_id])

    assert executed == [first_id, second_id]
    assert marked_failed == [(first_id, "synthetic_failure")]


@pytest.mark.anyio
async def test_execute_marks_file_failed_when_source_download_fails(monkeypatch):
    team_id = uuid4()
    row = FileRow(
        id=uuid4(),
        document_id=uuid4(),
        file_name="contract.pdf",
        storage_key="team/contract.pdf",
        media_type="application/pdf",
        byte_size=32,
        processing_status="processing",
        extracted_text=None,
        uploaded_by_member_id=uuid4(),
    )
    document_result = _Session([_Result((row, team_id))])
    failure_result = _Session([_Result(row)])
    sessions = iter([document_result, failure_result])

    monkeypatch.setattr(document_processing, "get_sessionmaker", lambda: lambda: next(sessions))

    async def _download(**_kwargs):
        raise storage.StorageError("storage_download_failed:503")

    removed: list[str] = []

    async def _remove(*, storage_key):
        removed.append(storage_key)

    monkeypatch.setattr(storage, "download", _download)
    monkeypatch.setattr(storage, "remove", _remove)

    await document_processing.execute(row.id)

    assert row.processing_status == "failed"
    assert row.processing_error == "storage_download_failed:503"
    assert removed == [document_processing.draft_storage_key(row.storage_key)]
    assert failure_result.committed


@pytest.mark.anyio
async def test_approve_review_persists_final_results_and_rag_chunks(monkeypatch):
    team_id = uuid4()
    document = Document(
        id=uuid4(),
        team_id=team_id,
        created_by_member_id=uuid4(),
        document_no="SL-DC-2026-0001",
        category_code="contract",
        title="합성 계약서",
        description=None,
        customer_company_id=None,
        customer_contact_id=None,
        sales_deal_id=None,
        purchase_order_id=None,
        tags=[],
        created_at=datetime.now(UTC),
    )
    row = FileRow(
        id=uuid4(),
        report_id=None,
        document_id=document.id,
        version_no=1,
        file_name="contract.txt",
        storage_key="team/contract.txt",
        media_type="text/plain",
        byte_size=32,
        processing_status="review_required",
        extracted_text=None,
        uploaded_by_member_id=document.created_by_member_id,
        note=None,
    )
    summary = DocumentSummaryOutput(
        summary="계약기간은 1년이다.",
        key_points=["계약기간: 1년"],
        source_refs=["계약서 1쪽"],
    )
    extracted = ExtractedDocument(
        plain_text="계약기간: 1년",
        markdown="## 계약 조건\n\n계약기간: 1년",
        payload={
            "source_type": "text",
            "pages": [{"page_number": 1, "markdown": "## 계약 조건\n\n계약기간: 1년"}],
        },
    )
    draft = document_processing._draft_bytes(extracted=extracted, summary=summary)

    async def _download(*, storage_key):
        assert storage_key == document_processing.draft_storage_key(row.storage_key)
        return draft

    db = _Session([object()])
    monkeypatch.setattr(type(settings), "embedding_configured", property(lambda self: False))
    monkeypatch.setattr(storage, "download", _download)

    await document_processing.approve_review(
        db,
        row=row,
        team_id=team_id,
        approved_by_member_id=document.created_by_member_id,
    )

    assert row.processing_status == "completed"
    assert row.extracted_text == "계약기간: 1년"
    assert "계약기간은 1년이다." in row.summary_markdown
    chunks = [item for item in db.added if item.__class__.__name__ == "DocumentChunk"]
    audits = [item for item in db.added if item.__class__.__name__ == "DocumentFileAudit"]
    assert len(chunks) == 1
    assert chunks[0].document_id == document.id
    assert chunks[0].page_start == 1
    assert len(audits) == 1
    assert audits[0].action_code == "summary_approved"
