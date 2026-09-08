"""실행된 WHERE의 대상 컬럼과 팀·담당자 바인딩을 검증한다. 실제 DB 격리는 별도 검증한다."""

from uuid import uuid4

import pytest
from team_scope import has_owner_predicate, has_team_predicate
from test_customers import _client, _Db, _member, _Result

from app.models.crm import CustomerCompany, CustomerContact


@pytest.mark.parametrize("role", ["member", "manager"])
@pytest.mark.parametrize(
    "column",
    [CustomerCompany.team_id],
    ids=["company"],
)
def test_detail_binds_each_team_predicate_to_authenticated_team(role, column):
    """고객은 팀 컬럼이 고객사에만 있다. 담당자 표는 고객사를 거쳐 팀에 묶인다."""
    member = _member(role=role)
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        hidden = client.get(f"/api/customer-contacts/{uuid4()}")

    assert hidden.status_code == 404
    assert has_team_predicate(db.statements[0], column, member.team_id)


@pytest.mark.parametrize("role", ["member", "manager"])
def test_list_total_and_rows_each_bind_authenticated_team(role):
    member = _member(role=role)
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(2)])

    with _client(db, member) as client:
        listed = client.get("/api/customer-contacts")

    assert listed.status_code == 200
    assert len(db.statements) == 2
    for statement in db.statements:
        assert has_team_predicate(statement, CustomerCompany.team_id, member.team_id)


# ---- 담당자 범위: 팀원은 본인이 맡은 고객만 본다 ----
#
# 고객만 구조가 다르다. 담당자가 별도 표에 있어 대표 담당자 비교와 담당자 표 EXISTS 를
# or_ 로 묶는다(`customers._assigned_to`). 여기서는 최상위 OR 안의 대표 담당자 비교가
# 인증된 사용자에게 묶였는지 본다 — 그 조건이 사라지면 범위가 넓어진다.


def test_member_detail_is_scoped_to_contacts_they_own():
    member = _member(role="member")
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        client.get(f"/api/customer-contacts/{uuid4()}")

    assert has_owner_predicate(db.statements[0], CustomerContact.owner_member_id, member.id)


def test_manager_detail_is_not_narrowed_to_a_single_owner():
    manager = _member(role="manager")
    db = _Db(_Result(rows=[]))

    with _client(db, manager) as client:
        client.get(f"/api/customer-contacts/{uuid4()}")

    assert not has_owner_predicate(db.statements[0], CustomerContact.owner_member_id, manager.id)


def test_member_list_queries_are_each_scoped_to_their_own_contacts():
    member = _member(role="member")
    db = _Db(*[_Result(scalar=0, rows=[]) for _ in range(2)])

    with _client(db, member) as client:
        client.get("/api/customer-contacts")

    assert len(db.statements) == 2
    for statement in db.statements:
        assert has_owner_predicate(statement, CustomerContact.owner_member_id, member.id)
