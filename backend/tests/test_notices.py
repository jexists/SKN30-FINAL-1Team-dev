from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member, Notice
from app.schemas.notices import NoticePageParams

NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
_MISSING = object()


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def _member(*, role: str = "member", team_id: UUID | None = None) -> Member:
    return Member(
        id=uuid4(),
        team_id=team_id or uuid4(),
        login_id=f"{uuid4()}@salesluv.demo",
        password_hash="unused",
        display_name="합성 영업 담당자",
        role_code=role,
        job_title="영업 담당자",
        active=True,
    )


def _notice(author: Member, *, recipient_id: UUID | None = None) -> Notice:
    return Notice(
        id=uuid4(),
        team_id=author.team_id,
        author_member_id=author.id,
        recipient_member_id=recipient_id,
        tag="공지",
        title="합성 공지",
        body="합성 본문",
        image_storage_key="team/secret-object-key.png",
        image_alt="합성 이미지",
        published_at=NOW,
        due_at=None,
        due_text=None,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_notice_page_params_reject_unsafe_values():
    with pytest.raises(ValidationError):
        NoticePageParams(scope="everyone")
    with pytest.raises(ValidationError):
        NoticePageParams(
            published_from="2026-08-17T00:00:00+09:00",
            published_to="2026-08-10T00:00:00+09:00",
        )
    with pytest.raises(ValidationError):
        NoticePageParams(limit=101)
    with pytest.raises(ValidationError):
        NoticePageParams(recipient_member_id=str(uuid4()))


def test_storage_key_is_never_exposed():
    member = _member()
    notice = _notice(member)
    db = _Db(_Result(rows=[(notice, member.display_name)]))

    with _client(db, member) as client:
        response = client.get(f"/api/notices/{notice.id}")

    assert response.status_code == 200
    body = response.json()
    assert "image_storage_key" not in body
    assert notice.image_storage_key not in response.text
    assert body["image_alt"] == "합성 이미지"


def test_scope_splits_team_notice_and_personal_directive():
    member = _member()
    team_notice = _notice(member)
    personal = _notice(member, recipient_id=member.id)

    team_db = _Db(_Result(scalar=1), _Result(rows=[(team_notice, member.display_name)]))
    with _client(team_db, member) as client:
        team = client.get("/api/notices?scope=team")
    assert team.status_code == 200
    assert team.json()["items"][0]["scope"] == "team"
    assert team.json()["items"][0]["recipient_member_id"] is None
    assert "public.notice.recipient_member_id IS NULL" in str(team_db.statements[0])

    personal_db = _Db(_Result(scalar=1), _Result(rows=[(personal, member.display_name)]))
    with _client(personal_db, member) as client:
        mine = client.get("/api/notices?scope=personal")
    assert mine.status_code == 200
    assert mine.json()["items"][0]["scope"] == "personal"
    assert mine.json()["items"][0]["recipient_member_id"] == str(member.id)

    sql = str(personal_db.statements[0])
    assert "public.notice.recipient_member_id =" in sql
    assert member.id in personal_db.statements[0].compile().params.values()


def test_default_scope_hides_other_members_directive():
    member = _member()
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        response = client.get("/api/notices")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0

    sql = str(db.statements[0])
    # 팀 공지이거나 내가 수신자인 지시만 보인다.
    assert "public.notice.recipient_member_id IS NULL OR public.notice.recipient_member_id =" in sql
    assert "public.notice.team_id =" in sql


def test_other_team_notice_is_hidden():
    member = _member()
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        response = client.get(f"/api/notices/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "notice_not_found"}
    assert member.team_id in db.statements[0].compile().params.values()
