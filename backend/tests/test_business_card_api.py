import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_current_member, get_db
from app.core.config import settings
from app.main import app
from app.models.content import Document
from app.models.crm import CustomerCompany, CustomerContact
from app.models.workspace import Member
from app.schemas.business_cards import BusinessCardDraft, BusinessCardFields
from app.schemas.documents import DocumentRead
from app.services import business_card_scans, business_cards, ocr, storage

_SYNTHETIC_OCR_TEXT = "합성 담당자\n합성 회사\n010-0000-0000"


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
        plain_text=_SYNTHETIC_OCR_TEXT,
        markdown=f"{_SYNTHETIC_OCR_TEXT}\n",
        payload={"pages": [{"page_number": 1}], "ocr_provider": "runpod"},
    )


def _accept_scan(monkeypatch, member: Member, ocr_call) -> str:
    """인식을 접수하고 scan_id 를 돌려준다. TestClient 는 응답 뒤 백그라운드까지 끝낸다."""

    async def _extract(**_kwargs):
        return BusinessCardDraft(
            fields=BusinessCardFields(
                name="합성 담당자",
                company_name="합성 회사",
                phone="010-0000-0000",
            ),
            ready_for_contact_registration=True,
        )

    monkeypatch.setattr(type(settings), "ocr_configured", property(lambda self: True))
    monkeypatch.setattr(ocr, "extract_document", ocr_call)
    monkeypatch.setattr(business_cards, "extract", _extract)
    app.dependency_overrides[get_current_member] = lambda: member
    with TestClient(app) as client:
        response = client.post(
            "/api/business-cards/scan",
            headers={"Origin": settings.cors_origin_list[0]},
            files={"image": ("card.jpg", b"\xff\xd8\xfftest", "image/jpeg")},
        )
    assert response.status_code == 202
    assert response.json()["processing_status"] == "processing"
    return response.json()["scan_id"]


def test_business_card_scan_route_accepts_then_serves_draft(monkeypatch):
    member = _scan_member()
    try:
        scan_id = _accept_scan(monkeypatch, member, _ocr_ok)
        with TestClient(app) as client:
            response = client.get(
                f"/api/business-cards/scan/{scan_id}",
                headers={"Origin": settings.cors_origin_list[0]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["processing_status"] == "completed"
    assert body["fields"]["name"] == "합성 담당자"
    assert body["ready_for_contact_registration"] is True
    assert body["processing_error"] is None


def test_business_card_scan_status_keeps_provider_failure_code(monkeypatch):
    member = _scan_member()

    async def _ocr_fails(**_kwargs):
        raise ocr.OcrError("runpod_job_failed")

    try:
        scan_id = _accept_scan(monkeypatch, member, _ocr_fails)
        with TestClient(app) as client:
            response = client.get(
                f"/api/business-cards/scan/{scan_id}",
                headers={"Origin": settings.cors_origin_list[0]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["processing_status"] == "failed"
    # 화면 문구가 의존하는 코드다. 제공자 원문 오류는 내보내지 않는다.
    assert body["processing_error"] == "ocr_unavailable"
    assert body["fields"] is None


def test_business_card_scan_status_hides_other_members_scan(monkeypatch):
    member = _scan_member()
    other = _scan_member()
    try:
        scan_id = _accept_scan(monkeypatch, member, _ocr_ok)
        app.dependency_overrides[get_current_member] = lambda: other
        with TestClient(app) as client:
            response = client.get(
                f"/api/business-cards/scan/{scan_id}",
                headers={"Origin": settings.cors_origin_list[0]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "business_card_scan_not_found"


def test_business_card_scan_state_expires_after_retention():
    member_id = uuid4()
    now = datetime.now(UTC)
    scan_id = business_card_scans.create(member_id=member_id, now=now)

    assert business_card_scans.get(scan_id, member_id=member_id, now=now) is not None
    expired = now + timedelta(seconds=business_card_scans.SCAN_RETENTION_SECONDS + 1)
    assert business_card_scans.get(scan_id, member_id=member_id, now=expired) is None


def test_business_card_scan_logs_stages_with_ocr_provider(monkeypatch, caplog):
    member = _scan_member()
    try:
        with caplog.at_level(logging.INFO, logger="app.services.agent_logging"):
            _accept_scan(monkeypatch, member, _ocr_ok)
    finally:
        app.dependency_overrides.clear()

    messages = [record.getMessage() for record in caplog.records]
    assert any('"stage": "business_card_scan_accepted"' in message for message in messages)
    # 원격 OCR이 로컬로 폴백했는지 콘솔에서 바로 구분할 수 있어야 한다.
    assert any(
        '"stage": "ocr_completed"' in message and '"ocr_provider": "runpod"' in message
        for message in messages
    )
    assert any('"stage": "scan_completed"' in message for message in messages)
    # 명함 원문과 추출 값은 허용 필드가 아니라 로그에 남지 않는다.
    assert not any("합성 담당자" in message for message in messages)


def test_business_card_scan_logs_failure_reason(monkeypatch, caplog):
    member = _scan_member()

    async def _ocr_fails(**_kwargs):
        raise ocr.OcrError("runpod_job_failed")

    try:
        with caplog.at_level(logging.INFO, logger="app.services.agent_logging"):
            _accept_scan(monkeypatch, member, _ocr_fails)
    finally:
        app.dependency_overrides.clear()

    messages = [record.getMessage() for record in caplog.records]
    assert any('"error_code": "ocr_unavailable"' in message for message in messages)


def test_business_card_matches_route_returns_confirmation_candidates(monkeypatch):
    member = Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )
    candidate = {
        "contact_id": uuid4(),
        "company_id": uuid4(),
        "company_name": "합성 회사",
        "name": "합성 담당자",
        "phone": "010-0000-0000",
        "email": None,
        "matched_by": ["phone"],
    }

    async def _matches(_db, **kwargs):
        assert kwargs["member"] is member
        assert kwargs["fields"].phone == "010-0000-0000"
        return [candidate]

    async def _db():
        yield object()

    monkeypatch.setattr(business_cards, "find_matches", _matches)
    app.dependency_overrides[get_current_member] = lambda: member
    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-cards/matches",
                headers={"Origin": settings.cors_origin_list[0]},
                json={
                    "name": "합성 담당자",
                    "company_name": "합성 회사",
                    "phone": "010-0000-0000",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["matched_by"] == ["phone"]


def test_business_card_archive_links_original_to_contact(monkeypatch):
    member = Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="합성 회사")
    contact = CustomerContact(id=uuid4(), company_id=company.id, name="합성 담당자")

    class _Result:
        def one_or_none(self):
            return contact, company

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
            document_no="SL-DC-2026-0001",
            category_code="business_card",
            title="합성 담당자 명함",
            description="명함 등록 시 보관된 원본 이미지",
            customer_company_id=company.id,
            customer_company_name=company.name,
            customer_contact_id=contact.id,
            sales_deal_id=None,
            sales_deal_no=None,
            purchase_order_id=None,
            product_id=None,
            product_name=None,
            tags=["business_card", "archive"],
            created_by_member_id=member.id,
            created_by_display_name=member.display_name,
            created_at="2026-08-25T00:00:00Z",
            file=None,
        )

    async def _next_document_no(*_args):
        return "SL-DC-2026-0001"

    monkeypatch.setattr(type(settings), "storage_configured", property(lambda self: True))
    monkeypatch.setattr(storage, "upload", _upload)
    monkeypatch.setattr(storage, "build_storage_key", lambda *_args: "team/card.jpg")
    monkeypatch.setattr("app.api.documents._detail", _detail)
    monkeypatch.setattr("app.api.documents._next_document_no", _next_document_no)
    app.dependency_overrides[get_current_member] = lambda: member

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-cards/archive",
                headers={"Origin": settings.cors_origin_list[0]},
                data={"contact_id": str(contact.id)},
                files={"image": ("card.jpg", b"\xff\xd8\xfftest", "image/jpeg")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert db.committed
    assert uploaded[0]["content"] == b"\xff\xd8\xfftest"
    archived = next(value for value in db.added if isinstance(value, Document))
    assert archived.customer_contact_id == contact.id
    assert archived.customer_company_id == company.id
