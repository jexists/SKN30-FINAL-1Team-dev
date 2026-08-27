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
from app.models.crm import CustomerCompany, CustomerContact, CustomerContactAssignee
from app.models.workspace import Member
from app.schemas.customers import (
    CustomerCompanyCreate,
    CustomerCompanyPatch,
    CustomerContactCreate,
    CustomerContactPatch,
    CustomerContactRead,
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


def _contact(
    company_id: UUID,
    owner_id: UUID,
    *,
    created_by_id: UUID | None = None,
) -> CustomerContact:
    return CustomerContact(
        id=uuid4(),
        company_id=company_id,
        owner_member_id=owner_id,
        created_by_member_id=created_by_id or owner_id,
        name="합성 고객",
        department="영업부",
        job_title="팀장",
        email="customer@demo.test",
        phone="02-000-0000",
        customer_contact_status_id=uuid4(),
        source_code="referral",
        memo="합성 메모",
        visited=False,
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


def _contact_row(
    contact: CustomerContact,
    company: CustomerCompany,
    owner: Member,
    contact_status: CustomerContactStatus | None,
    creator: Member | None = None,
) -> tuple:
    """목록·상세 쿼리가 돌려주는 조인 행. 마지막 칸이 등록한 사람의 이름이다."""
    return (
        contact,
        company.name,
        company.region_code,
        owner.display_name,
        contact_status,
        (creator or owner).display_name,
    )


def _assignee_result(*pairs: tuple[CustomerContact, Member]) -> _Result:
    """_load_assignees 가 읽는 (고객 id, 담당자 id, 담당자 이름) 행."""
    return _Result(
        rows=[(contact.id, assignee.id, assignee.display_name) for contact, assignee in pairs]
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

    assert company.model_dump() == {
        "name": "합성 고객사",
        "region_code": "seoul",
        "business_no": None,
        "postcode": None,
        "address": None,
        "address_detail": None,
    }
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
    # 방문 여부를 보내지 않았다. 아직 만나기 전이므로 미방문에서 시작해야 한다.
    assert response.json()["visited"] is False
    assert db.added[0].visited is False
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
        _Result(rows=[_contact_row(contact, company, member, contact_status)]),
        _assignee_result((contact, member)),
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
    assert [row["id"] for row in response.json()["items"][0]["assignees"]] == [str(member.id)]
    assert response.json()["items"][0]["created_by_display_name"] == member.display_name
    # 마지막 문장은 담당자만 읽는 별도 질의라 검색어·스코프 조건이 없다.
    for statement in db.statements[:2]:
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
    row = _contact_row(contact, company, other_owner, contact_status)
    assignees = _assignee_result((contact, other_owner))
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[row]),
        assignees,
        _Result(rows=[row]),
        _assignee_result((contact, other_owner)),
    )

    with _client(db, manager) as client:
        listed = client.get("/api/customer-contacts")
        detail = client.get(f"/api/customer-contacts/{contact.id}")

    assert listed.status_code == detail.status_code == 200
    assert listed.json()["items"][0]["owner_member_id"] == str(other_owner.id)
    assert detail.json()["owner_display_name"] == other_owner.display_name
    for statement in (db.statements[0], db.statements[1], db.statements[3]):
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
        _Result(rows=[_contact_row(contact, old_company, manager, contact_status)]),
        _assignee_result((contact, manager)),
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
    assert manager.team_id in db.statements[2].compile().params.values()


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
        _Result(rows=[_contact_row(contact, company, member, contact_status)]),
        _assignee_result((contact, member)),
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
        (patch_db.statements[2], "deleted_status"),
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


def test_contact_create_records_creator_and_defaults_assignee_to_self():
    member = _member()
    company = _company(member.team_id)
    db = _Db(_Result(scalar=company))

    with _client(db, member) as client:
        response = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "phone": "02-000-0000",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["owner_member_id"] == body["created_by_member_id"] == str(member.id)
    assert body["assignees"] == [{"id": str(member.id), "display_name": member.display_name}]
    # 담당자를 안 보내면 팀원 목록을 읽을 이유가 없다.
    assert len(db.statements) == 1
    assignee_rows = [row for row in db.added if isinstance(row, CustomerContactAssignee)]
    assert [row.member_id for row in assignee_rows] == [member.id]
    assert assignee_rows[0].customer_contact_id == db.added[0].id


def test_manager_assigns_several_owners_and_first_one_becomes_representative():
    manager = _member(role="manager")
    company = _company(manager.team_id)
    first = _member(team_id=manager.team_id)
    first.display_name = "합성 담당자 가"
    second = _member(team_id=manager.team_id)
    second.display_name = "합성 담당자 나"
    db = _Db(_Result(scalar=company), _Result(scalar_values=[second, first]))

    with _client(db, manager) as client:
        response = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "phone": "02-000-0000",
                # 중복은 지워지고 보낸 순서가 그대로 남는다.
                "assignee_member_ids": [str(first.id), str(second.id), str(first.id)],
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["owner_member_id"] == str(first.id)
    assert body["owner_display_name"] == first.display_name
    # 등록한 사람은 담당자가 아니어도 남는다.
    assert body["created_by_member_id"] == str(manager.id)
    assert [row["id"] for row in body["assignees"]] == [str(first.id), str(second.id)]
    assignee_rows = [row for row in db.added if isinstance(row, CustomerContactAssignee)]
    assert [row.member_id for row in assignee_rows] == [first.id, second.id]
    lookup = db.statements[1]
    assert manager.team_id in lookup.compile().params.values()
    assert "public.member.active IS true" in str(lookup)


def test_member_may_only_assign_themselves():
    member = _member()
    company = _company(member.team_id)
    other = _member(team_id=member.team_id)

    forbidden_db = _Db(_Result(scalar=company))
    with _client(forbidden_db, member) as client:
        forbidden = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "phone": "02-000-0000",
                "assignee_member_ids": [str(other.id)],
            },
        )

    allowed_db = _Db(_Result(scalar=company), _Result(scalar_values=[member]))
    with _client(allowed_db, member) as client:
        allowed = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "phone": "02-000-0000",
                "assignee_member_ids": [str(member.id)],
            },
        )

    assert forbidden.status_code == 403
    assert forbidden.json() == {"detail": "manager_required"}
    # 막혔으면 아무것도 남기지 않는다.
    assert forbidden_db.added == []
    assert allowed.status_code == 201


def test_assignees_must_exist_in_the_team_and_cannot_be_empty():
    manager = _member(role="manager")
    company = _company(manager.team_id)
    stranger = _member()

    missing_db = _Db(_Result(scalar=company), _Result(scalar_values=[]))
    with _client(missing_db, manager) as client:
        missing = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "phone": "02-000-0000",
                "assignee_member_ids": [str(stranger.id)],
            },
        )

    empty_db = _Db(_Result(scalar=company))
    with _client(empty_db, manager) as client:
        empty = client.post(
            "/api/customer-contacts",
            headers={"Origin": ORIGIN},
            json={
                "company_id": str(company.id),
                "name": "합성 고객",
                "phone": "02-000-0000",
                "assignee_member_ids": [],
            },
        )

    assert missing.status_code == empty.status_code == 422
    assert missing.json() == {"detail": "assignee_member_not_found"}
    assert empty.json() == {"detail": "assignee_required"}


def test_contact_patch_replaces_assignees_and_refreshes_owner_name():
    manager = _member(role="manager")
    company = _company(manager.team_id)
    old_owner = _member(team_id=manager.team_id)
    old_owner.display_name = "합성 이전 담당자"
    new_owner = _member(team_id=manager.team_id)
    new_owner.display_name = "합성 새 담당자"
    contact = _contact(company.id, old_owner.id, created_by_id=manager.id)
    contact_status = _contact_status(manager.team_id, status_id=contact.customer_contact_status_id)
    db = _Db(
        _Result(rows=[_contact_row(contact, company, old_owner, contact_status, manager)]),
        _assignee_result((contact, old_owner)),
        _Result(scalar_values=[new_owner]),
        _Result(),
    )

    with _client(db, manager) as client:
        response = client.patch(
            f"/api/customer-contacts/{contact.id}",
            headers={"Origin": ORIGIN},
            json={"assignee_member_ids": [str(new_owner.id)]},
        )

    assert response.status_code == 200
    body = response.json()
    assert contact.owner_member_id == new_owner.id
    # 갱신 전 조인 값이 아니라 새 담당자의 이름이 나가야 한다.
    assert body["owner_display_name"] == new_owner.display_name
    assert [row["id"] for row in body["assignees"]] == [str(new_owner.id)]
    # 등록한 사람은 담당자를 바꿔도 그대로다.
    assert body["created_by_member_id"] == str(manager.id)
    assert body["created_by_display_name"] == manager.display_name
    assert "DELETE FROM public.customer_contact_assignee" in str(db.statements[3])
    assignee_rows = [row for row in db.added if isinstance(row, CustomerContactAssignee)]
    assert [row.member_id for row in assignee_rows] == [new_owner.id]


def test_contact_scope_lets_a_member_see_customers_they_are_assigned_to():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, uuid4())
    contact_status = _contact_status(member.team_id, status_id=contact.customer_contact_status_id)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_contact_row(contact, company, member, contact_status)]),
        _assignee_result((contact, member)),
    )

    with _client(db, member) as client:
        response = client.get("/api/customer-contacts")

    assert response.status_code == 200
    sql = str(db.statements[0])
    assert "customer_contact_assignee" in sql
    assert "EXISTS" in sql


def test_company_write_round_trips_business_no_and_rejects_other_shapes():
    member = _member()
    db = _Db()

    with _client(db, member) as client:
        created = client.post(
            "/api/customer-companies",
            headers={"Origin": ORIGIN},
            json={"name": "합성 고객사", "region_code": None, "business_no": " 1234567890 "},
        )
        rejected = client.post(
            "/api/customer-companies",
            headers={"Origin": ORIGIN},
            json={"name": "합성 고객사", "business_no": "123-45-67890"},
        )

    assert created.status_code == 201
    assert created.json()["business_no"] == "1234567890"
    assert db.added[0].business_no == "1234567890"
    assert rejected.status_code == 422


def test_manager_contact_owner_filter_covers_owner_and_assignees():
    """팀장이 고른 팀원의 고객에는 그 팀원이 담당자로만 지정된 고객도 들어간다."""
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    company = _company(manager.team_id)
    contact = _contact(company.id, teammate.id)
    contact_status = _contact_status(manager.team_id, status_id=contact.customer_contact_status_id)
    db = _Db(
        _Result(scalar_values=[teammate.id]),
        _Result(scalar=1),
        _Result(rows=[_contact_row(contact, company, teammate, contact_status)]),
        _assignee_result((contact, teammate)),
    )

    with _client(db, manager) as client:
        response = client.get(
            "/api/customer-contacts",
            params={"owner_member_id": [str(teammate.id)]},
        )

    assert response.status_code == 200
    # 첫 문장은 범위 검증이고, 그 다음이 개수와 목록이다.
    sql = str(db.statements[1])
    assert "customer_contact_assignee" in sql
    assert "EXISTS" in sql
    assert teammate.id in db.statements[1].compile().params.values()


def test_manager_contact_owner_filter_uses_in_for_several_members():
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
            "/api/customer-contacts",
            params={"owner_member_id": [str(first.id), str(second.id)]},
        )

    assert response.status_code == 200
    params = db.statements[1].compile().params.values()
    assert [first.id, second.id] in params


def test_contact_list_narrows_to_one_company():
    """일정 모달은 고른 고객사의 담당자만 부른다. 회사명 검색 뒤 화면에서 거르면
    한 페이지 안에 다 들어오지 않은 사람이 조용히 빠진다."""
    manager = _member(role="manager")
    company = _company(manager.team_id)
    contact = _contact(company.id, manager.id)
    contact_status = _contact_status(manager.team_id, status_id=contact.customer_contact_status_id)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_contact_row(contact, company, manager, contact_status)]),
        _assignee_result((contact, manager)),
    )

    with _client(db, manager) as client:
        response = client.get(
            "/api/customer-contacts",
            params={"company_id": str(company.id)},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["company_id"] == str(company.id)
    # 개수와 목록이 같은 범위를 써야 has_more 가 어긋나지 않는다.
    for statement in (db.statements[0], db.statements[1]):
        assert "public.customer_contact.company_id = " in str(statement)
        assert company.id in statement.compile().params.values()


def test_member_contact_owner_filter_is_denied_before_any_query():
    member = _member()
    db = _Db()

    with _client(db, member) as client:
        response = client.get(
            "/api/customer-contacts",
            params={"owner_member_id": [str(uuid4())]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "scope_not_allowed"
    assert not db.statements


def test_manager_contact_owner_filter_rejects_a_member_outside_the_team():
    manager = _member(role="manager")
    db = _Db(_Result(scalar_values=[]))

    with _client(db, manager) as client:
        response = client.get(
            "/api/customer-contacts",
            params={"owner_member_id": [str(uuid4())]},
        )

    # 빈 목록이 아니라 거절이다. 조용히 비우면 화면은 "실적 0" 으로 읽는다.
    assert response.status_code == 403
    assert response.json()["detail"] == "scope_not_allowed"
    assert len(db.statements) == 1


def test_company_list_does_not_take_an_owner_filter():
    """회사는 팀 공용이라 담당자가 없다. 받고도 무시하지 않고 거절해야 한다."""
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.get(
            "/api/customer-companies",
            params={"owner_member_id": [str(uuid4())]},
        )

    assert response.status_code == 422
    assert not db.statements


def test_manager_contact_owner_filter_accepts_the_manager_themselves():
    """'내 현황 + 팀원' 을 함께 보는 경우다. 팀장 자신도 같은 팀의 활성 구성원이다."""
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    db = _Db(
        _Result(scalar_values=[manager.id, teammate.id]),
        _Result(scalar=0),
        _Result(rows=[]),
    )

    with _client(db, manager) as client:
        response = client.get(
            "/api/customer-contacts",
            params={"owner_member_id": [str(manager.id), str(teammate.id)]},
        )

    assert response.status_code == 200
    assert [manager.id, teammate.id] in db.statements[1].compile().params.values()


def _contact_read_payload(**overrides):
    payload = {
        "id": uuid4(),
        "company_id": uuid4(),
        "owner_member_id": uuid4(),
        "name": "김담당",
        "department": None,
        "job_title": None,
        "email": None,
        "phone": "010-0000-0000",
        "customer_contact_status_id": None,
        "customer_contact_status_name": None,
        "customer_contact_status_tone": None,
        "status_code": None,
        "source_code": None,
        "memo": None,
        "visited": False,
        "registered_at": NOW,
        "company_name": "한빛대학교병원",
        "company_region_code": None,
        "owner_display_name": "박영업",
        "created_by_member_id": uuid4(),
        "created_by_display_name": "박영업",
        "assignees": [],
    }
    return payload | overrides


def test_unknown_source_code_does_not_break_the_list():
    """컬럼이 자유 문자열이라 이 앱이 쓰지 않은 값이 들어 있을 수 있다.

    내보내는 쪽을 Literal 로 묶으면 그런 행 하나 때문에 목록 전체가 500 이 된다.
    한 사람 몫이 안 보이는 것과 목록이 통째로 안 열리는 것은 무게가 다르다.
    """
    read = CustomerContactRead(**_contact_read_payload(source_code="manual"))
    assert read.source_code == "manual"


def test_write_still_rejects_an_unknown_source_code():
    """읽기를 열어 준 것이지 아무 값이나 받아 준다는 뜻은 아니다."""
    with pytest.raises(ValidationError):
        CustomerContactCreate(
            company_id=uuid4(),
            name="김담당",
            phone="010-0000-0000",
            source_code="manual",
        )
