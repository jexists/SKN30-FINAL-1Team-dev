import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_member, get_db
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
    assert result.json()["fields"]["business_no"] == "1234567890"
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
    assert state.draft.fields.business_no == "1234567890"


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


def _archive_member() -> Member:
    return _scan_member()


def _pdf(size: int = 64) -> bytes:
    return b"%PDF-1.7\n" + b"0" * size


def test_business_license_archive_links_original_to_company(monkeypatch):
    from app.models.content import Document
    from app.models.crm import CustomerCompany
    from app.schemas.documents import DocumentRead
    from app.services import storage

    member = _archive_member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="합성 회사")

    class _Result:
        def scalar_one_or_none(self):
            return company

    class _Db:
        def __init__(self):
            self.added = []
            self.committed = False

        async def execute(self, _statement):
            return _Result()

        def add(self, value):
            self.added.append(value)

        async def commit(self):
            self.committed = True

        async def rollback(self):
            raise AssertionError("rollback should not run")

    db = _Db()
    uploaded = []

    async def _upload(**kwargs):
        uploaded.append(kwargs)

    async def _detail(_db, _member, document_id):
        return DocumentRead(
            id=document_id,
            document_no="SL-DC-2026-0002",
            category_code="business_license",
            title="합성 회사 사업자등록증",
            description="사업자등록증 등록 시 보관된 원본",
            customer_company_id=company.id,
            customer_company_name=company.name,
            customer_contact_id=None,
            sales_deal_id=None,
            sales_deal_no=None,
            purchase_order_id=None,
            product_id=None,
            product_name=None,
            tags=["business_license", "archive"],
            created_by_member_id=member.id,
            created_by_display_name=member.display_name,
            owner_member_id=member.id,
            owner_display_name=member.display_name,
            created_at="2026-09-09T00:00:00Z",
            file=None,
        )

    async def _next_document_no(*_args):
        return "SL-DC-2026-0002"

    monkeypatch.setattr(type(settings), "storage_configured", property(lambda self: True))
    monkeypatch.setattr(storage, "upload", _upload)
    monkeypatch.setattr(storage, "build_storage_key", lambda *_args: "team/license.pdf")
    monkeypatch.setattr("app.api.documents._detail", _detail)
    monkeypatch.setattr("app.api.documents._next_document_no", _next_document_no)
    app.dependency_overrides[get_current_member] = lambda: member

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-licenses/archive",
                headers={"Origin": settings.cors_origin_list[0]},
                data={"company_id": str(company.id)},
                files={"file": ("license.pdf", _pdf(), "application/pdf")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert db.committed
    assert uploaded[0]["content"].startswith(b"%PDF-")
    archived = next(value for value in db.added if isinstance(value, Document))
    # 등록증은 사람이 아니라 회사의 문서다.
    assert archived.customer_company_id == company.id
    assert archived.customer_contact_id is None
    assert archived.category_code == "business_license"


def test_business_license_archive_rejects_other_team_company(monkeypatch):
    from app.services import storage

    member = _archive_member()

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Db:
        async def execute(self, _statement):
            return _Result()

        def add(self, value):
            raise AssertionError("add should not run")

        async def commit(self):
            raise AssertionError("commit should not run")

    removed = []

    async def _upload(**_kwargs):
        return None

    async def _remove(**kwargs):
        removed.append(kwargs)

    monkeypatch.setattr(type(settings), "storage_configured", property(lambda self: True))
    monkeypatch.setattr(storage, "upload", _upload)
    monkeypatch.setattr(storage, "remove", _remove)
    app.dependency_overrides[get_current_member] = lambda: member

    async def _db():
        yield _Db()

    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-licenses/archive",
                headers={"Origin": settings.cors_origin_list[0]},
                data={"company_id": str(uuid4())},
                files={"file": ("license.pdf", _pdf(), "application/pdf")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "customer_company_not_found"
    # 회사를 확인하기 전에 올리지 않으므로 지울 것도 없다.
    assert removed == []


def test_business_license_archive_rejects_unsupported_file(monkeypatch):
    member = _archive_member()

    monkeypatch.setattr(type(settings), "storage_configured", property(lambda self: True))
    app.dependency_overrides[get_current_member] = lambda: member

    # 확장자에서 막히므로 세션을 쓰지는 않지만, 의존성은 엔드포인트에 들어가기 전에 모두
    # 풀린다. 진짜 get_db 로 두면 DATABASE_URL 이 없는 CI 에서 415 대신 RuntimeError 가 난다.
    class _Db:
        async def execute(self, _statement):
            raise AssertionError("확장자에서 막히므로 조회할 것이 없다")

    async def _db():
        yield _Db()

    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-licenses/archive",
                headers={"Origin": settings.cors_origin_list[0]},
                data={"company_id": str(uuid4())},
                files={"file": ("license.exe", b"MZ\x00\x00", "application/octet-stream")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 415
    assert response.json()["detail"] == "business_license_unsupported_file"
