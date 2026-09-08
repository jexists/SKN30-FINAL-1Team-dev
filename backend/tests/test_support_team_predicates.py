"""실행된 WHERE의 대상 컬럼과 팀 바인딩을 검증한다. 실제 DB 격리는 별도 검증한다."""

from uuid import uuid4

import pytest
from team_scope import has_team_predicate
from test_support import _client, _Db, _member, _Result

from app.api import support as api
from app.models.crm import SupportRequest


@pytest.mark.parametrize("role", ["member", "manager"])
@pytest.mark.parametrize(
    "column",
    [
        SupportRequest.team_id,
        api._assignee.team_id,
        api._company.team_id,
        api._deal.team_id,
    ],
    ids=["request", "assignee", "company", "deal"],
)
def test_detail_binds_each_team_predicate_to_authenticated_team(role, column):
    member = _member(role=role)
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        hidden = client.get(f"/api/support-requests/{uuid4()}")

    assert hidden.status_code == 404
    assert has_team_predicate(db.statements[0], column, member.team_id)


@pytest.mark.parametrize("role", ["member", "manager"])
def test_list_total_rows_and_counts_each_bind_authenticated_team(role):
    member = _member(role=role)
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(3)])

    with _client(db, member) as client:
        listed = client.get("/api/support-requests")

    assert listed.status_code == 200
    # 목록 한 번에 개수·본문·상태별 건수 세 쿼리가 나간다. 하나라도 팀 조건이 빠지면
    # 남의 팀 C/S 가 개수나 목록에 섞인다.
    assert len(db.statements) == 3
    for statement in db.statements:
        assert has_team_predicate(statement, SupportRequest.team_id, member.team_id)
