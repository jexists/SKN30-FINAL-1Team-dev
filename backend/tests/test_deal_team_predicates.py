"""실행된 WHERE의 대상 컬럼과 팀 바인딩을 검증한다. 실제 DB 격리는 별도 검증한다."""

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from team_scope import has_team_predicate
from test_sales_deals import _Db, _member, _Result

from app.api import sales_deals as api
from app.models.sales import SalesDeal
from app.schemas.sales_deals import SalesDealPageParams


@pytest.mark.parametrize("role", ["member", "manager"])
@pytest.mark.parametrize(
    "column",
    [
        SalesDeal.team_id,
        api._owner.team_id,
        api._company.team_id,
        api._pipeline.team_id,
        api._deal_type.team_id,
        api._product.team_id,
        api._quote_status.team_id,
        api._contract_status.team_id,
        api._contact_owner.team_id,
    ],
    ids=["deal", "owner", "company", "pipeline", "type", "product", "quote", "contract", "contact"],
)
def test_detail_binds_each_team_predicate_to_authenticated_team(role, column):
    member = _member(role=role)
    db = _Db(_Result(rows=[]))
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.get_sales_deal(uuid4(), member, db))
    assert error.value.status_code == 404
    assert has_team_predicate(db.statements[0], column, member.team_id)


@pytest.mark.parametrize("role", ["member", "manager"])
def test_list_total_rows_and_tab_counts_each_bind_authenticated_team(role):
    member = _member(role=role)
    db = _Db(_Result(scalar=0), _Result(rows=[]), _Result(rows=[]))
    result = asyncio.run(api.list_sales_deals(SalesDealPageParams(), member, db))
    assert result.total == 0 and result.items == [] and result.counts == {}
    # 빈 목록에서는 자식 조회를 생략하므로 실제 실행되는 세 쿼리를 모두 확인한다.
    assert len(db.statements) == 3
    for statement in db.statements:
        assert has_team_predicate(statement, SalesDeal.team_id, member.team_id)
