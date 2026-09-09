"""접근 범위 검증에 쓰는 공용 검사.

팀 격리(다른 팀)와 담당자 범위(같은 팀 다른 사람)가 같은 형태라 한 함수로 본다.

SQL 을 문자열로 바꿔 이름을 찾는 방식은 쓰지 않는다. 조인 조건(``ON ... = ....team_id``)과
SELECT 목록에도 같은 이름이 나와서, WHERE 에서 팀 조건을 통째로 빼도 그대로 통과한다.
문자열을 ``WHERE`` 로 자르는 것도 안전하지 않다 — 서브쿼리가 자기 WHERE 를 갖고 있어 엉뚱한
절을 집는다. 둘 다 실제로 겪었다.

그래서 문자열 대신 WHERE 절의 식 트리를 본다. 다만 트리 전체를 훑으면 안 된다 — 서브쿼리
안에만 있는 조건까지 세어, 바깥 행이 전혀 안 막히는 쿼리도 통과시킨다. 이 조건은 바깥 행을
거르는 자리에 있어야 뜻이 있다.
"""

from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import (
    BinaryExpression,
    BindParameter,
    BooleanClauseList,
    Grouping,
)
from sqlalchemy.sql.selectable import Exists

# 값을 지정하지 않으면 어떤 값에 묶였든 조건 자체를 찾는다.
ANY_VALUE = object()


def _outer_nodes(clause):
    """바깥 행을 거르는 자리의 노드만 낸다. 서브쿼리 안으로는 들어가지 않는다.

    AND 는 물론 OR 도 따라 내려간다. 실제 스코프가 nullable 관계를 ``or_(fk.is_(None),
    <표>.team_id == member.team_id)`` 로 쓰기 때문이다. 그 형태를 인정하지 않으면 상품·견적
    상태·계약 상태·연락처 담당자를 검사할 수 없다. AND 안의 OR 는 괄호(``Grouping``)로
    감싸여 오므로 그것도 벗겨 낸다.
    """
    if clause is None:
        return
    yield clause
    if isinstance(clause, Grouping):
        yield from _outer_nodes(clause.element)
    elif isinstance(clause, BooleanClauseList):
        for child in clause.clauses:
            yield from _outer_nodes(child)


def has_bound_predicate(statement, column, value=ANY_VALUE) -> bool:
    """statement 의 최상위 WHERE 에 ``<column> = <value>`` 조건이 있으면 True.

    서브쿼리(EXISTS·스칼라 SELECT) 안에만 있는 조건은 세지 않는다. 그 자리는 바깥 행을
    거르지 못한다. ``value`` 를 생략하면 묶인 값과 무관하게 등호 조건 자체를 찾는다.
    """
    target = column.__clause_element__()
    return any(
        isinstance(node, BinaryExpression)
        and node.operator is operators.eq
        and getattr(node.left, "table", None) is target.table
        and node.left.compare(target)
        and isinstance(node.right, BindParameter)
        and (value is ANY_VALUE or node.right.value == value)
        for node in _outer_nodes(statement.whereclause)
    )


def has_team_predicate(statement, column, team_id) -> bool:
    """팀 격리용 이름. 담당자 범위와 검사 형태가 같아 has_bound_predicate 에 위임한다."""
    return has_bound_predicate(statement, column, team_id)


def has_owner_predicate(statement, column, member_id) -> bool:
    """담당자 범위용 이름. 팀원은 본인 것만 보므로 이 조건이 있어야 하고, 팀장은 없어야 한다."""
    return has_bound_predicate(statement, column, member_id)


def narrows_to_single_owner(statement, column) -> bool:
    """담당자 컬럼이 값과 무관하게 한 사람과 등호로 묶였으면 True.

    팀장 검사에 쓴다. 팀장 본인 id 로만 확인하면 쿼리가 다른 값으로 좁혀져도 통과한다.
    조건이 무엇에 묶였는지가 아니라 조건의 존재 자체를 본다.

    호출부는 담당자 필터가 없는 요청이어야 한다. 팀장이 화면에서 담당자를 고르면 그 조건은
    정상이며, 여기서는 구분하지 않는다.
    """
    return has_bound_predicate(statement, column)


def _outer_exists_selects(clause):
    """최상위 OR 의 EXISTS 서브쿼리 SELECT 를 낸다.

    서브쿼리 안 조건은 보통 바깥 행을 거르지 못해 세지 않는다. 다만 최상위 OR 의 한쪽인
    EXISTS 는 바깥 행을 실제로 거른다. 고객 담당자 범위가 그 형태라 이 경로가 필요하다.
    """
    for node in _outer_nodes(clause):
        if isinstance(node, Exists):
            inner = node.element
            inner = getattr(inner, "element", inner)
            if inner is not None:
                yield inner


def has_exists_bound_predicate(statement, column, value=ANY_VALUE) -> bool:
    """최상위 OR 의 EXISTS 안에 ``<column> = <value>`` 조건이 있으면 True.

    ``or_(대표담당자 == 나, EXISTS(담당자표에 내가 있다))`` 의 뒤쪽 절을 본다. 앞쪽만 보면
    EXISTS 안의 바인딩이 인증된 사용자에서 풀려도 통과한다.
    """
    return any(
        has_bound_predicate(inner, column, value)
        for inner in _outer_exists_selects(statement.whereclause)
    )
