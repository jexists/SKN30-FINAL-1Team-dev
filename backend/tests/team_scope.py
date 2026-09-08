"""팀 격리 검증에 쓰는 공용 검사.

SQL 을 문자열로 바꿔 이름을 찾는 방식은 쓰지 않는다. 조인 조건(``ON ... = ....team_id``)과
SELECT 목록에도 같은 이름이 나와서, WHERE 에서 팀 조건을 통째로 빼도 그대로 통과한다.
문자열을 ``WHERE`` 로 자르는 것도 안전하지 않다 — 서브쿼리가 자기 WHERE 를 갖고 있어 엉뚱한
절을 집는다. 둘 다 실제로 겪었다.

그래서 문자열 대신 WHERE 절의 식 트리를 훑어, 그 컬럼이 인증된 팀 값에 실제로 묶였는지 본다.
"""

from sqlalchemy.sql import operators, visitors
from sqlalchemy.sql.elements import BinaryExpression, BindParameter


def has_team_predicate(statement, column, team_id) -> bool:
    """statement 의 WHERE 에 ``<column> = <team_id>`` 조건이 있으면 True."""
    return any(
        isinstance(node, BinaryExpression)
        and node.operator is operators.eq
        and getattr(node.left, "table", None) is column.__clause_element__().table
        and node.left.compare(column.__clause_element__())
        and isinstance(node.right, BindParameter)
        and node.right.value == team_id
        for node in visitors.iterate(statement.whereclause)
    )
