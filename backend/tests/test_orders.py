import asyncio
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import orders as api
from app.models.configuration import PurchaseOrderStatus
from app.models.crm import CustomerCompany
from app.models.sales import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesDeal,
    SalesPipeline,
    SalesPipelineStage,
)
from app.models.workspace import Member
from app.schemas.orders import OrderCreate, OrderMove, OrderPageParams, OrderPatch

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
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results
        return self.results.pop(0)

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name="합성 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _company(member: Member) -> CustomerCompany:
    return CustomerCompany(
        id=uuid4(),
        team_id=member.team_id,
        name="합성 고객사",
        region_code="seoul",
        created_at=NOW,
    )


def _pipeline(member: Member, *, status_code: str = "published") -> SalesPipeline:
    return SalesPipeline(
        id=uuid4(),
        team_id=member.team_id,
        name="기본 영업",
        description=None,
        status_code=status_code,
        is_default=True,
        published_at=NOW,
        archived_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _stage(
    pipeline: SalesPipeline,
    *,
    code: str,
    phase: str,
    position: int,
) -> SalesPipelineStage:
    return SalesPipelineStage(
        id=uuid4(),
        sales_pipeline_id=pipeline.id,
        stage_code=code,
        name=code,
        tone="gray",
        phase_code=phase,
        outcome_code="in_progress",
        position=position,
        created_at=NOW,
        updated_at=NOW,
    )


def _deal(
    member: Member,
    company: CustomerCompany,
    pipeline: SalesPipeline,
    stage: SalesPipelineStage,
    *,
    position: int = 0,
) -> SalesDeal:
    return SalesDeal(
        id=uuid4(),
        team_id=member.team_id,
        deal_no="FM-CT-2026-0020",
        customer_company_id=company.id,
        customer_contact_id=None,
        owner_member_id=member.id,
        product_id=None,
        sales_pipeline_id=pipeline.id,
        sales_pipeline_stage_id=stage.id,
        title="합성 딜",
        description=None,
        sales_deal_type_id=uuid4(),
        deal_amount=10_000_000,
        opened_on=date(2026, 8, 1),
        closed_on=date(2026, 8, 10),
        quote_no=None,
        quote_issued_on=None,
        quote_valid_until=None,
        contract_no=None,
        contract_signed_on=None,
        contract_ends_on=None,
        quote_status_id=None,
        contract_status_id=None,
        quote_amount=None,
        contract_amount=None,
        quote_delivery_terms=None,
        warranty_terms=None,
        expected_delivery_at=None,
        memo=None,
        stage_position=position,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _status(member: Member, *, code: str = "order_received", deleted: bool = False):
    return PurchaseOrderStatus(
        id=uuid4(),
        team_id=member.team_id,
        code=code,
        name=code,
        tone="gray",
        position=0,
        deleted_at=NOW if deleted else None,
        created_at=NOW,
        updated_at=NOW,
        outcome_code="in_progress",
    )


def _product(member: Member) -> Product:
    return Product(id=uuid4(), team_id=member.team_id, name="합성 상품", active=True)


def _order(member: Member, deal: SalesDeal, order_status: PurchaseOrderStatus) -> PurchaseOrder:
    return PurchaseOrder(
        id=uuid4(),
        team_id=member.team_id,
        order_no="SL-PO-2026-0001",
        sales_deal_id=deal.id,
        supplier_name="합성 공급처",
        purchase_order_status_id=order_status.id,
        ordered_on=date(2026, 8, 17),
        due_on=date(2026, 8, 31),
        expected_receipt_on=date(2026, 8, 30),
        request_department="영업팀",
        cooperation_department="생산팀",
        created_by_member_id=member.id,
        expected_customer_company_id=deal.customer_company_id,
        memo="합성 메모",
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _item(order: PurchaseOrder, product: Product) -> PurchaseOrderItem:
    return PurchaseOrderItem(
        id=uuid4(),
        purchase_order_id=order.id,
        product_id=product.id,
        quantity=2,
        unit_price=1_000_000,
        position=0,
    )


def _row(
    order: PurchaseOrder,
    deal: SalesDeal,
    company: CustomerCompany,
    member: Member,
    order_status: PurchaseOrderStatus,
):
    return (
        order,
        deal.deal_no,
        company.id,
        company.name,
        member.id,
        member.display_name,
        order_status.code,
        order_status.name,
        order_status.tone,
        order_status.outcome_code,
        order_status.position,
        member.display_name,
        company.name,
    )


def test_order_writes_require_deal_and_keep_dynamic_stage_code():
    product_id = uuid4()
    payload = OrderCreate(
        sales_deal_id=uuid4(),
        supplier_name="공급처",
        stage_code="team_custom_status",
        ordered_on="2026-08-17",
        due_on="2026-08-18",
        expected_receipt_on="2026-08-19",
        items=[{"product_id": product_id, "quantity": 1, "unit_price": 0}],
    )
    assert payload.stage_code == "team_custom_status"
    assert OrderPatch(memo=None).model_dump(exclude_unset=True) == {"memo": None}
    assert OrderPageParams(stage_code=["team_custom_status"])

    with pytest.raises(ValidationError):
        OrderCreate(**(payload.model_dump() | {"sales_deal_id": None}))
    with pytest.raises(ValidationError):
        OrderCreate(**(payload.model_dump() | {"due_on": date(2026, 8, 16)}))
    with pytest.raises(ValidationError):
        OrderCreate(**(payload.model_dump() | {"customer_company_id": uuid4()}))
    with pytest.raises(ValidationError):
        OrderPatch(sales_deal_id=None)
    with pytest.raises(ValidationError):
        OrderMove(expected_stage_code="order_received", stage_code="발주 완료")


def test_order_status_options_hide_deleted_but_order_reads_preserve_deleted_status():
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member, status_code="archived")
    stage = _stage(pipeline, code="order_in_progress", phase="order", position=6)
    deal = _deal(member, company, pipeline, stage)
    current_status = _status(member, deleted=True)
    order = _order(member, deal, current_status)
    product = _product(member)
    item = _item(order, product)
    db = _Db(
        _Result(scalar_values=[_status(member)]),
        _Result(scalar=1),
        _Result(rows=[_row(order, deal, company, member, current_status)]),
        _Result(rows=[(current_status.code, 1)]),
        _Result(rows=[(order.supplier_name,)]),
        _Result(rows=[(item, product.name)]),
        _Result(rows=[_row(order, deal, company, member, current_status)]),
        _Result(rows=[(item, product.name)]),
    )

    options = asyncio.run(api.list_purchase_order_statuses(member, db))
    page = asyncio.run(api.list_orders(OrderPageParams(), member, db))
    detail = asyncio.run(api.get_order(order.id, member, db))

    assert len(options) == 1
    assert page.items[0].stage_code == current_status.code
    assert detail.id == order.id
    assert page.items[0].customer_company_id == deal.customer_company_id
    assert page.items[0].owner_member_id == deal.owner_member_id
    assert "purchase_order_status.deleted_at IS NULL" in str(db.statements[0])
    for statement in (db.statements[1], db.statements[2], db.statements[4]):
        sql = str(statement)
        assert "purchase_order.deleted_at IS NULL" in sql
        assert "purchase_order_status.deleted_at IS NULL" not in sql
        assert "sales_pipeline_stage_1.phase_code" in sql
        assert "order" in statement.compile().params.values()


def test_order_detail_hides_order_after_deal_leaves_order_phase():
    member = _member()
    order_id = uuid4()
    db = _Db(_Result(rows=[]))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.get_order(order_id, member, db))

    assert exc.value.status_code == 404
    assert exc.value.detail == "order_not_found"
    assert "sales_pipeline_stage_1.phase_code" in str(db.statements[0])
    assert "order" in db.statements[0].compile().params.values()


def test_archived_pipeline_deal_is_not_a_new_order_or_relink_target():
    member = _member()
    db = _Db(_Result(rows=[]))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._team_sales_deal(db, member, uuid4()))

    assert exc.value.status_code == 404
    params = db.statements[0].compile().params.values()
    assert "published" in params
    assert "archived" not in params


def test_order_creation_move_uses_first_order_stage_and_reorders_atomically():
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member)
    source_stage = _stage(pipeline, code="contract_completed", phase="contract", position=5)
    order_stage = _stage(pipeline, code="order_in_progress", phase="order", position=6)
    moving = _deal(member, company, pipeline, source_stage, position=1)
    source_first = _deal(member, company, pipeline, source_stage, position=0)
    target_first = _deal(member, company, pipeline, order_stage, position=0)
    db = _Db(
        _Result(scalar=order_stage),
        _Result(scalar_values=[source_first, moving, target_first]),
    )

    asyncio.run(api._move_deal_to_first_stage_of_phase(db, member, moving, "contract", "order"))

    assert moving.sales_pipeline_stage_id == order_stage.id
    assert moving.stage_position == 0
    assert moving.closed_on is None
    assert source_first.stage_position == 0
    assert target_first.stage_position == 1
    assert "sales_pipeline_stage.phase_code" in str(db.statements[0])


def test_order_creation_fails_when_pipeline_has_no_order_stage():
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="contract_completed", phase="contract", position=5)
    deal = _deal(member, company, pipeline, stage)
    db = _Db(_Result(scalar=None))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._move_deal_to_first_stage_of_phase(db, member, deal, "contract", "order"))

    assert exc.value.status_code == 409
    assert exc.value.detail == "sales_pipeline_order_stage_not_found"


def test_order_status_move_resolves_active_target_and_rejects_stale_state(monkeypatch):
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="order_in_progress", phase="order", position=6)
    deal = _deal(member, company, pipeline, stage)
    current_status = _status(member, code="order_received", deleted=True)
    target_status = _status(member, code="delivered")
    target_status.outcome_code = "completed"
    order = _order(member, deal, current_status)
    db = _Db()

    async def locked(*_args):
        return order, current_status.code

    async def active_status(*_args):
        return target_status

    async def order_row(*_args):
        return _row(order, deal, company, member, target_status)

    async def items(*_args):
        return {order.id: []}

    monkeypatch.setattr(api, "_locked_order", locked)
    monkeypatch.setattr(api, "_active_order_status", active_status)
    monkeypatch.setattr(api, "_order_row", order_row)
    monkeypatch.setattr(api, "_items_by_order_ids", items)

    result = asyncio.run(
        api.move_order(
            order.id,
            OrderMove(expected_stage_code="order_received", stage_code="delivered"),
            member,
            db,
        )
    )
    assert result.stage_code == "delivered"
    assert order.purchase_order_status_id == target_status.id

    async def stale(*_args):
        return order, "delivered"

    monkeypatch.setattr(api, "_locked_order", stale)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.move_order(
                order.id,
                OrderMove(expected_stage_code="order_received", stage_code="delivered"),
                member,
                db,
            )
        )
    assert exc.value.status_code == 409
    assert db.rollback_count == 1


def test_orders_can_be_narrowed_to_one_sales_deal():
    """일정 상세의 관련 발주. 전건을 받아 거르지 않고 딜 하나로 좁혀 받는다."""
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="order_in_progress", phase="order", position=6)
    deal = _deal(member, company, pipeline, stage)
    status = _status(member)
    order = _order(member, deal, status)
    product = _product(member)
    item = _item(order, product)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(order, deal, company, member, status)]),
        _Result(rows=[(status.code, 1)]),
        _Result(rows=[(order.supplier_name,)]),
        _Result(rows=[(item, product.name)]),
    )

    page = asyncio.run(api.list_orders(OrderPageParams(sales_deal_id=[deal.id]), member, db))

    assert page.total == 1
    assert page.items[0].sales_deal_id == deal.id
    for statement in (db.statements[0], db.statements[1]):
        sql = str(statement)
        assert "purchase_order.sales_deal_id IN" in sql
        # IN 절이라 값이 목록으로 묶여 들어간다.
        assert [deal.id] in statement.compile().params.values()


def test_orders_can_be_picked_by_order_no():
    """상세 화면이 주소의 발주 번호로 바로 들어온다. 번호로 한 건만 집어 온다.

    목록에서 찾으면 그 발주가 현재 페이지 밖일 때 상세가 열리지 않는다. q 는 여러 열을
    훑는 부분 일치라 번호를 아는 조회에는 쓸 수 없다.
    """
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="order_in_progress", phase="order", position=6)
    deal = _deal(member, company, pipeline, stage)
    status = _status(member)
    order = _order(member, deal, status)
    product = _product(member)
    item = _item(order, product)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(order, deal, company, member, status)]),
        _Result(rows=[(status.code, 1)]),
        _Result(rows=[(order.supplier_name,)]),
        _Result(rows=[(item, product.name)]),
    )

    page = asyncio.run(api.list_orders(OrderPageParams(order_no=order.order_no), member, db))

    assert page.total == 1
    assert page.items[0].order_no == order.order_no
    # 개수 쿼리와 행 쿼리가 같은 조건으로 좁혀야 총계와 목록이 어긋나지 않는다.
    for statement in (db.statements[0], db.statements[1]):
        assert "purchase_order.order_no = " in str(statement)
        assert order.order_no in statement.compile().params.values()


def test_tab_counts_and_supplier_options_drop_only_their_own_filter():
    """탭 건수와 공급처 목록은 각자 자기 조건만 빼고 센다.

    자기 조건까지 넣으면 고른 항목만 남아 다른 탭·다른 공급처로 옮겨 갈 수가 없다.
    반대로 남의 조건까지 빼면 골랐을 때 0건이 되는 항목을 내놓게 된다.
    """
    member = _member()
    company = _company(member)
    pipeline = _pipeline(member)
    stage = _stage(pipeline, code="order_in_progress", phase="order", position=6)
    deal = _deal(member, company, pipeline, stage)
    status = _status(member)
    db = _Db(
        _Result(scalar=0),
        _Result(rows=[]),
        _Result(rows=[(status.code, 2), ("done", 5)]),
        _Result(rows=[("합성 공급처",)]),
    )

    page = asyncio.run(
        api.list_orders(
            OrderPageParams(stage_code=[status.code], supplier_name="합성 공급처"),
            member,
            db,
        )
    )

    assert page.counts == {status.code: 2, "done": 5}
    assert page.suppliers == ["합성 공급처"]

    # 상태 표는 별칭으로 조인되므로 별칭 이름으로 본다.
    status_filter = "purchase_order_status_1.code IN"
    supplier_filter = "purchase_order.supplier_name = "
    rows_sql = str(db.statements[1])
    counts_sql = str(db.statements[2])
    suppliers_sql = str(db.statements[3])

    # 목록은 두 조건을 다 적용한다. 별칭 이름이 바뀌면 아래 단언이 헛돌므로 여기서 잡는다.
    assert status_filter in rows_sql
    assert supplier_filter in rows_sql
    # 건수는 상태를 빼고 공급처는 남긴다.
    assert status_filter not in counts_sql
    assert supplier_filter in counts_sql
    # 공급처 목록은 그 반대다.
    assert supplier_filter not in suppliers_sql
    assert status_filter in suppliers_sql
    assert deal.id is not None
