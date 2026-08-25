from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.workspace import Member, Notice
from app.schemas.notices import NoticeManagePageParams, NoticePageParams

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
TODAY = date(2026, 8, 17)
_MISSING = object()


class _Result:
    def __init__(self, *, scalar=_MISSING, rows=None):
        self.scalar = scalar
        self.rows = [] if rows is None else rows

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalars(self):
        return self


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)

    def add(self, instance):
        self.added.append(instance)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


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


def _notice(author: Member, *, type: str = "NOTICE", **overrides) -> Notice:
    fields = {
        "id": uuid4(),
        "team_id": author.team_id,
        "author_member_id": author.id,
        "type": type,
        "tag": "공지",
        "title": "합성 공지",
        "body": "<p>합성 본문</p>",
        "image_storage_key": "team/secret-object-key.png",
        "image_alt": "합성 이미지",
        "published_at": NOW,
        "due_at": None,
        "due_text": None,
        "display_start_date": TODAY,
        "display_end_date": None,
        "is_hidden": False,
        "sort_order": 0,
        "updated_at": NOW,
        "deleted_at": None,
    }
    fields.update(overrides)
    return Notice(**fields)


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
        NoticePageParams(type="EVERYONE")
    with pytest.raises(ValidationError):
        NoticePageParams(
            published_from="2026-08-17T00:00:00+09:00",
            published_to="2026-08-10T00:00:00+09:00",
        )
    with pytest.raises(ValidationError):
        NoticePageParams(limit=31)
    with pytest.raises(ValidationError):
        NoticePageParams(recipient_member_id=str(uuid4()))


def test_scope_and_type_filters_must_agree():
    """옛 어휘와 새 어휘를 함께 보내면서 서로 다른 것을 가리키면 거절한다."""
    with pytest.raises(ValidationError):
        NoticePageParams(scope="team", type="DIRECTIVE")
    assert NoticePageParams(scope="team", type="NOTICE").type == "NOTICE"


def test_manage_page_params_reject_unsafe_values():
    with pytest.raises(ValidationError):
        NoticeManagePageParams(limit=31)
    with pytest.raises(ValidationError):
        NoticeManagePageParams(type="EVERYONE")
    # 팀장 화면은 숨긴 것도 기본으로 함께 본다.
    assert NoticeManagePageParams().include_hidden is True


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
    personal = _notice(member, type="DIRECTIVE")

    team_db = _Db(_Result(scalar=1), _Result(rows=[(team_notice, member.display_name)]))
    with _client(team_db, member) as client:
        team = client.get("/api/notices?scope=team")
    assert team.status_code == 200
    assert team.json()["items"][0]["scope"] == "team"
    assert team.json()["items"][0]["type"] == "NOTICE"
    assert team.json()["items"][0]["recipient_member_id"] is None
    assert "public.notice.type = " in str(team_db.statements[0])

    personal_db = _Db(
        _Result(scalar=1),
        _Result(rows=[(personal, member.display_name)]),
        # 지시는 수신자를 한 번 더 읽는다.
        _Result(rows=[(personal.id, member.id, member.display_name)]),
    )
    with _client(personal_db, member) as client:
        mine = client.get("/api/notices?scope=personal")
    assert mine.status_code == 200
    assert mine.json()["items"][0]["scope"] == "personal"
    assert mine.json()["items"][0]["type"] == "DIRECTIVE"
    # 수신자가 한 명이면 옛 필드도 그 사람을 가리킨다.
    assert mine.json()["items"][0]["recipient_member_id"] == str(member.id)

    sql = str(personal_db.statements[0])
    assert "EXISTS (SELECT public.notice_target.member_id" in sql
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
    assert "public.notice.type = " in sql
    assert "EXISTS (SELECT public.notice_target.member_id" in sql
    assert "public.notice.team_id =" in sql


def test_hidden_expired_and_deleted_notices_are_invisible():
    """팀원 목록은 지운 것, 숨긴 것, 노출 기간 밖을 모두 걷어낸다."""
    member = _member()
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, member) as client:
        assert client.get("/api/notices").status_code == 200

    sql = str(db.statements[0])
    assert "public.notice.deleted_at IS NULL" in sql
    assert "public.notice.is_hidden IS false" in sql
    assert "public.notice.display_start_date <=" in sql
    assert "public.notice.display_end_date IS NULL OR public.notice.display_end_date >=" in sql


def test_other_team_notice_is_hidden():
    member = _member()
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        response = client.get(f"/api/notices/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "notice_not_found"}
    assert member.team_id in db.statements[0].compile().params.values()


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/notices/manage", None),
        ("get", f"/api/notices/manage/{uuid4()}", None),
        ("post", "/api/notices", {"type": "NOTICE", "title": "제목", "body": "<p>본문</p>"}),
        ("patch", f"/api/notices/{uuid4()}", {"title": "제목"}),
        ("delete", f"/api/notices/{uuid4()}", None),
    ],
)
def test_writing_and_managing_requires_manager(method, path, payload):
    member = _member(role="member")
    db = _Db()

    with _client(db, member) as client:
        response = getattr(client, method)(
            path, headers={"Origin": ORIGIN}, **({"json": payload} if payload else {})
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "manager_required"}
    assert db.statements == []


def test_manage_route_is_not_shadowed_by_the_id_route():
    """/notices/manage 가 /notices/{notice_id} 아래에 있으면 UUID 로 읽혀 422 가 난다."""
    member = _member(role="member")
    db = _Db()

    with _client(db, member) as client:
        response = client.get("/api/notices/manage")

    assert response.status_code == 403


def test_manage_list_keeps_hidden_and_ignores_display_period():
    manager = _member(role="manager")
    hidden = _notice(manager, is_hidden=True, display_end_date=date(2026, 1, 1))
    db = _Db(_Result(scalar=1), _Result(rows=[(hidden, manager.display_name)]))

    with _client(db, manager) as client:
        response = client.get("/api/notices/manage")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["is_hidden"] is True
    # 목록은 본문을 싣지 않는다. 사진마다 서명 URL 을 발급하게 되기 때문이다.
    assert "body" not in item

    sql = str(db.statements[0])
    assert "public.notice.deleted_at IS NULL" in sql
    assert "is_hidden" not in sql
    assert "display_start_date" not in sql


def test_manage_list_can_hide_hidden_notices():
    manager = _member(role="manager")
    db = _Db(_Result(scalar=0), _Result(rows=[]))

    with _client(db, manager) as client:
        assert client.get("/api/notices/manage?include_hidden=false").status_code == 200

    assert "public.notice.is_hidden IS false" in str(db.statements[0])


def test_create_notice_stores_sanitized_body():
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.post(
            "/api/notices",
            headers={"Origin": ORIGIN},
            json={
                "type": "NOTICE",
                "title": "합성 공지",
                "body": '<p>안녕</p><script>alert(1)</script><img src="https://evil.example/x.png">',
                "sort_order": -10,
            },
        )

    assert response.status_code == 201
    assert response.headers["Location"].startswith("/api/notices/")
    assert db.committed is True

    body = response.json()["body"]
    assert "script" not in body
    assert "evil.example" not in body
    assert "<p>안녕</p>" in body
    assert response.json()["sort_order"] == -10
    assert response.json()["targets"] == []
    # 오늘부터 무기한이 기본이다.
    assert response.json()["display_end_date"] is None


def test_create_notice_rejects_body_that_is_only_markup():
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.post(
            "/api/notices",
            headers={"Origin": ORIGIN},
            json={"type": "NOTICE", "title": "합성 공지", "body": "<script>alert(1)</script>"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "notice_body_empty"}
    assert db.committed is False


def test_create_directive_requires_targets():
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.post(
            "/api/notices",
            headers={"Origin": ORIGIN},
            json={
                "type": "DIRECTIVE",
                "title": "합성 지시",
                "body": "<p>본문</p>",
                "target_member_ids": [],
            },
        )

    assert response.status_code == 422
    assert db.committed is False


def test_create_notice_rejects_targets():
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.post(
            "/api/notices",
            headers={"Origin": ORIGIN},
            json={
                "type": "NOTICE",
                "title": "합성 공지",
                "body": "<p>본문</p>",
                "target_member_ids": [str(uuid4())],
            },
        )

    assert response.status_code == 422
    assert db.committed is False


def test_create_directive_rejects_member_outside_the_team():
    manager = _member(role="manager")
    # 같은 팀에서 찾지 못하면 빈 결과가 돌아온다.
    db = _Db(_Result(rows=[]))

    with _client(db, manager) as client:
        response = client.post(
            "/api/notices",
            headers={"Origin": ORIGIN},
            json={
                "type": "DIRECTIVE",
                "title": "합성 지시",
                "body": "<p>본문</p>",
                "target_member_ids": [str(uuid4())],
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "notice_target_member_not_found"}
    assert db.committed is False


def test_create_notice_rejects_reversed_display_range():
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.post(
            "/api/notices",
            headers={"Origin": ORIGIN},
            json={
                "type": "NOTICE",
                "title": "합성 공지",
                "body": "<p>본문</p>",
                "display_start_date": "2026-08-20",
                "display_end_date": "2026-08-10",
            },
        )

    assert response.status_code == 422
    assert db.committed is False


def test_end_date_before_today_is_rejected_when_start_is_omitted():
    """시작일을 생략하면 스키마가 범위를 보지 못한다. 라우터가 오늘로 채운 뒤 다시 본다."""
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.post(
            "/api/notices",
            headers={"Origin": ORIGIN},
            json={
                "type": "NOTICE",
                "title": "합성 공지",
                "body": "<p>본문</p>",
                "display_end_date": "2020-01-01",
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_notice_display_range"}


def test_patch_cannot_turn_a_notice_into_a_directive_without_targets():
    manager = _member(role="manager")
    notice = _notice(manager)
    db = _Db(_Result(rows=[notice]))

    with _client(db, manager) as client:
        response = client.patch(
            f"/api/notices/{notice.id}",
            headers={"Origin": ORIGIN},
            json={"type": "DIRECTIVE"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "directive_target_required"}
    assert db.rolled_back is True
    assert db.committed is False


def test_patch_rejects_explicit_nulls_on_required_fields():
    manager = _member(role="manager")
    db = _Db()

    with _client(db, manager) as client:
        response = client.patch(
            f"/api/notices/{uuid4()}",
            headers={"Origin": ORIGIN},
            json={"title": None},
        )

    assert response.status_code == 422


def test_delete_is_soft():
    manager = _member(role="manager")
    notice = _notice(manager)
    db = _Db(_Result(rows=[notice]))

    with _client(db, manager) as client:
        response = client.delete(f"/api/notices/{notice.id}", headers={"Origin": ORIGIN})

    assert response.status_code == 204
    assert notice.deleted_at is not None
    assert notice.updated_at is not None
    assert db.committed is True
    # 행을 실제로 지우지 않는다.
    assert "DELETE FROM" not in " ".join(str(statement) for statement in db.statements)
