from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.configuration import CustomerContactStatus
from app.models.crm import CustomerCompany, CustomerContact
from app.models.workspace import Member
from app.schemas.customers import (
    CustomerCompanyCreate,
    CustomerCompanyPatch,
    CustomerContactCreate,
    CustomerContactPatch,
    CustomerPageParams,
)

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
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
            if isinstance(value, CustomerCompany) and value.created_at is None:
                value.created_at = NOW
            if isinstance(value, CustomerContact) and value.registered_at is None:
                value.registered_at = NOW

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
        login_id=f"{uuid4()}@salesluv.demo",
        password_hash="unused",
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _company(team_id: UUID, *, company_id: UUID | None = None) -> CustomerCompany:
    return CustomerCompany(
        id=company_id or uuid4(),
        team_id=team_id,
        name="합성 고객사",
        region_code="seoul",
        created_at=NOW,
    )


def _contact(company_id: UUID, owner_id: UUID) -> CustomerContact:
    return CustomerContact(
        id=uuid4(),
        company_id=company_id,
        owner_member_id=owner_id,
        name="합성 고객",
        department="영업부",
        job_title="팀장",
        email="customer@demo.test",
        phone="02-000-0000",
        customer_contact_status_id=uuid4(),
        source_code="referral",
        memo="합성 메모",
        registered_at=NOW,
    )


def _contact_status(
    team_id: UUID,
    *,
    status_id: UUID | None = None,
    code: str = "negotiation",
    deleted_at: datetime | None = None,
) -> CustomerContactStatus:
    return CustomerContactStatus(
        id=status_id or uuid4(),
        team_id=team_id,
        code=code,
        name="협상",
        tone="amber",
        position=2,
        deleted_at=deleted_at,
        created_at=NOW,
        updated_at=NOW,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_customer_request_sales_deal_trims_and_rejects_invalid_values():
    company = CustomerCompanyCreate(name="  합성 고객사  ", region_code="  seoul ")
    contact = CustomerContactCreate(
        company_id=uuid4(),
        name="  합성 고객  ",
        email="  customer@demo.test ",
        phone="  02-000-0000  ",
        status_code="new",
        source_code="website",
    )

    assert company.model_dump() == {"name": "합성 고객사", "region_code": "seoul"}
    assert contact.name == "합성 고객"
    assert contact.email == "customer@demo.test"
    assert contact.phone == "02-000-0000"
    assert (
        CustomerContactCreate(
            company_id=uuid4(),
            name="합성 고객",
            phone="02-000-0000",
            status_code="custom_status",
        ).status_code
        == "custom_status"
    )
    assert CustomerCompanyPatch(region_code=None).model_dump(exclude_unset=True) == {
        "region_code": None
    }
    assert CustomerContactPatch(memo=None).model_dump(exclude_unset=True) == {"memo": None}
    assert CustomerPageParams(q="  합성 고객  ").q == "합성 고객"

    with pytest.raises(ValidationError):
        CustomerCompanyCreate(name="합성 고객사", team_id=uuid4())
    with pytest.raises(ValidationError):
        CustomerCompanyPatch(name=None)
    with pytest.raises(ValidationError):
        CustomerContactCreate(
            company_id=uuid4(),
            name="합성 고객",
            email="not-an-email",
            phone=" ",
            status_code="신규",
        )
    with pytest.raises(ValidationError):
        CustomerContactPatch(company_id=None)
    with pytest.raises(ValidationError):
        CustomerPageParams(q=" ")
    with pytest.raises(ValidationError):
        CustomerPageParams(q="x" * 101)


def test_company_create_uses_authenticated_team_and_explicit_transaction():
    member = _member()
    db = _Db()

    with _client(db, member) as client:
        response = client.post(
            "/api/customer-companies",
            headers={"Origin": ORIGIN},
            json={"name": "  합성 고객사  ", "region_code": "seoul"},
        )

    assert response.status_code == 201
    assert response.json()["team_id"] == str(member.team_id)
    assert response.json()["name"] == "합성 고객사"
    assert response.headers["location"] == f"/api/customer-companies/{response.json()['id']}"
    assert db.added[0].team_id == member.team_id
    assert db.flush_count == db.commit_count == 1
    assert db.rollback_count == 0


def test_company_create_reuses_same_team_name_after_unique_conflict():
    member = _member()
    existing = _company(member.team_id)
    db = _Db(
        _Result(scalar=existing),
        flush_error=IntegrityError("insert", {}, RuntimeError("duplicate")),
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/customer-companies",
            headers={"Origin": ORIGIN},
            json={"name": existing.name, "region_code": "seoul"},
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(existing.id)
    assert response.headers["location"] == f"/api/customer-companies/{existing.id}"
    assert db.commit_count == 0
    assert db.rollback_count == 1


def test_company_patch_requires_manager_and_other_team_is_hidden():
    member = _member()
    member_db = _Db()
    with _client(member_db, member) as client:
        forbidden = client.patch(
            f"/api/customer-companies/{uuid4()}",
            headers={"Origin": ORIGIN},
            json={"name": "변경"},
        )

    manager = _member(role="manager")
    manager_db = _Db(_Result(scalar=None))
    with _client(manager_db, manager) as client:
        hidden = client.patch(
            f"/api/customer-companies/{uuid4()}",
            headers={"Origin": ORIGIN},
            json={"name": "변경"},
        )

    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "manager_required"}
    assert not member_db.statements
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "customer_company_not_found"}
    assert manager_db.commit_count == 0


def test_company_list_detail_and_manager_patch_share_team_scope():
    manager = _member(role="manager")
    company = _company(manager.team_id)
    db = _Db(
        _Result(scalar=1),
        _Result(scalar_values=[company]),
        _Result(scalar=company),
        _Result(scalar=company),
    )

    with _client(db, manager) as client:
        listed = client.get("/api/customer-companies", params={"q": "  합성  "})
        detail = client.get(f"/api/customer-companies/{company.id}")
        updated = client.patch(
            f"/api/customer-companies/{company.id}",
            headers={"Origin": ORIGIN},
            json={"region_code": None},
        )

    assert listed.status_code == detail.status_code == updated.status_code == 200
    assert listed.json()["items"][0]["id"] == str(company.id)
    assert detail.json()["name"] == company.name
    assert updated.json()["region_code"] is None
    assert db.flush_count == db.commit_count == 1
    for statement in db.statements:
        assert manager.team_id in statement.compile().params.values()
    for statement in db.statements[:2]:
        assert "%합성%" in statement.compile().params.values()


def test_contact_create_uses_current_owner_and_join_fields():
    member = _member()
    company = _company(member.team_id)
    contact_status = _contact_status(member.team_id, code="proposal")
    db = _Db(_Result(scalar=company), _Result(scalar=contact_status))

    with _client(db, member) as client:
        response = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "email": "customer@demo.test",
                "phone": "02-000-0000",
                "status_code": "proposal",
                "source_code": "referral",
            },
        )

    assert response.status_code == 201
    assert response.json()["owner_member_id"] == str(member.id)
    assert response.json()["company_name"] == company.name
    assert response.json()["company_region_code"] == company.region_code
    assert response.json()["owner_display_name"] == member.display_name
    assert response.json()["customer_contact_status_id"] == str(contact_status.id)
    assert response.json()["customer_contact_status_name"] == contact_status.name
    assert response.json()["customer_contact_status_tone"] == contact_status.tone
    assert response.headers["location"] == f"/api/customer-contacts/{response.json()['id']}"
    assert db.added[0].owner_member_id == member.id
    assert db.added[0].customer_contact_status_id == contact_status.id
    assert db.flush_count == db.commit_count == 1
    assert member.team_id in db.statements[0].compile().params.values()


def test_contact_list_is_owner_scoped_for_member_and_returns_join_fields():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    contact_status = _contact_status(
        member.team_id,
        status_id=contact.customer_contact_status_id,
        deleted_at=NOW,
    )
    db = _Db(
        _Result(scalar=1),
        _Result(
            rows=[
                (
                    contact,
                    company.name,
                    company.region_code,
                    member.display_name,
                    contact_status,
                )
            ]
        ),
    )

    with _client(db, member) as client:
        response = client.get(
            "/api/customer-contacts",
            params={"q": "  합성  ", "skip": 0, "limit": 30},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["company_name"] == company.name
    assert response.json()["items"][0]["owner_display_name"] == member.display_name
    assert response.json()["items"][0]["status_code"] == "negotiation"
    assert response.json()["items"][0]["customer_contact_status_name"] == "협상"
    assert response.json()["next_skip"] is None
    for statement in db.statements:
        assert member.id in statement.compile().params.values()
        assert list(statement.compile().params.values()).count("%합성%") == 6
        sql = str(statement)
        assert "public.member.active IS true" in sql
        assert "public.member.role_code IN" in sql
        assert "customer_contact_status.deleted_at IS NULL" not in sql
    assert "customer_contact_status.team_id =" in str(db.statements[1])


def test_manager_contact_list_and_detail_cover_the_whole_team():
    manager = _member(role="manager")
    company = _company(manager.team_id)
    other_owner = _member(team_id=manager.team_id)
    contact = _contact(company.id, other_owner.id)
    contact_status = _contact_status(
        manager.team_id,
        status_id=contact.customer_contact_status_id,
    )
    row = (
        contact,
        company.name,
        company.region_code,
        other_owner.display_name,
        contact_status,
    )
    db = _Db(_Result(scalar=1), _Result(rows=[row]), _Result(rows=[row]))

    with _client(db, manager) as client:
        listed = client.get("/api/customer-contacts")
        detail = client.get(f"/api/customer-contacts/{contact.id}")

    assert listed.status_code == detail.status_code == 200
    assert listed.json()["items"][0]["owner_member_id"] == str(other_owner.id)
    assert detail.json()["owner_display_name"] == other_owner.display_name
    for statement in db.statements:
        assert manager.team_id in statement.compile().params.values()
        assert manager.id not in statement.compile().params.values()
        sql = str(statement)
        assert "public.member.active IS true" in sql
        assert "public.member.role_code IN" in sql


def test_contact_patch_revalidates_destination_company_team():
    manager = _member(role="manager")
    old_company = _company(manager.team_id)
    new_company = _company(manager.team_id)
    contact = _contact(old_company.id, manager.id)
    contact_status = _contact_status(
        manager.team_id,
        status_id=contact.customer_contact_status_id,
    )
    db = _Db(
        _Result(
            rows=[
                (
                    contact,
                    old_company.name,
                    old_company.region_code,
                    manager.display_name,
                    contact_status,
                )
            ]
        ),
        _Result(scalar=new_company),
    )

    with _client(db, manager) as client:
        response = client.patch(
            f"/api/customer-contacts/{contact.id}",
            headers={"Origin": ORIGIN},
            json={"company_id": str(new_company.id), "memo": None},
        )

    assert response.status_code == 200
    assert response.json()["company_id"] == str(new_company.id)
    assert response.json()["company_name"] == new_company.name
    assert response.json()["memo"] is None
    assert contact.company_id == new_company.id
    assert db.flush_count == db.commit_count == 1
    assert manager.team_id in db.statements[1].compile().params.values()


def test_contact_status_write_resolves_only_active_same_team_lookup():
    member = _member()
    company = _company(member.team_id)
    create_db = _Db(_Result(scalar=company), _Result(scalar=None))
    with _client(create_db, member) as client:
        other_team = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "phone": "02-000-0000",
                "status_code": "other_team_status",
            },
        )

    contact = _contact(company.id, member.id)
    contact_status = _contact_status(
        member.team_id,
        status_id=contact.customer_contact_status_id,
    )
    patch_db = _Db(
        _Result(
            rows=[
                (
                    contact,
                    company.name,
                    company.region_code,
                    member.display_name,
                    contact_status,
                )
            ]
        ),
        _Result(scalar=None),
    )
    with _client(patch_db, member) as client:
        deleted = client.patch(
            f"/api/customer-contacts/{contact.id}",
            headers={"Origin": ORIGIN},
            json={"status_code": "deleted_status"},
        )

    assert other_team.status_code == deleted.status_code == 422
    assert (
        other_team.json() == deleted.json() == {"detail": "customer_contact_status_code_not_found"}
    )
    for statement, code in (
        (create_db.statements[1], "other_team_status"),
        (patch_db.statements[1], "deleted_status"),
    ):
        sql = str(statement)
        values = statement.compile().params.values()
        assert "customer_contact_status.deleted_at IS NULL" in sql
        assert member.team_id in values
        assert code in values


def test_contact_status_options_are_active_same_team_and_ordered():
    member = _member()
    contact_status = _contact_status(member.team_id, code="custom_status")
    db = _Db(_Result(scalar_values=[contact_status]))

    with _client(db, member) as client:
        response = client.get("/api/customer-contact-statuses")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(contact_status.id),
            "code": contact_status.code,
            "name": contact_status.name,
            "tone": contact_status.tone,
            "position": contact_status.position,
        }
    ]
    statement = db.statements[0]
    sql = str(statement)
    assert "customer_contact_status.deleted_at IS NULL" in sql
    assert "ORDER BY public.customer_contact_status.position" in sql
    assert member.team_id in statement.compile().params.values()


def test_cross_team_contact_detail_is_hidden_and_unknown_query_is_rejected():
    member = _member()
    detail_db = _Db(_Result(rows=[]))
    with _client(detail_db, member) as client:
        hidden = client.get(f"/api/customer-contacts/{uuid4()}")

    query_db = _Db()
    with _client(query_db, member) as client:
        invalid_query = client.get("/api/customer-companies?unknown=true")

    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "customer_contact_not_found"}
    assert invalid_query.status_code == 422
    assert not query_db.statements


def test_write_failure_rolls_back_transaction():
    member = _member()
    db = _Db(flush_error=RuntimeError("synthetic failure"))

    with _client(db, member) as client, pytest.raises(RuntimeError, match="synthetic failure"):
        client.post(
            "/api/customer-companies",
            headers={"Origin": ORIGIN},
            json={"name": "합성 고객사"},
        )

    assert db.commit_count == 0
    assert db.rollback_count == 1
