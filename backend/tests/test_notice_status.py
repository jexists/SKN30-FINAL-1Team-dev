"""팀장 지시사항의 이행 여부.

수신자 본인만 자기 몫을 바꾼다. 팀장은 공지관리 화면에서 누가 어떻게 했는지 보기만 하고
팀원 대신 이행 처리하지 않는다. 그래야 이행 기록이 실제로 한 사람의 말이 된다.
"""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member, Notice, NoticeTarget
from app.schemas.notices import NoticeStatusWrite

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 28, 9, tzinfo=UTC)
_MISSING = object()


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None, scalar_values=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows
        self.scalar_values = [] if scalar_values is None else scalar_values

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        # 상태를 바꾼 뒤 다시 도는 조회라 값을 그때그때 만들어야 한다. 미리 만들어 두면
        # 바뀌기 전 값을 보게 된다.
        return self.rows() if callable(self.rows) else self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1

    async def commit(self):
        self.commit_count += 1

    async def rollback(self):
        self.rollback_count += 1


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _notice(author: Member, *, type_code: str = "DIRECTIVE") -> Notice:
    return Notice(
        id=uuid4(),
        team_id=author.team_id,
        author_member_id=author.id,
        type=type_code,
        tag="높음",
        title="신규 거래처 방문 일정 정리",
        body="<p>이번 주 신규 거래처 방문 일정을 정리해 주세요.</p>",
        image_storage_key=None,
        image_alt=None,
        published_at=NOW,
        due_at=None,
        due_text=None,
        display_start_date=date(2026, 8, 28),
        display_end_date=None,
        is_hidden=False,
        sort_order=0,
        updated_at=NOW,
        deleted_at=None,
    )


def _target(notice: Notice, member: Member, *, status_code: str = "pending") -> NoticeTarget:
    return NoticeTarget(
        notice_id=notice.id,
        member_id=member.id,
        created_at=NOW,
        status_code=status_code,
        status_reason=None,
        status_changed_at=None,
        status_changed_by_member_id=None,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def _read_results(notice: Notice, author: Member, target: NoticeTarget | None):
    """상태를 바꾼 뒤 응답을 다시 조립하며 도는 조회들.

    행을 미리 만들지 않고 불릴 때 만든다. 이 조회들은 상태를 바꾼 다음에 돌기 때문에
    미리 만들어 두면 바뀌기 전 값이 응답에 실린다.
    """

    def targets():
        if target is None:
            return []
        return [
            (
                notice.id,
                target.member_id,
                "합성 영업 담당자",
                target.status_code,
                target.status_reason,
                target.status_changed_at,
            )
        ]

    def mine():
        if target is None:
            return []
        return [(notice.id, target.status_code, target.status_reason, target.status_changed_at)]

    return (
        _Result(rows=[(notice, author.display_name)]),
        _Result(rows=targets),
        _Result(rows=mine),
    )


def test_reason_is_required_when_marking_not_done():
    with pytest.raises(ValidationError):
        NoticeStatusWrite(status_code="not_done")

    # 이행에는 사유가 필요 없다.
    assert NoticeStatusWrite(status_code="done").reason is None

    with pytest.raises(ValidationError):
        # 손대지 않은 상태로 되돌리지는 않는다.
        NoticeStatusWrite(status_code="pending")


def test_recipient_marks_a_directive_done():
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    notice = _notice(manager)
    target = _target(notice, teammate, status_code="not_done")
    target.status_reason = "거래처 일정 변경으로 방문하지 못함"

    db = _Db(
        _Result(rows=[(notice, manager.display_name)]),
        _Result(scalar=target),
        *_read_results(notice, manager, target),
    )
    with _client(db, teammate) as client:
        response = client.post(
            f"/api/notices/{notice.id}/status",
            headers={"Origin": ORIGIN},
            json={"status_code": "done"},
        )

    assert response.status_code == 200
    assert response.json()["my_status"]["status_code"] == "done"
    assert target.status_code == "done"
    # 이행으로 돌리면 지난 미이행 사유를 남겨 두지 않는다.
    assert target.status_reason is None
    assert target.status_changed_by_member_id == teammate.id
    assert target.status_changed_at is not None
    assert "FOR UPDATE" in str(db.statements[1])
    assert db.flush_count == db.commit_count == 1


def test_recipient_records_a_reason_when_not_done():
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    notice = _notice(manager)
    target = _target(notice, teammate)

    db = _Db(
        _Result(rows=[(notice, manager.display_name)]),
        _Result(scalar=target),
        *_read_results(notice, manager, target),
    )
    with _client(db, teammate) as client:
        response = client.post(
            f"/api/notices/{notice.id}/status",
            headers={"Origin": ORIGIN},
            json={
                "status_code": "not_done",
                "reason": "거래처 일정 변경으로 방문하지 못함",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["my_status"]["status_code"] == "not_done"
    assert body["my_status"]["status_reason"] == "거래처 일정 변경으로 방문하지 못함"
    assert target.status_reason == "거래처 일정 변경으로 방문하지 못함"


def test_someone_who_is_not_a_recipient_cannot_record_a_status():
    """팀장은 자기가 보낸 지시를 관리 목록에서 보지만 수신자는 아니다."""
    manager = _member(role="manager")
    notice = _notice(manager)

    db = _Db(
        _Result(rows=[(notice, manager.display_name)]),
        _Result(scalar=None),
    )
    with _client(db, manager) as client:
        response = client.post(
            f"/api/notices/{notice.id}/status",
            headers={"Origin": ORIGIN},
            json={"status_code": "done"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "notice_target_not_found"}
    assert db.commit_count == 0
    assert db.rollback_count == 1


def test_plain_notices_have_no_fulfilment_state():
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    notice = _notice(manager, type_code="NOTICE")

    db = _Db(_Result(rows=[(notice, manager.display_name)]))
    with _client(db, teammate) as client:
        response = client.post(
            f"/api/notices/{notice.id}/status",
            headers={"Origin": ORIGIN},
            json={"status_code": "done"},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "not_a_directive"}


def test_notice_read_carries_my_status_but_not_other_peoples():
    """티커가 자기 이행 배지를 세우는 값이다. 남의 상태는 여기로 나가지 않는다."""
    manager = _member(role="manager")
    teammate = _member(team_id=manager.team_id)
    notice = _notice(manager)
    target = _target(notice, teammate, status_code="done")
    target.status_changed_at = NOW

    db = _Db(*_read_results(notice, manager, target))
    with _client(db, teammate) as client:
        response = client.get(f"/api/notices/{notice.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["my_status"]["status_code"] == "done"
    # 자기 행만 고르는 조회여야 남의 이행 여부가 새지 않는다.
    assert teammate.id in db.statements[2].compile().params.values()


def test_editing_recipients_keeps_existing_fulfilment_records():
    """명단을 손봐도 그대로 남는 사람의 이행 기록은 지우지 않는다."""
    manager = _member(role="manager")
    staying = _member(team_id=manager.team_id)
    added = _member(team_id=manager.team_id)
    notice = _notice(manager)

    db = _Db(
        _Result(scalar=notice),
        _Result(scalar_values=[staying, added]),
        # 남길 사람을 제외한 삭제
        _Result(),
        # 이미 행이 있는 사람
        _Result(scalar_values=[staying.id]),
        _Result(rows=[(notice, manager.display_name)]),
        _Result(rows=[]),
    )
    with _client(db, manager) as client:
        response = client.patch(
            f"/api/notices/{notice.id}",
            headers={"Origin": ORIGIN},
            json={"target_member_ids": [str(staying.id), str(added.id)]},
        )

    assert response.status_code == 200
    # 새로 들어온 사람만 행을 만든다. 남는 사람의 행은 건드리지 않는다.
    assert [row.member_id for row in db.added] == [added.id]
    delete_sql = str(db.statements[2])
    assert "DELETE FROM public.notice_target" in delete_sql
    assert "NOT IN" in delete_sql
