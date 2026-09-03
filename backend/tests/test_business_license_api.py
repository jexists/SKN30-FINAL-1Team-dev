import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_current_member
from app.core.config import settings
from app.main import app
from app.models.workspace import Member
from app.schemas.business_licenses import BusinessLicenseDraft, BusinessLicenseFields
from app.services import business_license_scans, business_licenses, ocr


def _scan_member() -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )


async def _ocr_ok(**_kwargs):
    from app.services.document_extraction import ExtractedDocument

    return ExtractedDocument(
        plain_text="사업자등록증\n상호: 합성 주식회사\n등록번호: 123-45-67890\n주소: 서울시 합성구",
        markdown="사업자등록증\n",
        payload={"pages": [{"page_number": 1}], "ocr_provider": "local"},
    )


def _accept_scan(monkeypatch, member: Member, *, file_name: str, content: bytes, media_type: str):
    async def _extract(**_kwargs):
        return BusinessLicenseDraft(
            fields=BusinessLicenseFields(
                company="합성 주식회사",
                business_no="123-45-67890",
                address="서울시 합성구",
            ),
            ready_for_company_registration=True,
        )

    monkeypatch.setattr(type(settings), "ocr_configured", property(lambda self: True))
    monkeypatch.setattr(ocr, "extract_document", _ocr_ok)
    monkeypatch.setattr(business_licenses, "extract", _extract)
    app.dependency_overrides[get_current_member] = lambda: member
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-licenses/scan",
                headers={"Origin": settings.cors_origin_list[0]},
                files={"file": (file_name, content, media_type)},
            )
    finally:
        app.dependency_overrides.clear()
    return response


def test_business_license_scan_accepts_pdf_and_returns_draft(monkeypatch):
    member = _scan_member()
    response = _accept_scan(
        monkeypatch,
        member,
        file_name="license.pdf",
        content=b"%PDF-synthetic",
        media_type="application/pdf",
    )

    assert response.status_code == 202
    scan_id = response.json()["scan_id"]
    app.dependency_overrides[get_current_member] = lambda: member
    try:
        with TestClient(app) as client:
            result = client.get(
                f"/api/business-licenses/scan/{scan_id}",
                headers={"Origin": settings.cors_origin_list[0]},
            )
    finally:
        app.dependency_overrides.clear()

    assert result.status_code == 200
    assert result.json()["processing_status"] == "completed"
    assert result.json()["fields"]["business_no"] == "123-45-67890"
    assert result.json()["ready_for_company_registration"] is True


def test_business_license_scan_accepts_image(monkeypatch):
    member = _scan_member()
    response = _accept_scan(
        monkeypatch,
        member,
        file_name="license.jpg",
        content=b"\xff\xd8\xffsynthetic",
        media_type="image/jpeg",
    )

    assert response.status_code == 202


def test_business_license_scan_rejects_other_document_types(monkeypatch):
    member = _scan_member()
    monkeypatch.setattr(type(settings), "ocr_configured", property(lambda self: True))
    app.dependency_overrides[get_current_member] = lambda: member
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-licenses/scan",
                headers={"Origin": settings.cors_origin_list[0]},
                files={"file": ("license.docx", b"PK\x03\x04", "application/octet-stream")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 415
    assert response.json()["detail"] == "business_license_unsupported_file"


def test_business_license_scan_hides_other_members_scan(monkeypatch):
    member = _scan_member()
    other = _scan_member()
    response = _accept_scan(
        monkeypatch,
        member,
        file_name="license.pdf",
        content=b"%PDF-synthetic",
        media_type="application/pdf",
    )
    scan_id = response.json()["scan_id"]
    app.dependency_overrides[get_current_member] = lambda: other
    try:
        with TestClient(app) as client:
            result = client.get(
                f"/api/business-licenses/scan/{scan_id}",
                headers={"Origin": settings.cors_origin_list[0]},
            )
    finally:
        app.dependency_overrides.clear()

    assert result.status_code == 404
    assert result.json()["detail"] == "business_license_scan_not_found"


def test_business_license_scan_state_expires_after_retention():
    member_id = uuid4()
    now = datetime.now(UTC)
    scan_id = business_license_scans.create(member_id=member_id, now=now)

    assert business_license_scans.get(scan_id, member_id=member_id, now=now) is not None
    expired = now + timedelta(seconds=business_license_scans.SCAN_RETENTION_SECONDS + 1)
    assert business_license_scans.get(scan_id, member_id=member_id, now=expired) is None


def test_business_license_scan_logs_no_ocr_values(monkeypatch, caplog):
    member = _scan_member()
    with caplog.at_level(logging.INFO, logger="app.services.agent_logging"):
        _accept_scan(
            monkeypatch,
            member,
            file_name="license.pdf",
            content=b"%PDF-synthetic",
            media_type="application/pdf",
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any('"stage": "business_license_scan_accepted"' in message for message in messages)
    assert any('"stage": "scan_completed"' in message for message in messages)
    assert not any("합성 주식회사" in message for message in messages)
