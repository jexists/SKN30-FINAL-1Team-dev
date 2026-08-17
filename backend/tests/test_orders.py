from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.crm import CustomerCompany
from app.models.sales import Contract, Product, PurchaseOrder, PurchaseOrderItem
from app.models.workspace import Member
from app.schemas.orders import OrderCreate, OrderMove, OrderPageParams, OrderPatch

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
            if isinstance(value, PurchaseOrder):
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


def _company(team_id: UUID, *, name: str = "합성 고객사") -> CustomerCompany:
    return CustomerCompany(
        id=uuid4(),
        team_id=team_id,
        name=name,
        region_code="seoul",
        created_at=NOW,
    )


def _product(team_id: UUID, *, name: str = "합성 상품", active: bool = True) -> Product:
    return Product(id=uuid4(), team_id=team_id, name=name, active=active)


def _contract(member: Member, company: CustomerCompany) -> Contract:
    return Contract(
        id=uuid4(),
        team_id=member.team_id,
        contract_no="FM-CT-2026-0020",
        customer_company_id=company.id,
        contact_id=None,
        owner_member_id=member.id,
        product_id=None,
        stage_id=uuid4(),
        title="합성 계약",
        description=None,
        contract_type="new_installation",
        amount=10_000_000,
        contract_date=date(2026, 8, 1),
        ends_on=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _order(
    member: Member,
    company: CustomerCompany,
    *,
    contract: Contract | None = None,
    stage_code: str = "order_received",
) -> PurchaseOrder:
    return PurchaseOrder(
        id=uuid4(),
        team_id=member.team_id,
        order_no="SL-PO-2026-0001",
        contract_id=None if contract is None else contract.id,
        customer_company_id=company.id,
        owner_member_id=member.id,
        supplier_name="합성 공급처",
        stage_code=stage_code,
        ordered_on=date(2026, 8, 17),
        due_on=date(2026, 8, 31),
        expected_receipt_on=date(2026, 8, 30),
        memo="합성 메모",
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _item(order: PurchaseOrder, product: Product, *, position: int = 0) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        quantity=position + 1,
        unit_price=1_000_000,
        position=position,
    )


def _row(
    order: PurchaseOrder,
    owner: Member,
    company: CustomerCompany,
    contract: Contract | None = None,
):
    return (
        order,
        owner.display_name,
        company.name,
        None if contract is None else contract.contract_no,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def _payload(company: CustomerCompany, product: Product, **overrides):
    values = {
        "customer_company_id": str(company.id),
        "supplier_name": " 합성 공급처 ",
        "stage_code": "order_received",
        "ordered_on": "2026-08-17",
        "due_on": "2026-08-31",
        "expected_receipt_on": "2026-08-30",
        "memo": " 합성 메모 ",
        "items": [
            {
                "product_id": str(product.id),
                "quantity": 2,
                "unit_price": 1_000_000,
            }
        ],
    }
    return values | overrides


def test_order_request_contract_is_strict_and_uses_six_stage_codes():
    company_id = uuid4()
    product_id = uuid4()
    stages = (
        "order_received",
        "dispatch_request_completed",
        "in_production",
        "stock_received",
        "delivered",
        "cancelled",
    )
    parsed = tuple(
        OrderMove(expected_stage_code="order_received", stage_code=stage).stage_code
        for stage in stages
    )
    assert parsed == stages
    assert OrderPatch(contract_id=None).model_dump(exclude_unset=True) == {"contract_id": None}
    # ERD에 없는 날짜 선후 규칙은 API가 임의로 만들지 않는다.
    assert OrderCreate(
        customer_company_id=company_id,
        supplier_name="공급처",
        stage_code="order_received",
        ordered_on="2026-08-17",
        due_on="2026-08-16",
        expected_receipt_on="2026-08-15",
        items=[{"product_id": product_id, "quantity": 1, "unit_price": 0}],
    )

    with pytest.raises(ValidationError):
        OrderCreate(
            customer_company_id=company_id,
            supplier_name="공급처",
            stage_code="발주 접수",
            ordered_on="2026-08-17",
            due_on="2026-08-31",
            expected_receipt_on="2026-08-30",
            items=[{"product_id": product_id, "quantity": 1, "unit_price": 0}],
        )
    with pytest.raises(ValidationError):
        OrderCreate(
            customer_company_id=company_id,
            supplier_name="공급처",
            stage_code="order_received",
            ordered_on="2026-08-17",
            due_on="2026-08-31",
            expected_receipt_on="2026-08-30",
            items=[],
        )
    with pytest.raises(ValidationError):
        OrderCreate(
            customer_company_id=company_id,
            supplier_name="공급처",
            stage_code="order_received",
            ordered_on="2026-08-17",
            due_on="2026-08-31",
            expected_receipt_on="2026-08-30",
            items=[{"product_id": product_id, "quantity": 1.5, "unit_price": 0}],
        )
    with pytest.raises(ValidationError):
        OrderPatch(stage_code="delivered")
    with pytest.raises(ValidationError):
        OrderPatch(items=None)
    assert OrderPageParams(start_date="2026-08-17", end_date="2026-08-17")
    with pytest.raises(ValidationError):
        OrderPageParams(start_date="2026-08-18", end_date="2026-08-17")


def test_member_order_list_and_detail_are_scoped_and_include_items():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    contract = _contract(member, company)
    order = _order(member, company, contract=contract)
    item = _item(order, product)
    list_db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(order, member, company, contract)]),
        _Result(rows=[(item, product.name)]),
    )

    with _client(list_db, member) as client:
        response = client.get(
            "/api/orders",
            params=[
                ("q", " 합성 "),
                ("supplier_name", order.supplier_name),
                ("stage_code", "order_received"),
                ("start_date", "2026-08-01"),
                ("end_date", "2026-08-31"),
            ],
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0] | {} == {
        "id": str(order.id),
        "order_no": order.order_no,
        "contract_id": str(contract.id),
        "contract_no": contract.contract_no,
        "customer_company_id": str(company.id),
        "customer_company_name": company.name,
        "owner_member_id": str(member.id),
        "owner_display_name": member.display_name,
        "supplier_name": order.supplier_name,
        "stage_code": order.stage_code,
        "ordered_on": "2026-08-17",
        "due_on": "2026-08-31",
        "expected_receipt_on": "2026-08-30",
        "memo": order.memo,
        "items": [
            {
                "id": str(item.id),
                "product_id": str(product.id),
                "product_name": product.name,
                "quantity": 1,
                "unit_price": 1_000_000,
                "position": 0,
            }
        ],
        "created_at": "2026-08-17T18:00:00+09:00",
        "updated_at": "2026-08-17T18:00:00+09:00",
    }
    for statement in list_db.statements[:2]:
        sql = str(statement)
        assert "purchase_order.deleted_at IS NULL" in sql
        assert member.id in statement.compile().params.values()
        assert member.team_id in statement.compile().params.values()
        assert "%합성%" in statement.compile().params.values()
        assert "EXISTS" in sql
    assert "product.active" not in str(list_db.statements[2])

    detail_db = _Db(
        _Result(rows=[_row(order, member, company, contract)]),
        _Result(rows=[(item, product.name)]),
    )
    with _client(detail_db, member) as client:
        detail = client.get(f"/api/orders/{order.id}")
    assert detail.status_code == 200
    assert detail.json()["items"][0]["product_name"] == product.name


def test_owner_filter_rules_and_cross_team_detail_are_hidden():
    manager = _member(role="manager")
    owner = _member(team_id=manager.team_id)
    manager_db = _Db(
        _Result(scalar_values=[owner.id]),
        _Result(scalar=0),
        _Result(rows=[]),
    )
    with _client(manager_db, manager) as client:
        response = client.get("/api/orders", params={"owner_member_id": str(owner.id)})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert [owner.id] in manager_db.statements[2].compile().params.values()

    member = _member()
    scope_db = _Db()
    with _client(scope_db, member) as client:
        denied = client.get("/api/orders", params={"owner_member_id": str(member.id)})
    assert denied.status_code == 403
    assert denied.json() == {"detail": "scope_not_allowed"}
    assert not scope_db.statements

    detail_db = _Db(_Result(rows=[]))
    with _client(detail_db, member) as client:
        hidden = client.get(f"/api/orders/{uuid4()}")
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "order_not_found"}


def test_order_scope_hides_invalid_contracts_and_cross_team_items_without_hiding_inactive_items():
    member = _member()

    list_db = _Db(_Result(scalar=0), _Result(rows=[]))
    with _client(list_db, member) as client:
        listed = client.get("/api/orders")
    assert listed.status_code == 200

    detail_db = _Db(_Result(rows=[]))
    with _client(detail_db, member) as client:
        detail = client.get(f"/api/orders/{uuid4()}")
    assert detail.status_code == 404

    lock_db = _Db(_Result(scalar=None))
    with _client(lock_db, member) as client:
        locked = client.delete(
            f"/api/orders/{uuid4()}",
            headers={"Origin": ORIGIN},
        )
    assert locked.status_code == 404

    for statement in [*list_db.statements, *detail_db.statements, *lock_db.statements]:
        sql = str(statement)
        assert "contract.deleted_at IS NULL" in sql or "contract_1.deleted_at IS NULL" in sql
        assert "customer_company_id = public.purchase_order.customer_company_id" in sql
        assert "owner_member_id = public.purchase_order.owner_member_id" in sql
        assert "NOT (EXISTS" in sql
        assert "product" in sql and "team_id !=" in sql
        assert "product_1.active" not in sql


def test_create_derives_owner_from_contract_and_assigns_server_number():
    manager = _member(role="manager")
    contract_owner = _member(team_id=manager.team_id)
    company = _company(manager.team_id)
    product = _product(manager.team_id)
    contract = _contract(contract_owner, company)
    db = _Db(
        _Result(scalar=company),
        _Result(rows=[(contract, contract_owner.display_name)]),
        _Result(scalar_values=[product]),
        _Result(scalar=manager.team_id),
        _Result(
            scalar_values=[
                "FM-PO-2026-9999",
                "SL-PO-2025-9999",
                "SL-PO-2026-0003",
                "SL-PO-2026-nope",
                "SL-PO-2026-10000",
            ]
        ),
    )

    with _client(db, manager) as client:
        response = client.post(
            "/api/orders",
            headers={"Origin": ORIGIN},
            json=_payload(company, product, contract_id=str(contract.id)),
        )

    assert response.status_code == 201
    item = response.json()
    assert item["order_no"] == "SL-PO-2026-0004"
    assert item["owner_member_id"] == str(contract_owner.id)
    assert item["owner_display_name"] == contract_owner.display_name
    assert item["contract_no"] == contract.contract_no
    assert item["items"][0]["position"] == 0
    assert response.headers["location"] == f"/api/orders/{item['id']}"
    created_order = next(value for value in db.added if isinstance(value, PurchaseOrder))
    assert created_order.team_id == manager.team_id
    assert created_order.owner_member_id == contract_owner.id
    assert len([value for value in db.added if isinstance(value, PurchaseOrderItem)]) == 1
    assert "contract.deleted_at IS NULL" in str(db.statements[1])
    assert "product.active IS true" in str(db.statements[2])
    assert "FOR UPDATE" in str(db.statements[3])
    assert "SL-PO-2026-%" in db.statements[4].compile().params.values()
    assert db.flush_count == db.commit_count == 1
    assert db.rollback_count == 0


def test_create_without_contract_uses_current_member_and_rejects_company_mismatch():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    db = _Db(
        _Result(scalar=company),
        _Result(scalar_values=[product]),
        _Result(scalar=member.team_id),
        _Result(scalar_values=[]),
    )
    with _client(db, member) as client:
        response = client.post(
            "/api/orders",
            headers={"Origin": ORIGIN},
            json=_payload(company, product),
        )
    assert response.status_code == 201
    assert response.json()["owner_member_id"] == str(member.id)
    assert response.json()["contract_id"] is None

    other_company = _company(member.team_id, name="다른 합성 고객사")
    contract = _contract(member, other_company)
    mismatch_db = _Db(
        _Result(scalar=company),
        _Result(rows=[(contract, member.display_name)]),
    )
    with _client(mismatch_db, member) as client:
        mismatch = client.post(
            "/api/orders",
            headers={"Origin": ORIGIN},
            json=_payload(company, product, contract_id=str(contract.id)),
        )
    assert mismatch.status_code == 422
    assert mismatch.json() == {"detail": "contract_company_mismatch"}
    assert mismatch_db.commit_count == 0
    assert mismatch_db.rollback_count == 1


def test_patch_unlinks_contract_preserves_owner_and_replaces_items_atomically():
    member = _member()
    company = _company(member.team_id)
    old_product = _product(member.team_id, name="기존 상품", active=False)
    new_product = _product(member.team_id, name="새 상품")
    contract = _contract(member, company)
    order = _order(member, company, contract=contract)
    replacement = _item(order, new_product)
    db = _Db(
        _Result(scalar=order),
        _Result(scalar_values=[new_product]),
        _Result(),
        _Result(rows=[_row(order, member, company)]),
        _Result(rows=[(replacement, new_product.name)]),
    )

    with _client(db, member) as client:
        response = client.patch(
            f"/api/orders/{order.id}",
            headers={"Origin": ORIGIN},
            json={
                "contract_id": None,
                "memo": None,
                "items": [
                    {
                        "product_id": str(new_product.id),
                        "quantity": 3,
                        "unit_price": 2_000_000,
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["contract_id"] is None
    assert response.json()["owner_member_id"] == str(member.id)
    assert response.json()["memo"] is None
    assert order.contract_id is None
    assert order.owner_member_id == member.id
    assert "DELETE FROM public.purchase_order_item" in str(db.statements[2])
    added_item = next(value for value in db.added if isinstance(value, PurchaseOrderItem))
    added_values = (
        added_item.product_id,
        added_item.quantity,
        added_item.unit_price,
        added_item.position,
    )
    assert added_values == (
        new_product.id,
        3,
        2_000_000,
        0,
    )
    assert db.flush_count == db.commit_count == 1
    assert db.rollback_count == 0
    # 읽기에서는 과거 비활성 상품도 제외하지 않는다.
    assert old_product.active is False
    assert "product.active" not in str(db.statements[4])

    failing_order = _order(member, company)
    failing_db = _Db(
        _Result(scalar=failing_order),
        _Result(scalar_values=[new_product]),
        _Result(),
        flush_error=RuntimeError("synthetic failure"),
    )
    with (
        _client(failing_db, member) as client,
        pytest.raises(RuntimeError, match="synthetic failure"),
    ):
        client.patch(
            f"/api/orders/{failing_order.id}",
            headers={"Origin": ORIGIN},
            json={
                "items": [
                    {
                        "product_id": str(new_product.id),
                        "quantity": 1,
                        "unit_price": 0,
                    }
                ]
            },
        )
    assert failing_db.commit_count == 0
    assert failing_db.rollback_count == 1


def test_move_uses_stale_guard_and_delete_is_soft():
    member = _member()
    company = _company(member.team_id)
    product = _product(member.team_id)
    order = _order(member, company)
    item = _item(order, product)
    move_db = _Db(
        _Result(scalar=order),
        _Result(rows=[_row(order, member, company)]),
        _Result(rows=[(item, product.name)]),
    )
    with _client(move_db, member) as client:
        moved = client.post(
            f"/api/orders/{order.id}/move",
            headers={"Origin": ORIGIN},
            json={
                "expected_stage_code": "order_received",
                "stage_code": "delivered",
            },
        )
    assert moved.status_code == 200
    assert moved.json()["stage_code"] == "delivered"
    assert order.stage_code == "delivered"
    assert "FOR UPDATE" in str(move_db.statements[0])
    assert move_db.flush_count == move_db.commit_count == 1

    stale_order = _order(member, company, stage_code="in_production")
    stale_db = _Db(_Result(scalar=stale_order))
    with _client(stale_db, member) as client:
        conflict = client.post(
            f"/api/orders/{stale_order.id}/move",
            headers={"Origin": ORIGIN},
            json={
                "expected_stage_code": "order_received",
                "stage_code": "stock_received",
            },
        )
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "invalid_state_transition"}
    assert stale_db.flush_count == stale_db.commit_count == 0
    assert stale_db.rollback_count == 1

    delete_db = _Db(_Result(scalar=order))
    with _client(delete_db, member) as client:
        deleted = client.delete(
            f"/api/orders/{order.id}",
            headers={"Origin": ORIGIN},
        )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert order.deleted_at is not None
    assert order.updated_at == order.deleted_at
    assert all(
        not str(statement).startswith("DELETE FROM public.purchase_order_item")
        for statement in delete_db.statements
    )
    assert delete_db.flush_count == delete_db.commit_count == 1
