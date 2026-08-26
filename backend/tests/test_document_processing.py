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
async def test_execute_persists_extraction_summary_and_rag_chunks(monkeypatch):
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
    second = _Session([_Result(row), object()])
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
    assert len(second.added) == 1
    chunk = second.added[0]
    assert chunk.document_id == document.id
    assert chunk.page_start == 1
    assert chunk.page_end == 1
    assert chunk.content == "계약기간: 1년"
