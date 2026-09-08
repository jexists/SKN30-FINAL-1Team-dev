"""실행된 WHERE의 대상 컬럼과 팀 바인딩을 검증한다. 실제 DB 격리는 별도 검증한다."""

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from team_scope import has_owner_predicate, has_team_predicate
from test_orders import _Db, _member, _Result

from app.api import orders as api
from app.models.sales import PurchaseOrder
from app.schemas.orders import OrderPageParams


@pytest.mark.parametrize("role", ["member", "manager"])
@pytest.mark.parametrize(
    "column",
    [
        PurchaseOrder.team_id,
        api._sales_deal.team_id,
        api._owner.team_id,
        api._company.team_id,
        api._order_status.team_id,
        api._creator.team_id,
        api._expected_company.team_id,
    ],
    ids=["order", "deal", "owner", "company", "status", "creator", "expected_company"],
)
def test_detail_binds_each_team_predicate_to_authenticated_team(role, column):
    member = _member(role=role)
    db = _Db(_Result(rows=[]))
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.get_order(uuid4(), member, db))
    assert error.value.status_code == 404
    assert error.value.detail == "order_not_found"
    assert has_team_predicate(db.statements[0], column, member.team_id)


@pytest.mark.parametrize("role", ["member", "manager"])
def test_list_total_rows_counts_and_suppliers_each_bind_authenticated_team(role):
    member = _member(role=role)
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(4)])
    page = asyncio.run(api.list_orders(OrderPageParams(), member, db))
    assert page.total == 0 and page.items == []
    # 목록 한 번에 개수·본문·상태별 건수·공급처 목록 네 쿼리가 나간다. 하나라도 팀 조건이
    # 빠지면 남의 팀 발주가 개수나 필터 후보에 섞인다.
    assert len(db.statements) == 4
    for statement in db.statements:
        assert has_team_predicate(statement, PurchaseOrder.team_id, member.team_id)


# ---- 담당자 범위: 팀원은 본인이 맡은 딜의 발주만 본다 ----
#
# 발주에는 담당자 컬럼이 없다. 딸린 딜의 담당자로 좁힌다.


def test_member_detail_is_scoped_to_deals_they_own():
    member = _member(role="member")
    db = _Db(_Result(rows=[]))
    with pytest.raises(HTTPException):
        asyncio.run(api.get_order(uuid4(), member, db))
    assert has_owner_predicate(db.statements[0], api._sales_deal.owner_member_id, member.id)


def test_manager_detail_is_not_narrowed_to_a_single_owner():
    manager = _member(role="manager")
    db = _Db(_Result(rows=[]))
    with pytest.raises(HTTPException):
        asyncio.run(api.get_order(uuid4(), manager, db))
    assert not has_owner_predicate(db.statements[0], api._sales_deal.owner_member_id, manager.id)


def test_member_list_queries_are_each_scoped_to_their_own_deals():
    member = _member(role="member")
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(4)])
    asyncio.run(api.list_orders(OrderPageParams(), member, db))
    assert len(db.statements) == 4
    for statement in db.statements:
        assert has_owner_predicate(statement, api._sales_deal.owner_member_id, member.id)
