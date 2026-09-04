import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
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


def _empty_draft() -> BusinessLicenseDraft:
    return BusinessLicenseDraft(
        fields=BusinessLicenseFields(business_no="123-45-67890"),
        missing_required_fields=["company"],
    )


def _full_draft() -> BusinessLicenseDraft:
    return BusinessLicenseDraft(
        fields=BusinessLicenseFields(
            company="합성 주식회사",
            business_no="123-45-67890",
            address="서울시 합성구",
            representative="합성 사람",
        ),
        ready_for_company_registration=True,
    )


def _stub_scan(monkeypatch, drafts: list[BusinessLicenseDraft]) -> list[str | None]:
    """호출마다 준비된 draft를 순서대로 돌려주고, 넘어온 media_type을 기록한다."""

    seen: list[str | None] = []

    async def _extract_document(**kwargs):
        seen.append(kwargs.get("media_type"))
        return await _ocr_ok()

    async def _extract(**_kwargs):
        return drafts[min(len(seen), len(drafts)) - 1]

    monkeypatch.setattr(ocr, "extract_document", _extract_document)
    monkeypatch.setattr(business_licenses, "extract", _extract)
    return seen


@pytest.mark.anyio
async def test_scanned_pdf_is_retried_as_an_image(monkeypatch):
    # PDF 경로에는 한국어 설정이 없어 한글이 통째로 빈다. 이미지로 구워 다시 읽는다.
    seen = _stub_scan(monkeypatch, [_empty_draft(), _full_draft()])
    monkeypatch.setattr(ocr, "render_pdf_page_png", lambda content, **_kwargs: b"\x89PNG-synthetic")

    member_id = uuid4()
    scan_id = business_license_scans.create(member_id=member_id)
    await business_license_scans.run(
        scan_id,
        file_name="license.pdf",
        media_type="application/pdf",
        content=b"%PDF-synthetic",
    )

    state = business_license_scans.get(scan_id, member_id=member_id)
    assert state is not None
    assert seen == ["application/pdf", "image/png"]
    assert state.processing_status == "completed"
    assert state.draft is not None
    assert state.draft.fields.company == "합성 주식회사"
    assert state.draft.fields.representative == "합성 사람"


@pytest.mark.anyio
async def test_first_draft_is_kept_when_the_image_retry_fails(monkeypatch):
    seen = _stub_scan(monkeypatch, [_empty_draft(), _full_draft()])

    def _render_fails(_content, **_kwargs):
        raise ocr.OcrError("pdf_render_dependency_missing")

    monkeypatch.setattr(ocr, "render_pdf_page_png", _render_fails)

    member_id = uuid4()
    scan_id = business_license_scans.create(member_id=member_id)
    await business_license_scans.run(
        scan_id,
        file_name="license.pdf",
        media_type="application/pdf",
        content=b"%PDF-synthetic",
    )

    state = business_license_scans.get(scan_id, member_id=member_id)
    assert state is not None
    assert seen == ["application/pdf"]
    # 재시도가 안 되더라도 1차 결과는 살아 있어야 한다.
    assert state.processing_status == "completed"
    assert state.draft is not None
    assert state.draft.fields.business_no == "123-45-67890"


@pytest.mark.anyio
async def test_text_pdf_is_not_retried_when_the_company_is_read(monkeypatch):
    seen = _stub_scan(monkeypatch, [_full_draft()])

    def _unexpected_render(_content, **_kwargs):
        raise AssertionError("회사명을 읽었으면 다시 굽지 않는다")

    monkeypatch.setattr(ocr, "render_pdf_page_png", _unexpected_render)

    member_id = uuid4()
    scan_id = business_license_scans.create(member_id=member_id)
    await business_license_scans.run(
        scan_id,
        file_name="license.pdf",
        media_type="application/pdf",
        content=b"%PDF-synthetic",
    )

    assert seen == ["application/pdf"]
