"""실행된 WHERE의 대상 컬럼과 팀·담당자 바인딩을 검증한다. 실제 DB 격리는 별도 검증한다."""

from uuid import uuid4

import pytest
from team_scope import has_owner_predicate, has_team_predicate
from test_activities import _client, _Db, _member, _Result

from app.api import activities as api
from app.models.crm import Activity


@pytest.mark.parametrize("role", ["member", "manager"])
@pytest.mark.parametrize(
    "column",
    [
        Activity.team_id,
        api._owner.team_id,
        api._company.team_id,
        api._sales_deal.team_id,
    ],
    ids=["activity", "owner", "company", "deal"],
)
def test_detail_binds_each_team_predicate_to_authenticated_team(role, column):
    member = _member(role=role)
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        hidden = client.get(f"/api/activities/{uuid4()}")

    assert hidden.status_code == 404
    assert has_team_predicate(db.statements[0], column, member.team_id)


@pytest.mark.parametrize("role", ["member", "manager"])
def test_list_total_and_rows_each_bind_authenticated_team(role):
    member = _member(role=role)
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(2)])

    with _client(db, member) as client:
        listed = client.get("/api/activities")

    assert listed.status_code == 200
    assert len(db.statements) == 2
    for statement in db.statements:
        assert has_team_predicate(statement, Activity.team_id, member.team_id)


# ---- 담당자 범위: 팀원은 본인 일정만 본다 ----


def test_member_detail_is_scoped_to_activities_they_own():
    member = _member(role="member")
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        client.get(f"/api/activities/{uuid4()}")

    assert has_owner_predicate(db.statements[0], Activity.owner_member_id, member.id)


def test_manager_detail_is_not_narrowed_to_a_single_owner():
    manager = _member(role="manager")
    db = _Db(_Result(rows=[]))

    with _client(db, manager) as client:
        client.get(f"/api/activities/{uuid4()}")

    assert not has_owner_predicate(db.statements[0], Activity.owner_member_id, manager.id)


def test_member_list_queries_are_each_scoped_to_their_own_activities():
    member = _member(role="member")
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(2)])

    with _client(db, member) as client:
        client.get("/api/activities")

    assert len(db.statements) == 2
    for statement in db.statements:
        assert has_owner_predicate(statement, Activity.owner_member_id, member.id)
