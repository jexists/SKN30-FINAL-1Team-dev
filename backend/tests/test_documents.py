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
from app.services import business_cards, document_processing, sales_context, storage

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
        product_id=None,
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


@pytest.mark.parametrize("operation", ["create", "patch_existing_product"])
def test_document_rejects_product_and_deal_together(operation):
    member = _member()
    product_id = uuid4()
    sales_deal_id = uuid4()
    if operation == "create":
        db = _Db()
    else:
        document = _document(member)
        document.product_id = product_id
        db = _Db(_Result(scalar=document))

    with _client(db, member) as client:
        if operation == "create":
            response = client.post(
                "/api/documents",
                headers={"Origin": ORIGIN},
                json={
                    "category_code": "proposal",
                    "title": "동시 연결 자료",
                    "product_id": str(product_id),
                    "sales_deal_id": str(sales_deal_id),
                },
            )
        else:
            response = client.patch(
                f"/api/documents/{document.id}",
                headers={"Origin": ORIGIN},
                json={"sales_deal_id": str(sales_deal_id)},
            )

    assert response.status_code == 422
    assert response.json() == {"detail": "document_link_conflict"}
    assert db.commit_count == 0
    assert db.rollback_count == 1


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


def test_second_upload_to_a_document_is_rejected(storage_ready, monkeypatch):
    """자료 하나에 파일 하나다. 이미 파일이 있으면 거절하고 방금 올린 객체를 지운다."""
    uploaded: list[str] = []
    removed: list[str] = []

    async def _upload(**kwargs):
        uploaded.append(kwargs["storage_key"])

    async def _remove(**kwargs):
        removed.append(kwargs["storage_key"])

    monkeypatch.setattr(storage, "upload", _upload)
    monkeypatch.setattr(storage, "remove", _remove)

    member = _member()
    document = _document(member)
    db = _Db(
        _Result(scalar=document),
        _Result(scalar=None),
        _Result(scalar=document),
        _Result(scalar=uuid4()),
    )
    with _client(db, member) as client:
        first = client.post(
            f"/api/documents/{document.id}/files",
            headers={"Origin": ORIGIN},
            files={"upload": ("same.pdf", PDF, "application/pdf")},
        )
        second = client.post(
            f"/api/documents/{document.id}/files",
            headers={"Origin": ORIGIN},
            files={"upload": ("same.pdf", PDF, "application/pdf")},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"detail": "document_file_exists"}
    # 버전을 매기지 않고 언제나 1 로 저장한다. DB 검사가 1 이상을 요구한다.
    assert [row.version_no for row in db.added if isinstance(row, FileRow)] == [1]
    # 거절한 요청이 올린 객체는 고아로 남기지 않는다.
    assert len(uploaded) == 2
    assert removed == [uploaded[1]]


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


def test_process_route_reprocesses_completed_file_and_records_audit(monkeypatch):
    member = _member()
    document = _document(member)
    row = _file(document, member)
    row.processing_status = "completed"
    row.approved_by_member_id = member.id
    row.approved_at = NOW
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
    assert row.processing_status == "processing"
    assert row.processing_error is None
    assert row.approved_by_member_id is None
    assert row.approved_at is None
    assert scheduled == [row.id]
    audits = [item for item in db.added if item.__class__.__name__ == "DocumentFileAudit"]
    assert len(audits) == 1
    assert audits[0].action_code == "summary_reprocess_requested"


def test_process_batch_route_queues_all_files_for_server_processing(monkeypatch):
    member = _member()
    first = _file(_document(member), member)
    second = _file(_document(member), member)
    scheduled: list[list[object]] = []

    async def _execute_batch(file_ids):
        scheduled.append(file_ids)

    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))
    monkeypatch.setattr("app.services.document_processing.execute_batch", _execute_batch)
    db = _Db(_Result(rows=[(first, member.display_name), (second, member.display_name)]))

    with _client(db, member) as client:
        response = client.post(
            "/api/documents/process-batch",
            json={"file_ids": [str(first.id), str(second.id)]},
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 202
    assert [item["id"] for item in response.json()["files"]] == [
        str(first.id),
        str(second.id),
    ]
    assert first.processing_status == "processing"
    assert second.processing_status == "processing"
    assert scheduled == [[first.id, second.id]]
    assert db.commit_count == 1


def test_summary_route_exposes_review_draft(monkeypatch):
    member = _member()
    document = _document(member)
    row = _file(document, member)
    row.processing_status = "review_required"

    async def _draft(_storage_key):
        return {
            "extracted_text": "계약금액: 1,000원",
            "extracted_markdown": "## 금액\n\n계약금액: 1,000원",
            "extracted_payload": {"pages": []},
            "summary_markdown": "# 문서 요약\n\n계약금액은 1,000원이다.",
            "summary_payload": {"extracted_fields": {"계약금액": "1,000원"}},
        }

    monkeypatch.setattr(document_processing, "load_review_draft", _draft)
    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )
    with _client(db, member) as client:
        response = client.get(f"/api/documents/{document.id}/files/{row.id}/summary")

    assert response.status_code == 200
    assert response.json()["processing_status"] == "review_required"
    assert response.json()["extracted_text"] == "계약금액: 1,000원"


def test_summary_route_returns_saved_summary_again():
    member = _member()
    document = _document(member)
    row = _file(document, member)
    row.processing_status = "completed"
    row.extracted_text = "계약금액: 1,000원"
    row.extracted_markdown = "## 금액\n\n계약금액: 1,000원"
    row.extracted_payload = {"pages": [{"page_number": 1}]}
    row.summary_markdown = "# 문서 요약\n\n계약금액은 1,000원이다."
    row.summary_payload = {"extracted_fields": {"계약금액": "1,000원"}}
    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )

    with _client(db, member) as client:
        response = client.get(f"/api/documents/{document.id}/files/{row.id}/summary")

    assert response.status_code == 200
    assert response.json()["processing_status"] == "completed"
    assert response.json()["summary_markdown"] == row.summary_markdown


def test_approve_summary_route_commits_final_result(monkeypatch):
    member = _member()
    document = _document(member)
    row = _file(document, member)
    row.processing_status = "review_required"

    async def _approve(_db, *, row, team_id, approved_by_member_id):
        assert team_id == member.team_id
        assert approved_by_member_id == member.id
        row.processing_status = "completed"
        row.extracted_text = "승인된 원문"
        row.extracted_markdown = "승인된 원문"
        row.summary_markdown = "승인된 요약"
        row.summary_payload = {"approved": True}

    async def _remove(*, storage_key):
        assert storage_key.endswith(document_processing.DRAFT_SUFFIX)

    monkeypatch.setattr(document_processing, "approve_review", _approve)
    monkeypatch.setattr(storage, "remove", _remove)
    db = _Db(
        _Result(rows=[(document, member.display_name, None)]),
        _Result(scalar=row),
    )
    with _client(db, member) as client:
        response = client.post(
            f"/api/documents/{document.id}/files/{row.id}/approve-summary",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 200
    assert response.json()["processing_status"] == "completed"
    assert response.json()["summary_markdown"] == "승인된 요약"
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


def test_uploader_and_date_filters_look_at_one_file_only():
    """담당자·올린 날짜 필터는 문서에 딸린 파일 한 건만 본다.

    화면의 표가 그 파일의 올린 사람과 날짜를 보여 주므로 필터도 같은 파일을 봐야 한다.
    예전 자료에 남은 행까지 아무거나 맞으면 되게 하면, 예전에 올린 사람으로 걸러도
    문서가 나온다.
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

    # 한 건만 보도록 상관 서브쿼리로 좁힌다. 별칭 번호는 쿼리마다 달라 이름만 본다.
    assert "version_no DESC" in count_sql
    assert "LIMIT" in count_sql
    assert "document_id = public.document.id" in count_sql
    assert "uploaded_by_member_id IN" in count_sql
    assert "uploaded_at >=" in count_sql
    # 검색은 연결한 딜·상품 이름과 파일 이름까지 훑는다.
    assert "deal_no" in count_sql
    assert "file_name" in count_sql

    # 분류 탭 옆 건수는 분류만 빼고 나머지는 그대로 둔다.
    assert "document.category_code IN" in count_sql
    assert "document.category_code IN" not in counts_sql
    assert "uploaded_by_member_id IN" in counts_sql
