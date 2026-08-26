import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import documents as documents_api
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.content import Document
from app.models.content import File as FileRow
from app.models.workspace import Member
from app.schemas.business_cards import BusinessCardDraft, BusinessCardFields
from app.schemas.documents import DocumentCreate, DocumentPageParams
from app.services import business_cards, sales_context, storage

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
PDF = b"%PDF-1.7\ntest\n"
_MISSING = object()


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, FileRow) and value.uploaded_at is None:
                value.uploaded_at = NOW

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def storage_ready(monkeypatch):
    monkeypatch.setattr(type(settings), "storage_configured", property(lambda self: True))
    yield


@pytest.fixture
def storage_missing(monkeypatch):
    monkeypatch.setattr(type(settings), "storage_configured", property(lambda self: False))
    yield


def _member(*, role: str = "member") -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _document(member: Member) -> Document:
    return Document(
        id=uuid4(),
        team_id=member.team_id,
        created_by_member_id=member.id,
        document_no="SL-DC-2026-0001",
        category_code="proposal",
        title="합성 자료",
        description=None,
        customer_company_id=None,
        sales_deal_id=None,
        purchase_order_id=None,
        tags=[],
        created_at=NOW,
    )


def _file(document: Document, member: Member) -> FileRow:
    return FileRow(
        id=uuid4(),
        report_id=None,
        document_id=document.id,
        version_no=1,
        file_name="제안서.pdf",
        storage_key=f"{member.team_id}/secret-object-key.pdf",
        media_type="application/pdf",
        byte_size=len(PDF),
        processing_status="uploaded",
        extracted_text=None,
        uploaded_by_member_id=member.id,
        note=None,
        uploaded_at=NOW,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_document_request_rejects_unsafe_values():
    with pytest.raises(ValidationError):
        # 업무 번호와 작성자는 요청으로 정할 수 없다.
        DocumentCreate(category_code="proposal", title="a", document_no="SL-DC-2026-0001")
    with pytest.raises(ValidationError):
        DocumentCreate(category_code="Proposal", title="a")
    with pytest.raises(ValidationError):
        DocumentCreate(category_code="proposal", title="")
    with pytest.raises(ValidationError):
        DocumentPageParams(limit=31)


def test_upload_requires_storage_configuration(storage_missing):
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        response = client.post(
            f"/api/documents/{uuid4()}/files",
            headers={"Origin": ORIGIN},
            files={"upload": ("a.pdf", PDF, "application/pdf")},
        )
    assert response.status_code == 503
    assert response.json() == {"detail": "storage_not_configured"}


@pytest.mark.parametrize(
    ("file_name", "media_type", "content", "detail", "code"),
    [
        ("악성.pdf", "application/pdf", b"MZ\x90\x00", "file_signature_mismatch", 415),
        ("a.zip", "application/zip", b"PK\x03\x04", "unsupported_file_extension", 415),
        ("a.pdf", "image/png", PDF, "media_type_mismatch", 415),
        ("a.pdf", "application/pdf", b"", "empty_file", 422),
        ("../a.pdf", "application/pdf", PDF, "invalid_file_name", 422),
    ],
)
def test_upload_rejects_bad_files_before_touching_storage(
    storage_ready, monkeypatch, file_name, media_type, content, detail, code
):
    uploaded: list[str] = []

    async def _never(**kwargs):
        uploaded.append(kwargs["storage_key"])

    monkeypatch.setattr(storage, "upload", _never)

    member = _member()
    db = _Db()
    with _client(db, member) as client:
        response = client.post(
            f"/api/documents/{uuid4()}/files",
            headers={"Origin": ORIGIN},
            files={"upload": (file_name, content, media_type)},
        )

    assert response.status_code == code
    assert response.json() == {"detail": detail}
    # 검증 전에 저장소를 건드리지 않는다.
    assert uploaded == []
    assert db.commit_count == 0


def test_upload_removes_object_when_db_write_fails(storage_ready, monkeypatch):
    uploaded: list[str] = []
    removed: list[str] = []

    async def _upload(**kwargs):
        uploaded.append(kwargs["storage_key"])

    async def _remove(**kwargs):
        removed.append(kwargs["storage_key"])

    monkeypatch.setattr(storage, "upload", _upload)
    monkeypatch.setattr(storage, "remove", _remove)

    member = _member()
    # 문서를 찾지 못해 404 로 끝난다.
    db = _Db(_Result(scalar=None))
    with _client(db, member) as client:
        response = client.post(
            f"/api/documents/{uuid4()}/files",
            headers={"Origin": ORIGIN},
            files={"upload": ("a.pdf", PDF, "application/pdf")},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    # 올린 객체를 지워 고아를 남기지 않는다.
    assert uploaded == removed
    assert len(removed) == 1
    assert db.rollback_count == 1


def test_download_never_exposes_storage_key(storage_ready, monkeypatch):
    member = _member()
    document = _document(member)
    row = _file(document, member)

    async def _signed(**kwargs):
        return "https://example.invalid/storage/v1/object/sign/x?token=abc"

    monkeypatch.setattr(storage, "signed_url", _signed)

    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )
    with _client(db, member) as client:
        response = client.get(
            f"/api/documents/{document.id}/files/{row.id}/download",
        )

    assert response.status_code == 200
    assert "storage_key" not in response.text
    assert row.storage_key not in response.text
    assert response.json()["expires_in"] == 60
    assert response.json()["file_name"] == "제안서.pdf"


@pytest.mark.parametrize("artifact", ["txt", "md", "json", "summary"])
def test_document_artifact_download_returns_processed_result(artifact):
    member = _member()
    document = _document(member)
    row = _file(document, member)
    row.extracted_text = "계약기간: 1년"
    row.extracted_markdown = "# 계약서\n\n계약기간: 1년"
    row.extracted_payload = {"source_type": "pdf", "pages": []}
    row.summary_markdown = "# 문서 요약\n\n- 계약기간: 1년"
    row.summary_payload = {"summary": "계약기간은 1년이다."}
    row.processing_status = "completed"

    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )
    with _client(db, member) as client:
        response = client.get(
            f"/api/documents/{document.id}/files/{row.id}/artifacts/{artifact}",
        )

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    if artifact == "json":
        assert response.json()["source_type"] == "pdf"
    else:
        assert "계약기간" in response.text


def test_process_route_marks_file_processing_and_schedules_summary(monkeypatch):
    member = _member()
    document = _document(member)
    row = _file(document, member)
    scheduled: list[object] = []

    async def _execute(file_id):
        scheduled.append(file_id)

    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))
    monkeypatch.setattr("app.services.document_processing.execute", _execute)
    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )

    with _client(db, member) as client:
        response = client.post(
            f"/api/documents/{document.id}/files/{row.id}/process",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 202
    assert response.json()["processing_status"] == "processing"
    assert row.processing_status == "processing"
    assert scheduled == [row.id]
    assert db.commit_count == 1


def test_business_card_draft_route_returns_confirmation_payload(monkeypatch):
    member = _member()
    document = _document(member)
    row = _file(document, member)
    row.file_name = "business-card.jpeg"
    row.media_type = "image/jpeg"
    row.processing_status = "completed"
    row.extracted_text = "합성 담당자\n합성 회사\n010-0000-0000"

    async def _extract(**kwargs):
        assert kwargs["ocr_text"] == row.extracted_text
        return BusinessCardDraft(
            fields=BusinessCardFields(
                name="합성 담당자",
                company_name="합성 회사",
                phone="010-0000-0000",
            ),
            ready_for_contact_registration=True,
        )

    monkeypatch.setattr(business_cards, "extract", _extract)
    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )
    with _client(db, member) as client:
        response = client.post(
            f"/api/documents/{document.id}/files/{row.id}/business-card-draft",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 200
    assert response.json()["ready_for_contact_registration"] is True
    assert response.json()["fields"]["company_name"] == "합성 회사"


def test_briefing_context_route_returns_rag_sources_and_summaries(monkeypatch):
    member = _member()
    sales_deal_id = uuid4()
    expected = {
        "query": "계약기간",
        "summaries": [
            {
                "file_id": str(uuid4()),
                "document_id": str(uuid4()),
                "file_name": "계약서.docx",
                "summary_markdown": "# 문서 요약\n\n계약기간은 1년이다.",
                "summary_payload": {"summary": "계약기간은 1년이다."},
            }
        ],
        "sources": [
            {
                "chunk_id": str(uuid4()),
                "document_id": str(uuid4()),
                "file_id": str(uuid4()),
                "file_name": "계약서.docx",
                "chunk_no": 0,
                "section": "계약 조건",
                "content": "계약기간은 1년으로 한다.",
                "score": 0.9,
                "metadata": {"source_type": "docx"},
            }
        ],
    }

    async def _context(_db, **kwargs):
        assert kwargs["team_id"] == member.team_id
        assert kwargs["query"] == "계약기간"
        assert kwargs["sales_deal_id"] == sales_deal_id
        return expected

    monkeypatch.setattr(sales_context, "retrieve_briefing_context", _context)
    with _client(_Db(), member) as client:
        response = client.get(
            f"/api/documents/briefing-context?q=계약기간&limit=5&sales_deal_id={sales_deal_id}"
        )

    assert response.status_code == 200
    assert response.json()["summaries"][0]["file_name"] == "계약서.docx"
    assert response.json()["sources"][0]["content"] == "계약기간은 1년으로 한다."


@pytest.mark.parametrize("artifact", ["text", "txt"])
def test_document_artifact_text_alias_returns_extracted_text(artifact):
    member = _member()
    document = _document(member)
    row = _file(document, member)
    row.processing_status = "completed"
    row.extracted_text = "OCR 평문 결과"
    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )

    with _client(db, member) as client:
        response = client.get(f"/api/documents/{document.id}/files/{row.id}/artifacts/{artifact}")

    assert response.status_code == 200
    assert response.text == "OCR 평문 결과"
    assert "text/plain" in response.headers["content-type"]


def test_other_team_document_is_hidden():
    member = _member()
    db = _Db(_Result(rows=[]))
    with _client(db, member) as client:
        response = client.get(f"/api/documents/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "document_not_found"}
    assert member.team_id in db.statements[0].compile().params.values()


def test_uploader_and_date_filters_look_at_the_latest_version_only():
    """담당자·올린 날짜 필터는 최신 버전 파일을 본다.

    화면의 표가 최신 버전의 올린 사람과 날짜를 보여 주므로 필터도 같은 파일을 봐야 한다.
    아무 버전이나 맞으면 되게 하면, 예전 버전을 올린 사람으로 걸러도 문서가 나온다.
    """
    member = _member()
    db = _Db(_Result(scalar=0), _Result(rows=[]), _Result(rows=[]), _Result(rows=[]))

    page = asyncio.run(
        documents_api.list_documents(
            DocumentPageParams(
                latest_uploader_member_id=[member.id],
                latest_uploaded_from=datetime(2026, 3, 1, tzinfo=UTC),
                category_code=["proposal"],
                q="합성",
            ),
            member,
            db,
        )
    )

    assert page.counts == {}
    count_sql = str(db.statements[0])
    counts_sql = str(db.statements[2])

    # 최신 한 건만 보도록 상관 서브쿼리로 좁힌다. 별칭 번호는 쿼리마다 달라 이름만 본다.
    assert "version_no DESC" in count_sql
    assert "LIMIT" in count_sql
    assert "document_id = public.document.id" in count_sql
    assert "uploaded_by_member_id IN" in count_sql
    assert "uploaded_at >=" in count_sql
    # 검색은 태그와 최신 파일 이름까지 훑는다.
    assert "document.tags" in count_sql
    assert "file_name" in count_sql

    # 분류 탭 옆 건수는 분류만 빼고 나머지는 그대로 둔다.
    assert "document.category_code IN" in count_sql
    assert "document.category_code IN" not in counts_sql
    assert "uploaded_by_member_id IN" in counts_sql
