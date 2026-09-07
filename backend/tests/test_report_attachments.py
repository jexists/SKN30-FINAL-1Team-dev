import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

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


def _client(member: Member) -> TestClient:
    async def unexpected_db():
        raise AssertionError("일회용 첨부 API가 DB를 요청했습니다.")

    async def override_member():
        return member

    app.dependency_overrides[get_db] = unexpected_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_dependencies():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_upload_extracts_without_database_or_durable_storage(monkeypatch):
    async def unexpected_storage(**_kwargs):
        raise AssertionError("일회용 첨부를 영구 스토리지에 저장했습니다.")

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

    monkeypatch.setattr(storage, "upload", unexpected_storage)
    monkeypatch.setattr(report_attachments, "extract", extract)

    with _client(_member()) as client:
        response = client.post(
            "/api/report-attachments",
            headers={"Origin": ORIGIN},
            files={"upload": ("proposal.pdf", PDF, "application/pdf")},
        )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "kind", "name", "byte_size", "extract"}
    assert UUID(body["id"])
    assert body | {"id": None} == {
        "id": None,
        "kind": "pdf",
        "name": "proposal.pdf",
        "byte_size": len(PDF),
        "extract": "서버가 추출한 제안 조건",
    }


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
