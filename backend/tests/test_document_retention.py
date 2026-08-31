from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.content import Document
from app.models.content import File as FileRow
from app.services import document_retention, storage


class _Result:
    def __init__(self, rows=None, rowcount=0):
        self.rows = [] if rows is None else rows
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self, *results):
        self.results = iter(results)
        self.deleted = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, _statement):
        return next(self.results)

    async def delete(self, row):
        self.deleted.append(row)

    async def commit(self):
        self.committed = True


@pytest.mark.anyio
async def test_cleanup_expired_applies_separate_review_file_and_audit_retention(monkeypatch):
    now = datetime(2026, 8, 28, tzinfo=UTC)
    document = Document(id=uuid4())
    expired_review = FileRow(
        id=uuid4(),
        document_id=document.id,
        storage_key="team/review.pdf",
        processing_status="review_required",
        uploaded_at=now - timedelta(days=8),
        processed_at=now - timedelta(days=8),
    )
    db = _Db(_Result([expired_review]), _Result(rowcount=4))
    removed = []

    async def _remove(*, storage_key):
        removed.append(storage_key)

    monkeypatch.setattr(document_retention, "get_sessionmaker", lambda: lambda: db)
    monkeypatch.setattr(storage, "remove", _remove)

    result = await document_retention.cleanup_expired(now=now)

    assert result.expired_unapproved_files == 0
    assert result.expired_review_drafts == 1
    assert result.deleted_audit_logs == 4
    assert removed == ["team/review.pdf.document-summary-draft.json"]
    assert db.deleted == []
    assert expired_review.processing_status == "failed"
    assert expired_review.processing_error == "review_expired"
    assert db.committed
