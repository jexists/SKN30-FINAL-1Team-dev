"""공용 팀 조건 검사(team_scope) 자체를 검증한다.

이 검사가 느슨하면 그 위에 쌓은 딜·발주·C/S 테스트가 전부 같이 느슨해진다. 그래서 무엇을
통과시키고 무엇을 막아야 하는지 여기서 못박는다.
"""

from uuid import uuid4

from sqlalchemy import or_, select
from team_scope import has_team_predicate

from app.models.crm import Activity
from app.models.sales import SalesDeal


def test_top_level_team_predicate_is_found():
    team = uuid4()
    statement = select(SalesDeal).where(SalesDeal.team_id == team)
    assert has_team_predicate(statement, SalesDeal.team_id, team)


def test_predicate_joined_by_and_is_found():
    team = uuid4()
    statement = select(SalesDeal).where(
        SalesDeal.deleted_at.is_(None),
        SalesDeal.team_id == team,
    )
    assert has_team_predicate(statement, SalesDeal.team_id, team)


def test_predicate_inside_a_nullable_or_is_found():
    """실제 스코프가 nullable 관계에 쓰는 형태다. 이걸 막으면 상품·견적·계약을 검사할 수 없다."""
    team = uuid4()
    statement = select(SalesDeal).where(
        or_(SalesDeal.product_id.is_(None), SalesDeal.team_id == team)
    )
    assert has_team_predicate(statement, SalesDeal.team_id, team)


def test_predicate_only_inside_a_subquery_is_not_counted():
    """서브쿼리 안의 조건은 바깥 행을 거르지 못한다.

    트리 전체를 훑으면 이 쿼리도 통과시켜, 바깥이 전혀 안 막힌 상태를 "격리됨"으로 읽는다.
    """
    team = uuid4()
    inner = select(Activity.id).where(SalesDeal.team_id == team).exists()
    statement = select(SalesDeal).where(inner)
    assert not has_team_predicate(statement, SalesDeal.team_id, team)


def test_other_team_value_is_not_counted():
    """조건이 있어도 묶인 값이 다른 팀이면 격리가 아니다."""
    team = uuid4()
    statement = select(SalesDeal).where(SalesDeal.team_id == uuid4())
    assert not has_team_predicate(statement, SalesDeal.team_id, team)


def test_missing_where_is_not_counted():
    assert not has_team_predicate(select(SalesDeal), SalesDeal.team_id, uuid4())
