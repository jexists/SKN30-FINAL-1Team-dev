from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.crm import CustomerCompany, CustomerContact
from app.models.sales import Contract, PipelineStage, Product
from app.models.workspace import Member
from app.schemas.contracts import (
    ContractCreate,
    ContractMove,
    ContractPageParams,
    ContractPatch,
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
            if isinstance(value, Contract):
                value.created_at = value.created_at or NOW
                value.updated_at = value.updated_at or NOW

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


def _company(team_id: UUID) -> CustomerCompany:
    return CustomerCompany(
        id=uuid4(),
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
        department="구매팀",
        job_title="팀장",
        email=None,
        phone="02-000-0000",
        status_code=None,
        source_code=None,
        memo=None,
        registered_at=NOW,
    )


def _product(team_id: UUID) -> Product:
    return Product(id=uuid4(), team_id=team_id, name="합성 상품", active=True)


def _stage(
    team_id: UUID,
    *,
    name: str = "니즈 검증",
    outcome: str = "in_progress",
    position: int = 0,
) -> PipelineStage:
    return PipelineStage(
        id=uuid4(),
        team_id=team_id,
        name=name,
        tone="green" if outcome == "confirmed" else "gray",
        outcome_code=outcome,
        position=position,
    )


def _contract(
    member: Member,
    company: CustomerCompany,
    product: Product,
    stage: PipelineStage,
    *,
    position: int = 0,
    contract_no: str = "SL-CT-2026-0001",
) -> Contract:
    return Contract(
        id=uuid4(),
        team_id=member.team_id,
        contract_no=contract_no,
        customer_company_id=company.id,
        contact_id=None,
        owner_member_id=member.id,
        product_id=product.id,
        stage_id=stage.id,
        title="합성 고객사 합성 상품",
        description=None,
        contract_type="new_installation",
        amount=10_000_000,
        contract_date=date(2026, 8, 17),
        ends_on=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo="합성 메모",
        position=position,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _row(
    contract: Contract,
    owner: Member,
    company: CustomerCompany,
    product: Product,
    stage: PipelineStage,
    contact: CustomerContact | None = None,
):
    return (
        contract,
        owner.display_name,
        company.name,
        company.region_code,
        None if contact is None else contact.name,
        product.name,
        stage.name,
        stage.tone,
        stage.outcome_code,
        stage.position,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_contract_request_contract_is_strict_and_uses_snake_case_type_codes():
    payload = ContractCreate(
        customer_company_id=uuid4(),
        product_id=uuid4(),
        stage_id=uuid4(),
        contract_type="new_installation",
        amount=10_000_000,
        contract_date="2026-08-17",
    )

    assert payload.title is None
    type_codes = (
        "new_installation",
        "expansion",
        "renewal",
        "maintenance",
        "consumables_supply",
    )
    parsed_type_codes = tuple(
        ContractPatch(contract_type=code).contract_type for code in type_codes
    )
    assert parsed_type_codes == type_codes
    assert ContractPatch(memo=None).model_dump(exclude_unset=True) == {"memo": None}
    assert ContractPageParams(start_date="2026-08-17", end_date="2026-08-17")

    with pytest.raises(ValidationError):
        ContractCreate(
            customer_company_id=uuid4(),
            product_id=uuid4(),
            stage_id=uuid4(),
            contract_type="신규 도입",
            amount=1,
            contract_date="2026-08-17",
        )
    with pytest.raises(ValidationError):
        ContractCreate(**(payload.model_dump() | {"contract_no": "SL-CT-2026-0001"}))
    with pytest.raises(ValidationError):
        ContractCreate(**(payload.model_dump() | {"owner_member_id": uuid4()}))
    with pytest.raises(ValidationError):
        ContractPatch(product_id=None)
    with pytest.raises(ValidationError):
        ContractPatch(title=None)
    with pytest.raises(ValidationError):
        ContractMove(expected_stage_id=uuid4(), stage_id=uuid4(), position=1.5)
    with pytest.raises(ValidationError):
        ContractPageParams(start_date="2026-08-18", end_date="2026-08-17")


def test_pipeline_stages_and_products_are_active_team_scoped():
    member = _member()
    stage = _stage(member.team_id)
    product = _product(member.team_id)
    db = _Db(
        _Result(scalar_values=[stage]),
        _Result(scalar=1),
        _Result(scalar_values=[product]),
    )

    with _client(db, member) as client:
        stages = client.get("/api/pipeline-stages")
        products = client.get("/api/products", params={"q": "  합성  "})

    assert stages.status_code == products.status_code == 200
    assert stages.json() == [
        {
            "id": str(stage.id),
            "name": stage.name,
            "tone": stage.tone,
            "outcome_code": stage.outcome_code,
            "position": stage.position,
        }
    ]
    assert products.json()["items"][0]["id"] == str(product.id)
    assert products.json()["next_skip"] is None
    assert member.team_id in db.statements[0].compile().params.values()
    for statement in db.statements[1:]:
        sql = str(statement)
        assert "product.active IS true" in sql
        assert member.team_id in statement.compile().params.values()
        assert "%합성%" in statement.compile().params.values()

    invalid_db = _Db()
    with _client(invalid_db, member) as client:
        invalid = client.get("/api/pipeline-stages?unknown=true")
    assert invalid.status_code == 422
    assert not invalid_db.statements


def test_member_contract_list_is_owner_team_and_soft_delete_scoped():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    stage = _stage(member.team_id)
    contract = _contract(member, company, product, stage)
    db = _Db(_Result(scalar=1), _Result(rows=[_row(contract, member, company, product, stage)]))

    with _client(db, member) as client:
        response = client.get(
            "/api/contracts",
            params={
                "q": "  합성  ",
                "start_date": "2026-08-01",
                "end_date": "2026-08-31",
            },
        )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == str(contract.id)
    assert item["customer_company_name"] == company.name
    assert item["product_name"] == product.name
    assert item["owner_display_name"] == member.display_name
    assert item["stage_outcome_code"] == stage.outcome_code
    for statement in db.statements:
        sql = str(statement)
        assert "contract.deleted_at IS NULL" in sql
        assert member.id in statement.compile().params.values()
        assert member.team_id in statement.compile().params.values()
        assert list(statement.compile().params.values()).count("%합성%") == 7


def test_manager_contract_filters_validate_active_team_owners_and_stages():
    manager = _member(role="manager")
    owner = _member(team_id=manager.team_id)
    company = _company(manager.team_id)
    product = _product(manager.team_id)
    stage = _stage(manager.team_id)
    contract = _contract(owner, company, product, stage)
    db = _Db(
        _Result(scalar_values=[owner.id]),
        _Result(scalar_values=[stage.id]),
        _Result(scalar=1),
        _Result(rows=[_row(contract, owner, company, product, stage)]),
    )

    with _client(db, manager) as client:
        response = client.get(
            "/api/contracts",
            params=[
                ("owner_member_id", str(owner.id)),
                ("stage_id", str(stage.id)),
            ],
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["owner_member_id"] == str(owner.id)
    assert manager.id not in db.statements[2].compile().params.values()

    invalid_owner_db = _Db(_Result(scalar_values=[]))
    with _client(invalid_owner_db, manager) as client:
        invalid_owner = client.get(
            "/api/contracts",
            params={"owner_member_id": str(uuid4())},
        )
    assert invalid_owner.status_code == 403
    assert invalid_owner.json() == {"detail": "scope_not_allowed"}

    invalid_stage_db = _Db(_Result(scalar_values=[]))
    with _client(invalid_stage_db, manager) as client:
        invalid_stage = client.get(
            "/api/contracts",
            params={"stage_id": str(uuid4())},
        )
    assert invalid_stage.status_code == 404
    assert invalid_stage.json() == {"detail": "pipeline_stage_not_found"}


def test_member_cannot_request_owner_scope_and_cross_team_detail_is_hidden():
    member = _member()
    scope_db = _Db()
    with _client(scope_db, member) as client:
        denied = client.get(
            "/api/contracts",
            params={"owner_member_id": str(member.id)},
        )
    assert denied.status_code == 403
    assert denied.json() == {"detail": "scope_not_allowed"}
    assert not scope_db.statements

    detail_db = _Db(_Result(rows=[]))
    with _client(detail_db, member) as client:
        hidden = client.get(f"/api/contracts/{uuid4()}")
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "contract_not_found"}


def test_create_contract_uses_authenticated_owner_derives_title_and_places_first():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    stage = _stage(member.team_id)
    existing = _contract(member, company, product, stage, position=0, contract_no="OLD")
    db = _Db(
        _Result(scalar=company),
        _Result(scalar=product),
        _Result(scalar=stage),
        _Result(scalar=member.team_id),
        _Result(
            scalar_values=[
                "FM-CT-2026-9999",
                "SL-CT-2025-9999",
                "SL-CT-2026-0003",
                "SL-CT-2026-nope",
                "SL-CT-2026-10000",
            ]
        ),
        _Result(scalar_values=[existing]),
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/contracts",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(company.id),
                "product_id": str(product.id),
                "stage_id": str(stage.id),
                "contract_type": "new_installation",
                "amount": 20_000_000,
                "contract_date": "2026-08-17",
            },
        )

    assert response.status_code == 201
    item = response.json()
    assert item["contract_no"] == "SL-CT-2026-0004"
    assert item["title"] == f"{company.name} {product.name}"
    assert item["owner_member_id"] == str(member.id)
    assert item["position"] == 0
    assert response.headers["location"] == f"/api/contracts/{item['id']}"
    created = db.added[0]
    assert created.team_id == member.team_id
    assert created.owner_member_id == member.id
    assert existing.position == 1
    assert "FOR UPDATE" in str(db.statements[3])
    assert "SL-CT-2026-%" in db.statements[4].compile().params.values()
    assert member.id in db.statements[5].compile().params.values()
    assert db.flush_count == db.commit_count == 1
    assert db.rollback_count == 0


def test_create_rejects_exhausted_number_and_contact_boundary():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    stage = _stage(member.team_id)

    exhausted_db = _Db(
        _Result(scalar=company),
        _Result(scalar=product),
        _Result(scalar=stage),
        _Result(scalar=member.team_id),
        _Result(scalar_values=["SL-CT-2026-9999"]),
    )
    with _client(exhausted_db, member) as client:
        exhausted = client.post(
            "/api/contracts",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(company.id),
                "product_id": str(product.id),
                "stage_id": str(stage.id),
                "contract_type": "renewal",
                "amount": 1,
                "contract_date": "2026-08-17",
            },
        )
    assert exhausted.status_code == 409
    assert exhausted.json() == {"detail": "contract_number_exhausted"}
    assert exhausted_db.rollback_count == 1

    other_company = _company(member.team_id)
    contact = _contact(other_company.id, member.id)
    contact_db = _Db(
        _Result(scalar=company),
        _Result(scalar=product),
        _Result(scalar=stage),
        _Result(scalar=contact),
    )
    with _client(contact_db, member) as client:
        mismatch = client.post(
            "/api/contracts",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(company.id),
                "contact_id": str(contact.id),
                "product_id": str(product.id),
                "stage_id": str(stage.id),
                "contract_type": "renewal",
                "amount": 1,
                "contract_date": "2026-08-17",
            },
        )
    assert mismatch.status_code == 422
    assert mismatch.json() == {"detail": "contact_company_mismatch"}
    assert contact_db.rollback_count == 1


@pytest.mark.parametrize("custom_title", [False, True])
def test_patch_refreshes_only_the_server_derived_title(custom_title: bool):
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    stage = _stage(member.team_id)
    contract = _contract(member, company, product, stage)
    if custom_title:
        contract.title = "직접 입력한 제목"

    new_company = _company(member.team_id)
    new_company.name = "새 합성 고객사"
    new_product = _product(member.team_id)
    new_product.name = "새 합성 상품"
    db = _Db(
        _Result(scalar=contract),
        _Result(rows=[_row(contract, member, company, product, stage)]),
        _Result(scalar=new_company),
        _Result(scalar=new_product),
        _Result(rows=[_row(contract, member, new_company, new_product, stage)]),
    )

    with _client(db, member) as client:
        response = client.patch(
            f"/api/contracts/{contract.id}",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(new_company.id),
                "product_id": str(new_product.id),
            },
        )

    expected = "직접 입력한 제목" if custom_title else "새 합성 고객사 새 합성 상품"
    assert response.status_code == 200
    assert response.json()["title"] == expected
    assert contract.title == expected


def test_patch_and_soft_delete_share_locked_owner_scope():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    stage = _stage(member.team_id)
    contract = _contract(member, company, product, stage)
    patch_db = _Db(
        _Result(scalar=contract),
        _Result(rows=[_row(contract, member, company, product, stage)]),
    )

    with _client(patch_db, member) as client:
        updated = client.patch(
            f"/api/contracts/{contract.id}",
            headers={"Origin": ORIGIN},
            json={"amount": 30_000_000, "memo": None},
        )

    assert updated.status_code == 200
    assert updated.json()["amount"] == 30_000_000
    assert updated.json()["memo"] is None
    assert "FOR UPDATE" in str(patch_db.statements[0])
    assert patch_db.flush_count == patch_db.commit_count == 1

    delete_db = _Db(_Result(scalar=contract))
    with _client(delete_db, member) as client:
        deleted = client.delete(
            f"/api/contracts/{contract.id}",
            headers={"Origin": ORIGIN},
        )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert contract.deleted_at is not None
    assert contract.updated_at == contract.deleted_at
    assert delete_db.flush_count == delete_db.commit_count == 1


def test_move_is_atomic_reorders_both_stages_and_rejects_stale_state():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    source_stage = _stage(member.team_id)
    target_stage = _stage(
        member.team_id,
        name="계약 완료",
        outcome="confirmed",
        position=1,
    )
    moving = _contract(member, company, product, source_stage, position=1)
    source_first = _contract(
        member,
        company,
        product,
        source_stage,
        position=0,
        contract_no="SOURCE",
    )
    target_first = _contract(
        member,
        company,
        product,
        target_stage,
        position=0,
        contract_no="TARGET",
    )
    db = _Db(
        _Result(scalar=target_stage),
        _Result(scalar=moving),
        _Result(scalar_values=[source_first, moving, target_first]),
        _Result(rows=[_row(moving, member, company, product, target_stage)]),
    )

    with _client(db, member) as client:
        response = client.post(
            f"/api/contracts/{moving.id}/move",
            headers={"Origin": ORIGIN},
            json={
                "expected_stage_id": str(source_stage.id),
                "stage_id": str(target_stage.id),
                "position": 0,
            },
        )

    assert response.status_code == 200
    assert response.json()["stage_id"] == str(target_stage.id)
    assert response.json()["stage_outcome_code"] == "confirmed"
    assert moving.stage_id == target_stage.id
    assert moving.position == 0
    assert target_first.position == 1
    assert source_first.position == 0
    assert db.flush_count == db.commit_count == 1
    assert all("FOR UPDATE" in str(statement) for statement in db.statements[1:3])
    assert member.id in db.statements[2].compile().params.values()

    stale = _contract(member, company, product, target_stage)
    stale_db = _Db(_Result(scalar=source_stage), _Result(scalar=stale))
    with _client(stale_db, member) as client:
        conflict = client.post(
            f"/api/contracts/{stale.id}/move",
            headers={"Origin": ORIGIN},
            json={
                "expected_stage_id": str(source_stage.id),
                "stage_id": str(source_stage.id),
                "position": 0,
            },
        )
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "invalid_state_transition"}
    assert stale_db.flush_count == stale_db.commit_count == 0
    assert stale_db.rollback_count == 1


def test_write_failure_rolls_back_contract_transaction():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    stage = _stage(member.team_id)
    db = _Db(
        _Result(scalar=company),
        _Result(scalar=product),
        _Result(scalar=stage),
        _Result(scalar=member.team_id),
        _Result(scalar_values=[]),
        _Result(scalar_values=[]),
        flush_error=RuntimeError("synthetic failure"),
    )

    with _client(db, member) as client, pytest.raises(RuntimeError, match="synthetic failure"):
        client.post(
            "/api/contracts",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(company.id),
                "product_id": str(product.id),
                "stage_id": str(stage.id),
                "contract_type": "new_installation",
                "amount": 1,
                "contract_date": "2026-08-17",
            },
        )

    assert db.commit_count == 0
    assert db.rollback_count == 1
