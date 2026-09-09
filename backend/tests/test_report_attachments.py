import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member
from app.services import report_attachments, storage
from app.services.document_extraction import ExtractedDocument, ExtractionError

ORIGIN = settings.cors_origin_list[0]
PDF = b"%PDF-1.7\nsynthetic\n"


def _member() -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )


class _UploadDb:
    def __init__(self, *, fail_commit: int | None = None):
        self.rows = []
        self.deleted = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit

    def add(self, row):
        self.rows.append(row)

    async def execute(self, statement):
        assert "FOR UPDATE" in str(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: self.rows[0] if self.rows else None)

    async def delete(self, row):
        self.deleted.append(row)

    async def commit(self):
        self.commits += 1
        if self.commits == self.fail_commit:
            raise RuntimeError("synthetic database failure")

    async def rollback(self):
        self.rollbacks += 1


def _client(member: Member, db=None) -> TestClient:
    async def override_db():
        return db or _UploadDb()

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_dependencies(monkeypatch):
    app.dependency_overrides.clear()
    monkeypatch.setattr(settings, "supabase_url", "https://storage.invalid")
    monkeypatch.setattr(settings, "supabase_storage_bucket", "synthetic")
    monkeypatch.setattr(settings, "supabase_secret_key", SecretStr("synthetic"))
    monkeypatch.setattr(storage, "upload", AsyncMock())
    monkeypatch.setattr(storage, "remove", AsyncMock(return_value=True))
    yield
    app.dependency_overrides.clear()


def test_attachment_limits_require_authentication():
    async def override_db():
        return _UploadDb()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        response = client.get("/api/report-attachments/limits")
    assert response.status_code == 401
    assert response.json() == {"detail": "not_authenticated"}


def test_attachment_limits_return_only_effective_upload_settings(monkeypatch):
    monkeypatch.setattr(settings, "stt_max_bytes", 321)
    monkeypatch.setattr(settings, "upload_max_bytes", 654)
    monkeypatch.setattr(settings, "ocr_runpod_inline_max_bytes", 1)
    with _client(_member()) as client:
        response = client.get("/api/report-attachments/limits")
        assert response.status_code == 200
        assert response.json() == {"audio_max_bytes": 321, "document_max_bytes": 654}
        monkeypatch.setattr(settings, "upload_max_bytes", 987)
        assert client.get("/api/report-attachments/limits").json() == {
            "audio_max_bytes": 321,
            "document_max_bytes": 987,
        }


@pytest.mark.parametrize(
    "name,media,content,setting",
    [
        ("proposal.pdf", "application/pdf", PDF, "upload_max_bytes"),
        ("meeting.mp3", "audio/mpeg", b"ID3synthetic", "stt_max_bytes"),
    ],
)
def test_upload_enforces_advertised_limit_before_extraction(
    monkeypatch, name, media, content, setting
):
    extract = AsyncMock(
        return_value=ExtractedDocument(plain_text="합성 추출문", markdown="합성 추출문", payload={})
    )
    monkeypatch.setattr(report_attachments, "extract", extract)
    monkeypatch.setattr(settings, setting, len(content))
    db = _UploadDb()
    with _client(_member(), db) as client:
        limits = client.get("/api/report-attachments/limits").json()
        key = "audio_max_bytes" if setting == "stt_max_bytes" else "document_max_bytes"
        assert limits[key] == len(content)
        rejected = client.post(
            "/api/report-attachments",
            headers={"Origin": ORIGIN},
            files={"upload": (name, content + b"x", media)},
        )
        assert rejected.status_code == 413
        assert rejected.json() == {"detail": "file_too_large"}
        assert not db.rows
        extract.assert_not_awaited()
        storage.upload.assert_not_awaited()
        accepted = client.post(
            "/api/report-attachments",
            headers={"Origin": ORIGIN},
            files={"upload": (name, content, media)},
        )
        assert accepted.status_code == 201
        extract.assert_awaited_once()


def test_upload_keeps_original_with_owner_metadata_and_expiry(monkeypatch):
    async def extract(**kwargs):
        assert kwargs == {
            "file_name": "proposal.pdf",
            "media_type": "application/pdf",
            "content": PDF,
        }
        return ExtractedDocument(
            plain_text="서버가 추출한 제안 조건",
            markdown="서버가 추출한 제안 조건\n",
            payload={"version": 1, "source_type": "pdf"},
        )

    monkeypatch.setattr(report_attachments, "extract", extract)
    member, db = _member(), _UploadDb()
    with _client(member, db) as client:
        response = client.post(
            "/api/report-attachments",
            headers={"Origin": ORIGIN},
            files={"upload": ("proposal.pdf", PDF, "application/pdf")},
        )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "kind", "name", "byte_size", "extract", "original_stored"}
    assert UUID(body["id"])
    assert body | {"id": None} == {
        "id": None,
        "kind": "pdf",
        "name": "proposal.pdf",
        "byte_size": len(PDF),
        "extract": "서버가 추출한 제안 조건",
        "original_stored": True,
    }
    row = db.rows[0]
    assert row.team_id == member.team_id and row.uploaded_by_member_id == member.id
    assert row.report_id is None and row.extracted_text == body["extract"]
    assert row.expires_at - row.uploaded_at == report_attachments.PENDING_RETENTION
    assert row.storage_key.startswith(f"{member.team_id}/") and "proposal" not in row.storage_key
    storage.upload.assert_awaited_once_with(
        storage_key=row.storage_key, content=PDF, media_type="application/pdf"
    )
    assert db.commits == 2


def test_upload_maps_extraction_failure_without_leaking_provider_detail(monkeypatch):
    async def extract(**_kwargs):
        raise ExtractionError("provider response containing private text")

    monkeypatch.setattr(report_attachments, "extract", extract)

    with _client(_member()) as client:
        response = client.post(
            "/api/report-attachments",
            headers={"Origin": ORIGIN},
            files={"upload": ("proposal.pdf", PDF, "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "report_attachment_extraction_failed"}


def test_upload_maps_runpod_inline_limit_to_413(monkeypatch):
    async def extract(**_kwargs):
        raise ExtractionError("report_attachment_ocr_too_large")

    monkeypatch.setattr(report_attachments, "extract", extract)

    with _client(_member()) as client:
        response = client.post(
            "/api/report-attachments",
            headers={"Origin": ORIGIN},
            files={"upload": ("proposal.pdf", PDF, "application/pdf")},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "report_attachment_ocr_too_large"}


def test_report_attachment_has_no_delete_route():
    with _client(_member()) as client:
        response = client.delete(
            f"/api/report-attachments/{uuid4()}",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 404


def test_audio_reuses_stt(monkeypatch):
    async def transcribe(**kwargs):
        assert kwargs["content"] == b"audio"
        return "후속 미팅은 화요일입니다."

    monkeypatch.setattr(report_attachments.stt, "transcribe", transcribe)

    result = asyncio.run(
        report_attachments.extract(
            file_name="meeting.wav",
            media_type="audio/wav",
            content=b"audio",
        )
    )

    assert result.plain_text == "후속 미팅은 화요일입니다."


def test_runpod_ocr_uses_inline_content_without_storage(monkeypatch):
    content = b"small-image"
    captured = {}

    def require_ocr(**_kwargs):
        raise ExtractionError("ocr_provider_required")

    async def extract_ocr(**kwargs):
        captured.update(kwargs)
        return ExtractedDocument(
            plain_text="이미지에서 추출한 텍스트",
            markdown="이미지에서 추출한 텍스트\n",
            payload={"version": 1, "source_type": "ocr"},
        )

    async def unexpected_storage(**_kwargs):
        raise AssertionError("인라인 OCR 원본을 스토리지에 저장했습니다.")

    monkeypatch.setattr(report_attachments, "extract_document", require_ocr)
    monkeypatch.setattr(report_attachments.ocr, "extract_document", extract_ocr)
    monkeypatch.setattr(storage, "upload", unexpected_storage)
    monkeypatch.setattr(settings, "ocr_provider", "runpod")
    monkeypatch.setattr(settings, "ocr_runpod_inline_max_bytes", len(content))

    result = asyncio.run(
        report_attachments.extract(
            file_name="photo.png",
            media_type="image/png",
            content=content,
        )
    )

    assert result.plain_text == "이미지에서 추출한 텍스트"
    assert captured.get("source_url") is None


def test_large_runpod_ocr_is_rejected_without_storage(monkeypatch):
    def require_ocr(**_kwargs):
        raise ExtractionError("ocr_required")

    async def unexpected_storage(**_kwargs):
        raise AssertionError("큰 OCR 원본을 스토리지에 저장했습니다.")

    monkeypatch.setattr(report_attachments, "extract_document", require_ocr)
    monkeypatch.setattr(storage, "upload", unexpected_storage)
    monkeypatch.setattr(settings, "ocr_provider", "runpod")
    monkeypatch.setattr(settings, "ocr_runpod_inline_max_bytes", 1)

    with pytest.raises(ExtractionError, match="report_attachment_ocr_too_large"):
        asyncio.run(
            report_attachments.extract(
                file_name="scan.pdf",
                media_type="application/pdf",
                content=b"large",
            )
        )


@pytest.mark.parametrize(
    "fail_commit,storage_error,removed",
    [
        (1, False, True),
        (2, False, True),
        (2, False, False),
        (None, True, False),
    ],
)
def test_upload_failure_keeps_cleanup_retryable(monkeypatch, fail_commit, storage_error, removed):
    monkeypatch.setattr(
        report_attachments,
        "extract",
        AsyncMock(
            return_value=ExtractedDocument(
                plain_text="합성 추출문", markdown="합성 추출문", payload={}
            )
        ),
    )
    if storage_error:
        storage.upload.side_effect = storage.StorageError("storage_request_failed:Timeout")
    storage.remove.return_value = removed
    db = _UploadDb(fail_commit=fail_commit)
    with _client(_member(), db) as client:
        if fail_commit:
            with pytest.raises(RuntimeError, match="synthetic database failure"):
                client.post(
                    "/api/report-attachments",
                    headers={"Origin": ORIGIN},
                    files={"upload": ("proposal.pdf", PDF, "application/pdf")},
                )
        else:
            response = client.post(
                "/api/report-attachments",
                headers={"Origin": ORIGIN},
                files={"upload": ("proposal.pdf", PDF, "application/pdf")},
            )
            assert response.status_code == 503
    if fail_commit == 1:
        storage.upload.assert_not_awaited()
        storage.remove.assert_not_awaited()
    else:
        storage.remove.assert_awaited_once()
        assert bool(db.deleted) == removed
        if not removed:
            assert (
                db.rows[0].expires_at
                <= db.rows[0].uploaded_at + report_attachments.PENDING_RETENTION
            )
    assert db.rollbacks >= 1


@pytest.mark.parametrize(
    "name,media,content,expected",
    [
        ("../proposal.pdf", "application/pdf", PDF, 422),
        ("proposal.pdf", "image/png", PDF, 415),
        ("proposal.pdf", "application/pdf", b"not a pdf", 415),
        ("payload.html", "text/html", b"<html>bad</html>", 415),
        ("proposal.pdf", "application/pdf", b"", 422),
    ],
)
def test_invalid_original_never_reaches_storage(monkeypatch, name, media, content, expected):
    extract = AsyncMock()
    monkeypatch.setattr(report_attachments, "extract", extract)
    db = _UploadDb()
    with _client(_member(), db) as client:
        response = client.post(
            "/api/report-attachments",
            headers={"Origin": ORIGIN},
            files={"upload": (name, content, media)},
        )
    assert response.status_code == expected
    assert not db.rows
    extract.assert_not_awaited()
    storage.upload.assert_not_awaited()
