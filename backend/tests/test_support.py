from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.crm import CustomerCompany, CustomerContact, SupportRequest, SupportResponse
from app.models.workspace import Member
from app.schemas.support import (
    SupportRequestCreate,
    SupportRequestPageParams,
    SupportResponseCreate,
    SupportTransition,
)

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
_MISSING = object()


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None, scalar_values=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows
        self.scalar_values = [] if scalar_values is None else scalar_values

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

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result, flush_error: Exception | None = None):
        self.results = list(results)
        self.flush_error = flush_error
        self.statements = []
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1
        if self.flush_error is not None:
            raise self.flush_error
        for value in self.added:
            if isinstance(value, SupportRequest) and value.registered_at is None:
                value.registered_at = NOW
            if isinstance(value, SupportResponse) and value.responded_at is None:
                value.responded_at = NOW

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name="합성 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _company(team_id: UUID) -> CustomerCompany:
    return CustomerCompany(
        id=uuid4(),
        team_id=team_id,
        name="합성 고객사",
        region_code="seoul",
        created_at=NOW,
    )


def _contact(owner: Member, company: CustomerCompany) -> CustomerContact:
    return CustomerContact(
        id=uuid4(),
        company_id=company.id,
        owner_member_id=owner.id,
        name="합성 고객",
        department="구매팀",
        job_title="팀장",
        email=None,
        phone="010-0000-0000",
        customer_contact_status_id=None,
        source_code=None,
        memo=None,
        registered_at=NOW,
    )


def _request(
    assignee: Member,
    contact: CustomerContact,
    *,
    status_code: str = "in_progress",
) -> SupportRequest:
    return SupportRequest(
        id=uuid4(),
        team_id=assignee.team_id,
        customer_contact_id=contact.id,
        assignee_member_id=assignee.id,
        title="합성 문의",
        body="합성 문의 본문",
        is_urgent=True,
        status_code=status_code,
        registered_at=NOW,
    )


def _support_response(request: SupportRequest, responder: Member) -> SupportResponse:
    return SupportResponse(
        id=uuid4(),
        support_request_id=request.id,
        responder_member_id=responder.id,
        body="합성 답변",
        responded_at=NOW,
    )


def _row(
    request: SupportRequest,
    contact: CustomerContact,
    company: CustomerCompany,
    assignee: Member,
):
    return request, contact.name, company.id, company.name, assignee.display_name


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def _payload(contact: CustomerContact, **overrides):
    values = {
        "customer_contact_id": str(contact.id),
        "title": " 합성 문의 ",
        "body": " 합성 문의 본문 ",
        "is_urgent": True,
        "status_code": "in_progress",
    }
    return values | overrides


def test_support_write_models_are_strict_and_allow_only_two_status_codes():
    contact_id = uuid4()
    parsed = SupportRequestCreate(
        customer_contact_id=contact_id,
        title=" 문의 ",
        body=" 본문 ",
        is_urgent=True,
        status_code="completed",
    )
    assert parsed.title == "문의"
    assert parsed.body == "본문"
    assert SupportRequestPageParams(status_code=["in_progress", "completed"])

    invalid_payloads = (
        {"body": " "},
        {"status_code": "처리중"},
        {"is_urgent": 1},
        {"unknown": "value"},
    )
    for invalid in invalid_payloads:
        with pytest.raises(ValidationError):
            SupportRequestCreate(
                **{
                    "customer_contact_id": contact_id,
                    "title": "문의",
                    "body": "본문",
                    "is_urgent": True,
                    "status_code": "in_progress",
                }
                | invalid
            )
    with pytest.raises(ValidationError):
        SupportResponseCreate(body=" ")
    with pytest.raises(ValidationError):
        SupportTransition(expected_status_code="in_progress", status_code="done")


def test_member_list_and_detail_are_scoped_and_include_response_history():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(member, company)
    request = _request(member, contact)
    response_item = _support_response(request, member)
    list_db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(request, contact, company, member)]),
        _Result(rows=[(response_item, member.display_name)]),
    )

    with _client(list_db, member) as client:
        response = client.get(
            "/api/support-requests",
            params=[("q", " 합성 "), ("status_code", "in_progress")],
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": str(request.id),
                "customer_contact_id": str(contact.id),
                "customer_contact_name": contact.name,
                "customer_company_id": str(company.id),
                "customer_company_name": company.name,
                "assignee_member_id": str(member.id),
                "assignee_display_name": member.display_name,
                "title": request.title,
                "body": request.body,
                "is_urgent": True,
                "status_code": "in_progress",
                "registered_at": "2026-08-17T18:00:00+09:00",
                "responses": [
                    {
                        "id": str(response_item.id),
                        "support_request_id": str(request.id),
                        "responder_member_id": str(member.id),
                        "responder_display_name": member.display_name,
                        "body": response_item.body,
                        "responded_at": "2026-08-17T18:00:00+09:00",
                    }
                ],
            }
        ],
        "skip": 0,
        "limit": 30,
        "total": 1,
        "has_more": False,
        "next_skip": None,
    }
    for statement in list_db.statements[:2]:
        assert member.id in statement.compile().params.values()
        assert member.team_id in statement.compile().params.values()
        assert "%합성%" in statement.compile().params.values()
    assert member.team_id in list_db.statements[2].compile().params.values()

    detail_db = _Db(
        _Result(rows=[_row(request, contact, company, member)]),
        _Result(rows=[(response_item, member.display_name)]),
    )
    with _client(detail_db, member) as client:
        detail = client.get(f"/api/support-requests/{request.id}")
    assert detail.status_code == 200
    assert detail.json()["responses"][0]["body"] == response_item.body


def test_manager_reads_team_request_without_member_self_filter():
    manager = _member(role="manager")
    assignee = _member(team_id=manager.team_id)
    company = _company(manager.team_id)
    contact = _contact(assignee, company)
    request = _request(assignee, contact)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(request, contact, company, assignee)]),
        _Result(rows=[]),
    )

    with _client(db, manager) as client:
        response = client.get("/api/support-requests")

    assert response.status_code == 200
    assert response.json()["items"][0]["assignee_member_id"] == str(assignee.id)
    assert manager.id not in db.statements[0].compile().params.values()


def test_create_uses_visible_contact_and_current_member_as_assignee():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(member, company)
    db = _Db(_Result(rows=[(contact, company)]))

    with _client(db, member) as client:
        response = client.post(
            "/api/support-requests",
            headers={"Origin": ORIGIN},
            json=_payload(contact, status_code="completed"),
        )

    assert response.status_code == 201
    data = response.json()
    assert data["assignee_member_id"] == str(member.id)
    assert data["status_code"] == "completed"
    assert data["title"] == "합성 문의"
    assert data["responses"] == []
    assert response.headers["location"] == f"/api/support-requests/{data['id']}"
    created = db.added[0]
    assert isinstance(created, SupportRequest)
    assert created.team_id == member.team_id
    assert created.assignee_member_id == member.id
    assert member.id in db.statements[0].compile().params.values()
    assert db.flush_count == db.commit_count == 1
    assert db.rollback_count == 0

    hidden_db = _Db(_Result(rows=[]))
    with _client(hidden_db, member) as client:
        hidden = client.post(
            "/api/support-requests",
            headers={"Origin": ORIGIN},
            json=_payload(contact),
        )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "customer_contact_not_found"}
    assert hidden_db.added == []
    assert hidden_db.commit_count == 0
    assert hidden_db.rollback_count == 1


def test_transition_uses_stale_guard_and_rejects_noop():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(member, company)
    request = _request(member, contact)
    db = _Db(
        _Result(scalar=request),
        _Result(rows=[_row(request, contact, company, member)]),
        _Result(rows=[]),
    )

    with _client(db, member) as client:
        response = client.post(
            f"/api/support-requests/{request.id}/transition",
            headers={"Origin": ORIGIN},
            json={"expected_status_code": "in_progress", "status_code": "completed"},
        )

    assert response.status_code == 200
    assert response.json()["status_code"] == "completed"
    assert "FOR UPDATE" in str(db.statements[0])
    assert db.flush_count == db.commit_count == 1

    for payload in (
        {"expected_status_code": "completed", "status_code": "in_progress"},
        {"expected_status_code": "in_progress", "status_code": "in_progress"},
    ):
        current = _request(member, contact)
        stale_db = _Db(_Result(scalar=current))
        with _client(stale_db, member) as client:
            stale = client.post(
                f"/api/support-requests/{current.id}/transition",
                headers={"Origin": ORIGIN},
                json=payload,
            )
        assert stale.status_code == 409
        assert stale.json() == {"detail": "invalid_state_transition"}
        assert stale_db.flush_count == stale_db.commit_count == 0
        assert stale_db.rollback_count == 1


def test_response_creation_uses_current_member_and_hides_invisible_request():
    manager = _member(role="manager")
    assignee = _member(team_id=manager.team_id)
    company = _company(manager.team_id)
    contact = _contact(assignee, company)
    request = _request(assignee, contact)
    db = _Db(_Result(scalar=request))

    with _client(db, manager) as client:
        response = client.post(
            f"/api/support-requests/{request.id}/responses",
            headers={"Origin": ORIGIN},
            json={"body": " 합성 처리 답변 "},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["support_request_id"] == str(request.id)
    assert data["responder_member_id"] == str(manager.id)
    assert data["responder_display_name"] == manager.display_name
    assert data["body"] == "합성 처리 답변"
    assert data["responded_at"] == "2026-08-17T18:00:00+09:00"
    assert response.headers["location"].endswith(f"/responses/{data['id']}")
    assert isinstance(db.added[0], SupportResponse)
    assert db.flush_count == db.commit_count == 1

    hidden_db = _Db(_Result(scalar=None))
    with _client(hidden_db, manager) as client:
        hidden = client.post(
            f"/api/support-requests/{uuid4()}/responses",
            headers={"Origin": ORIGIN},
            json={"body": "합성 답변"},
        )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "support_request_not_found"}
    assert hidden_db.added == []
    assert hidden_db.rollback_count == 1


def test_manager_support_assignee_filter_narrows_to_the_chosen_members():
    manager = _member(role="manager")
    first = _member(team_id=manager.team_id)
    second = _member(team_id=manager.team_id)
    db = _Db(
        _Result(scalar_values=[first.id, second.id]),
        _Result(scalar=0),
        _Result(rows=[]),
    )

    with _client(db, manager) as client:
        response = client.get(
            "/api/support-requests",
            params={"assignee_member_id": [str(first.id), str(second.id)]},
        )

    assert response.status_code == 200
    # 첫 문장은 범위 검증이고, 그 다음이 개수와 목록이다.
    assert [first.id, second.id] in db.statements[1].compile().params.values()


def test_member_support_assignee_filter_is_denied_before_any_query():
    member = _member()
    db = _Db()

    with _client(db, member) as client:
        response = client.get(
            "/api/support-requests",
            params={"assignee_member_id": [str(uuid4())]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "scope_not_allowed"
    assert not db.statements


def test_manager_support_assignee_filter_rejects_a_member_outside_the_team():
    manager = _member(role="manager")
    db = _Db(_Result(scalar_values=[]))

    with _client(db, manager) as client:
        response = client.get(
            "/api/support-requests",
            params={"assignee_member_id": [str(uuid4())]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "scope_not_allowed"
    assert len(db.statements) == 1
