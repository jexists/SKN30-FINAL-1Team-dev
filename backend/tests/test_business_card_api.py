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
from app.services import business_cards, ocr, storage


def test_business_card_scan_route_returns_structured_draft(monkeypatch):
    member = Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )

    async def _ocr(**_kwargs):
        from app.services.document_extraction import ExtractedDocument

        return ExtractedDocument(
            plain_text="합성 담당자\n합성 회사\n010-0000-0000",
            markdown="합성 담당자\n합성 회사\n010-0000-0000\n",
            payload={"pages": [{"page_number": 1}]},
        )

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
    monkeypatch.setattr(ocr, "extract_document", _ocr)
    monkeypatch.setattr(business_cards, "extract", _extract)
    app.dependency_overrides[get_current_member] = lambda: member
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/business-cards/scan",
                headers={"Origin": settings.cors_origin_list[0]},
                files={"image": ("card.jpg", b"\xff\xd8\xfftest", "image/jpeg")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["fields"]["name"] == "합성 담당자"


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
            purchase_order_id=None,
            tags=["business_card", "archive"],
            created_by_member_id=member.id,
            created_by_display_name=member.display_name,
            created_at="2026-08-25T00:00:00Z",
            files=[],
            latest_version_no=1,
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
