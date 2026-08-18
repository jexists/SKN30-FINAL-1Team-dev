"""Supabase 사용자와 구성원을 잇는 명령 테스트.

DB 에 붙지 않는다. 세션을 대신하는 가짜 객체로 어떤 문장이 나가는지만 본다.
"""

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from scripts.link_demo_auth_users import (
    EMPTY_MANAGER_ID,
    EMPTY_MEMBER_ID,
    FILLED_MANAGER_ID,
    FILLED_MEMBER_ID,
    ROLES,
    TEST_MANAGER_ID,
    TEST_MEMBER_ID,
    build_parser,
    link_demo_auth_users,
    parse_assignments,
)

FILLED_MANAGER_UID = UUID("11111111-1111-4111-8111-111111111111")
FILLED_MEMBER_UID = UUID("22222222-2222-4222-8222-222222222222")
EMPTY_MANAGER_UID = UUID("33333333-3333-4333-8333-333333333333")
EMPTY_MEMBER_UID = UUID("44444444-4444-4444-8444-444444444444")


def _args(*, omit: tuple[str, ...] = (), **overrides) -> list[str]:
    values = {
        "--filled-manager": str(FILLED_MANAGER_UID),
        "--filled-member": str(FILLED_MEMBER_UID),
        "--empty-manager": str(EMPTY_MANAGER_UID),
        "--empty-member": str(EMPTY_MEMBER_UID),
    }
    values.update(overrides)
    for flag in omit:
        values.pop(flag)
    return [part for flag, value in values.items() for part in (flag, value)]


def _parse(*, omit: tuple[str, ...] = (), **overrides):
    return build_parser().parse_args(_args(omit=omit, **overrides))


# 데모 계정을 한 번에 다 만들지 않는 실제 상황: 데이터가 있는 팀 두 자리만 연결한다.
FILLED_ONLY = ("--empty-manager", "--empty-member")


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    """조회 두 번(대상 구성원, 이미 쓰인 UID) 뒤에 UPDATE 가 이어진다."""

    def __init__(self, rows, taken=()):
        self._results = iter([FakeResult(rows), FakeResult(list(taken))])
        self.updates = []
        self.rolled_back = False

    async def execute(self, statement):
        try:
            return next(self._results)
        except StopIteration:
            self.updates.append(statement)
            return FakeResult([])

    async def rollback(self):
        self.rolled_back = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    def begin(self):
        return self


def _rows(*, linked: dict[UUID, UUID] | None = None):
    linked = linked or {}
    names = {
        FILLED_MANAGER_ID: ("김서현", "manager"),
        FILLED_MEMBER_ID: ("김지훈", "member"),
        EMPTY_MANAGER_ID: ("김서현", "manager"),
        EMPTY_MEMBER_ID: ("김지훈", "member"),
    }
    return [
        SimpleNamespace(
            id=member_id,
            display_name=display_name,
            role_code=role_code,
            auth_user_id=linked.get(member_id),
        )
        for member_id, (display_name, role_code) in names.items()
    ]


def _run(session, assignments, *, dry_run: bool, monkeypatch):
    monkeypatch.setattr(
        "scripts.link_demo_auth_users.get_sessionmaker",
        lambda: lambda: session,
    )
    asyncio.run(link_demo_auth_users(assignments, dry_run=dry_run))


def test_roles_cover_only_the_login_accounts():
    assert [member_id for _name, _flag, member_id in ROLES] == [
        FILLED_MANAGER_ID,
        FILLED_MEMBER_ID,
        EMPTY_MANAGER_ID,
        EMPTY_MEMBER_ID,
        TEST_MANAGER_ID,
        TEST_MEMBER_ID,
    ]


def test_assignments_map_each_role_to_its_member():
    assert parse_assignments(_parse()) == {
        FILLED_MANAGER_ID: FILLED_MANAGER_UID,
        FILLED_MEMBER_ID: FILLED_MEMBER_UID,
        EMPTY_MANAGER_ID: EMPTY_MANAGER_UID,
        EMPTY_MEMBER_ID: EMPTY_MEMBER_UID,
    }


def test_duplicate_uuid_is_rejected():
    duplicated = _parse(**{"--empty-member": str(FILLED_MANAGER_UID)})

    with pytest.raises(SystemExit):
        parse_assignments(duplicated)


def test_malformed_uuid_is_rejected():
    with pytest.raises(SystemExit):
        parse_assignments(_parse(**{"--empty-member": "not-a-uuid"}))


def test_only_the_given_roles_are_assigned():
    assert parse_assignments(_parse(omit=FILLED_ONLY)) == {
        FILLED_MANAGER_ID: FILLED_MANAGER_UID,
        FILLED_MEMBER_ID: FILLED_MEMBER_UID,
    }


def test_no_role_at_all_is_rejected():
    with pytest.raises(SystemExit):
        parse_assignments(build_parser().parse_args([]))


def test_dry_run_does_not_write(monkeypatch, capsys):
    session = FakeSession(_rows())

    _run(session, parse_assignments(_parse()), dry_run=True, monkeypatch=monkeypatch)

    assert session.updates == []
    assert session.rolled_back
    assert "--dry-run" in capsys.readouterr().out


def test_apply_writes_one_update_per_member(monkeypatch):
    session = FakeSession(_rows())

    _run(session, parse_assignments(_parse()), dry_run=False, monkeypatch=monkeypatch)

    assert len(session.updates) == 4
    assert not session.rolled_back


def test_partial_run_touches_only_the_given_members(monkeypatch, capsys):
    assignments = parse_assignments(_parse(omit=FILLED_ONLY))
    session = FakeSession([row for row in _rows() if row.id in assignments])

    _run(session, assignments, dry_run=False, monkeypatch=monkeypatch)

    assert len(session.updates) == 2
    output = capsys.readouterr().out
    # 빠진 자리는 로그인할 수 없으므로 화면에 남겨 둔다.
    assert "--empty-manager" in output
    assert "--empty-member" in output
    assert "구성원 2명" in output


def test_rerun_with_the_same_uuids_is_unchanged(monkeypatch, capsys):
    assignments = parse_assignments(_parse())
    session = FakeSession(_rows(linked=assignments), taken=list(assignments.items()))

    _run(session, assignments, dry_run=False, monkeypatch=monkeypatch)

    assert len(session.updates) == 4
    assert "변경" not in capsys.readouterr().out


def test_uuid_already_linked_to_another_member_is_rejected(monkeypatch):
    session = FakeSession(_rows(), taken=[(uuid4(), FILLED_MANAGER_UID)])

    with pytest.raises(SystemExit):
        _run(session, parse_assignments(_parse()), dry_run=False, monkeypatch=monkeypatch)


def test_missing_member_row_is_rejected(monkeypatch):
    session = FakeSession([row for row in _rows() if row.id != EMPTY_MEMBER_ID])

    with pytest.raises(SystemExit):
        _run(session, parse_assignments(_parse()), dry_run=False, monkeypatch=monkeypatch)
