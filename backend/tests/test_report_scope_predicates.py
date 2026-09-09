"""실행된 WHERE의 대상 컬럼과 팀·담당자 바인딩을 검증한다. 실제 DB 격리는 별도 검증한다."""

from uuid import uuid4

import pytest
from team_scope import has_owner_predicate, has_team_predicate, narrows_to_single_owner
from test_reports import _client, _Db, _member, _Result

from app.api import reports as api
from app.models.content import Report


@pytest.mark.parametrize("role", ["member", "manager"])
@pytest.mark.parametrize(
    "column",
    [Report.team_id, api._author.team_id],
    ids=["report", "author"],
)
def test_detail_binds_each_team_predicate_to_authenticated_team(role, column):
    member = _member(role=role)
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        hidden = client.get(f"/api/reports/{uuid4()}")

    assert hidden.status_code == 404
    assert has_team_predicate(db.statements[0], column, member.team_id)


@pytest.mark.parametrize("role", ["member", "manager"])
def test_list_total_and_rows_each_bind_authenticated_team(role):
    member = _member(role=role)
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(2)])

    with _client(db, member) as client:
        listed = client.get("/api/reports")

    assert listed.status_code == 200
    assert len(db.statements) == 2
    for statement in db.statements:
        assert has_team_predicate(statement, Report.team_id, member.team_id)


# ---- 담당자 범위: 팀원은 본인이 쓴 보고서만 본다 ----
#
# 보고서는 담당자 컬럼 이름이 author_member_id 다. 받는 사람이 아니라 쓴 사람으로 좁힌다.


def test_member_detail_is_scoped_to_reports_they_wrote():
    member = _member(role="member")
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        client.get(f"/api/reports/{uuid4()}")

    assert has_owner_predicate(db.statements[0], Report.author_member_id, member.id)


def test_manager_detail_is_not_narrowed_to_a_single_author():
    manager = _member(role="manager")
    db = _Db(_Result(rows=[]))

    with _client(db, manager) as client:
        client.get(f"/api/reports/{uuid4()}")

    assert not narrows_to_single_owner(db.statements[0], Report.author_member_id)


def test_member_list_queries_are_each_scoped_to_their_own_reports():
    member = _member(role="member")
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(2)])

    with _client(db, member) as client:
        client.get("/api/reports")

    assert len(db.statements) == 2
    for statement in db.statements:
        assert has_owner_predicate(statement, Report.author_member_id, member.id)


def test_manager_list_queries_are_not_narrowed_to_a_single_author():
    """팀장 목록은 팀 전체를 봐야 한다. 상세만 보면 목록이 좁혀진 것을 놓친다."""
    manager = _member(role="manager")
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(2)])

    with _client(db, manager) as client:
        client.get("/api/reports")

    assert len(db.statements) == 2
    for statement in db.statements:
        assert not narrows_to_single_owner(statement, Report.author_member_id)
