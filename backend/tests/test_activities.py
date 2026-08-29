from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.configuration import ActivityActionTag, ActivityCategory
from app.models.crm import Activity, CustomerCompany, CustomerContact
from app.models.sales import Product
from app.models.workspace import Member
from app.schemas.activities import ActivityCreate, ActivityPageParams, ActivityPatch
from app.services import agent_runs as agent_run_service
from app.services import contract_schedule_snapshots

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, tzinfo=UTC)
START = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
END = datetime(2026, 8, 17, 2, 0, tzinfo=UTC)
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

    def scalar_one(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def scalar_one_or_none(self):
        assert self.scalar is not _MISSING
        return self.scalar

    def one_or_none(self):
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result, flush_error: Exception | None = None):
        self.results = list(results)
        self.flush_error = flush_error
        self.statements = []
        self.added = []
        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flush_count += 1
        if self.flush_error is not None:
            raise self.flush_error
        for value in self.added:
            if isinstance(value, Activity):
                value.created_at = value.created_at or NOW
                value.updated_at = value.updated_at or NOW

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


def _company(team_id: UUID) -> CustomerCompany:
    return CustomerCompany(
        id=uuid4(),
        team_id=team_id,
        name="합성 고객사",
        region_code="seoul",
        created_at=NOW,
    )


def _contact(company_id: UUID, owner_id: UUID) -> CustomerContact:
    return CustomerContact(
        id=uuid4(),
        company_id=company_id,
        owner_member_id=owner_id,
        name="합성 고객",
        department="영업부",
        job_title="팀장",
        email=None,
        phone="02-000-0000",
        customer_contact_status_id=None,
        source_code=None,
        memo=None,
        registered_at=NOW,
    )


def _product(team_id: UUID) -> Product:
    return Product(id=uuid4(), team_id=team_id, name="합성 상품", active=True)


def _activity(member: Member, *, contact_id: UUID | None = None, product_id: UUID | None = None):
    return Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        customer_contact_id=contact_id,
        end_user_contact_id=None,
        activity_category_id=uuid4(),
        title="합성 미팅",
        starts_at=START,
        ends_at=END,
        all_day=False,
        due_at=None,
        location="회의실",
        activity_action_tag_id=uuid4(),
        completed_at=None,
        note="합성 메모",
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
        product_id=product_id,
        sales_deal_id=None,
        purchase_order_id=None,
    )


def _category(
    team_id: UUID,
    *,
    code: str = "visit",
    deleted_at: datetime | None = None,
) -> ActivityCategory:
    return ActivityCategory(
        id=uuid4(),
        team_id=team_id,
        code=code,
        name="방문",
        tone="blue",
        position=1,
        deleted_at=deleted_at,
        created_at=NOW,
        updated_at=NOW,
    )


def _action_tag(
    team_id: UUID,
    *,
    code: str = "meeting",
    deleted_at: datetime | None = None,
) -> ActivityActionTag:
    return ActivityActionTag(
        id=uuid4(),
        team_id=team_id,
        code=code,
        name="미팅",
        tone="violet",
        position=1,
        deleted_at=deleted_at,
        created_at=NOW,
        updated_at=NOW,
    )


def _row(
    activity: Activity,
    owner: Member,
    contact: CustomerContact | None = None,
    company: CustomerCompany | None = None,
    product: Product | None = None,
    category: ActivityCategory | None = None,
    action_tag: ActivityActionTag | None | object = _MISSING,
):
    category = category or _category(owner.team_id)
    if action_tag is _MISSING:
        action_tag = _action_tag(owner.team_id)
    return (
        activity,
        owner.display_name,
        contact,
        None if company is None else company.id,
        None if company is None else company.name,
        None if product is None else product.name,
        category,
        action_tag,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def test_activity_request_sales_deal_rejects_unsafe_values():
    payload = ActivityCreate(
        category_code="education",
        title="  합성 미팅  ",
        starts_at="2026-08-17T10:00:00+09:00",
        ends_at="2026-08-17T11:00:00+09:00",
        action_tag="demo_completed",
    )

    assert payload.title == "합성 미팅"
    assert (
        ActivityCreate(
            category_code="custom_category",
            title="합성 미팅",
            starts_at="2026-08-17T10:00:00+09:00",
            action_tag="custom_action",
        ).action_tag
        == "custom_action"
    )
    assert ActivityPatch(note=None).model_dump(exclude_unset=True) == {"note": None}
    assert ActivityPageParams(start_date="2026-08-17").end_date is None

    invalid_payloads = (
        {"owner_member_id": str(uuid4())},
        {"category_code": "Bad-Code"},
        {"action_tag": "bad__code"},
        {"action_tag": "데모 완료"},
        {"starts_at": "2026-08-17T10:00:00"},
        {"starts_at": "2026-08-17T01:00:00Z"},
        {"starts_at": "9999-12-31T15:00:00+00:00"},
        {"ends_at": "2026-08-17T09:00:00+09:00"},
    )
    base = {
        "category_code": "visit",
        "title": "합성 미팅",
        "starts_at": "2026-08-17T10:00:00+09:00",
        "ends_at": "2026-08-17T11:00:00+09:00",
    }
    for invalid in invalid_payloads:
        with pytest.raises(ValidationError):
            ActivityCreate(**(base | invalid))
    with pytest.raises(ValidationError):
        ActivityPatch(title=None)
    with pytest.raises(ValidationError):
        ActivityPageParams(start_date="2026-08-18", end_date="2026-08-17")
    with pytest.raises(ValidationError):
        ActivityPageParams(start_date="9999-12-31")
    with pytest.raises(ValidationError):
        ActivityPageParams(start_date="2026-08-17", skip=9_223_372_036_854_775_808)


def test_member_cannot_link_another_owners_customer_contact():
    member = _member()
    other_owner = _member(team_id=member.team_id)
    company = _company(member.team_id)
    contact = _contact(company.id, other_owner.id)
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "customer_contact_id": str(contact.id),
                "category_code": "visit",
                "title": "다른 담당자의 고객 일정",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "customer_contact_not_found"}
    assert member.id in db.statements[0].compile().params.values()
    assert not db.added


def test_member_list_is_owner_date_and_soft_delete_scoped():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    product = _product(member.team_id)
    activity = _activity(member, contact_id=contact.id, product_id=product.id)
    category = _category(member.team_id, deleted_at=NOW)
    action_tag = _action_tag(member.team_id, deleted_at=NOW)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(activity, member, contact, company, product, category, action_tag)]),
    )

    with _client(db, member) as client:
        response = client.get(
            "/api/activities",
            params={"start_date": "2026-08-17", "limit": 30},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(activity.id)
    assert response.json()["items"][0]["owner_member_id"] == str(member.id)
    assert response.json()["items"][0]["starts_at"].endswith("+09:00")
    assert response.json()["items"][0]["customer_company_name"] == company.name
    assert response.json()["items"][0]["product_name"] == product.name
    assert response.json()["items"][0]["category_code"] == "visit"
    assert response.json()["items"][0]["action_tag"] == "meeting"
    assert response.json()["items"][0]["activity_category_id"] == str(category.id)
    assert response.json()["items"][0]["activity_category_name"] == category.name
    assert response.json()["items"][0]["activity_category_tone"] == category.tone
    assert response.json()["items"][0]["activity_action_tag_id"] == str(action_tag.id)
    assert response.json()["items"][0]["activity_action_tag_name"] == action_tag.name
    assert response.json()["items"][0]["activity_action_tag_tone"] == action_tag.tone
    for statement in db.statements:
        sql = str(statement)
        assert "activity.deleted_at IS NULL" in sql
        assert "activity_category.deleted_at IS NULL" not in sql
        assert "activity_action_tag.deleted_at IS NULL" not in sql
        assert member.id in statement.compile().params.values()
        assert member.team_id in statement.compile().params.values()

    denied_db = _Db()
    with _client(denied_db, member) as client:
        denied = client.get(
            "/api/activities",
            params=[("start_date", "2026-08-17"), ("owner_member_id", str(member.id))],
        )
        unknown = client.get("/api/activities?start_date=2026-08-17&unknown=true")
    assert denied.status_code == 403
    assert denied.json() == {"detail": "scope_not_allowed"}
    assert unknown.status_code == 422
    assert not denied_db.statements


def test_manager_owner_filter_is_limited_to_active_same_team_members():
    manager = _member(role="manager")
    owner = _member(team_id=manager.team_id)
    activity = _activity(owner)
    db = _Db(
        _Result(scalar_values=[owner.id]),
        _Result(scalar=1),
        _Result(rows=[_row(activity, owner)]),
    )

    with _client(db, manager) as client:
        response = client.get(
            "/api/activities",
            params=[
                ("start_date", "2026-08-17"),
                ("owner_member_id", str(owner.id)),
            ],
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["owner_member_id"] == str(owner.id)
    parameter_values = db.statements[1].compile().params.values()
    assert any(
        owner.id in value for value in parameter_values if isinstance(value, (list, tuple, set))
    )
    assert manager.id not in db.statements[1].compile().params.values()

    invalid_db = _Db(_Result(scalar_values=[]))
    with _client(invalid_db, manager) as client:
        invalid = client.get(
            "/api/activities",
            params=[
                ("start_date", "2026-08-17"),
                ("owner_member_id", str(uuid4())),
            ],
        )
    assert invalid.status_code == 403
    assert invalid.json() == {"detail": "scope_not_allowed"}
    assert len(invalid_db.statements) == 1


def test_create_uses_authenticated_owner_and_same_team_references():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    product = _product(member.team_id)
    category = _category(member.team_id, code="demo")
    action_tag = _action_tag(member.team_id, code="demo_in_progress")
    db = _Db(
        _Result(rows=[(contact, company.id, company.name)]),
        _Result(scalar=product),
        _Result(scalar=category),
        _Result(scalar=action_tag),
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "customer_contact_id": str(contact.id),
                "product_id": str(product.id),
                "category_code": "demo",
                "title": "  합성 데모  ",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "ends_at": "2026-08-17T11:00:00+09:00",
                "action_tag": "demo_in_progress",
            },
        )

    assert response.status_code == 201
    assert response.json()["owner_member_id"] == str(member.id)
    assert response.json()["owner_display_name"] == member.display_name
    assert response.json()["customer_contact_name"] == contact.name
    assert response.json()["product_name"] == product.name
    assert response.headers["location"] == f"/api/activities/{response.json()['id']}"
    activity = db.added[0]
    assert activity.team_id == member.team_id
    assert activity.owner_member_id == member.id
    assert activity.activity_category_id == category.id
    assert activity.activity_action_tag_id == action_tag.id
    assert response.json()["activity_category_name"] == category.name
    assert response.json()["activity_action_tag_name"] == action_tag.name
    assert activity.title == "합성 데모"
    assert db.flush_count == db.commit_count == 1
    assert db.rollback_count == 0
    assert member.team_id in db.statements[0].compile().params.values()
    assert member.team_id in db.statements[1].compile().params.values()

    hidden_db = _Db(_Result(rows=[]))
    with _client(hidden_db, member) as client:
        hidden = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "customer_contact_id": str(uuid4()),
                "category_code": "visit",
                "title": "타팀 고객 일정",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "customer_contact_not_found"}
    assert hidden_db.rollback_count == 1
    assert not hidden_db.added


def test_activity_options_reject_other_team_or_deleted_lookups():
    member = _member()
    category_db = _Db(_Result(scalar=None))
    with _client(category_db, member) as client:
        other_team_category = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "other_team_category",
                "title": "합성 미팅",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    action_db = _Db(_Result(scalar=_category(member.team_id)), _Result(scalar=None))
    with _client(action_db, member) as client:
        deleted_action = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "visit",
                "action_tag": "deleted_action",
                "title": "합성 미팅",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    activity = _activity(member)
    patch_db = _Db(_Result(scalar=activity), _Result(scalar=None))
    with _client(patch_db, member) as client:
        deleted_category = client.patch(
            f"/api/activities/{activity.id}",
            headers={"Origin": ORIGIN},
            json={"category_code": "deleted_category"},
        )

    assert other_team_category.status_code == deleted_category.status_code == 422
    assert (
        other_team_category.json()
        == deleted_category.json()
        == {"detail": "activity_category_code_not_found"}
    )
    assert deleted_action.status_code == 422
    assert deleted_action.json() == {"detail": "activity_action_tag_code_not_found"}

    checks = (
        (category_db.statements[0], "other_team_category", "activity_category"),
        (action_db.statements[1], "deleted_action", "activity_action_tag"),
        (patch_db.statements[1], "deleted_category", "activity_category"),
    )
    for statement, code, table in checks:
        sql = str(statement)
        values = statement.compile().params.values()
        assert f"{table}.deleted_at IS NULL" in sql
        assert member.team_id in values
        assert code in values


def test_member_cannot_link_another_owners_sales_deal():
    member = _member()
    sales_deal_id = uuid4()
    db = _Db(_Result(scalar=None))

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "sales_deal_id": str(sales_deal_id),
                "category_code": "visit",
                "title": "합성 미팅",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "sales_deal_not_found"}
    statement = db.statements[0]
    assert "sales_deal.owner_member_id" in str(statement)
    assert member.id in statement.compile().params.values()
    assert member.team_id in statement.compile().params.values()
    assert db.rollback_count == 1


def test_activity_options_are_active_same_team_and_ordered():
    member = _member()
    category = _category(member.team_id, code="custom_category")
    action_tag = _action_tag(member.team_id, code="custom_action")
    db = _Db(
        _Result(scalar_values=[category]),
        _Result(scalar_values=[action_tag]),
    )

    with _client(db, member) as client:
        categories = client.get("/api/activity-categories")
        action_tags = client.get("/api/activity-action-tags")

    assert categories.status_code == action_tags.status_code == 200
    assert categories.json()[0]["code"] == category.code
    assert action_tags.json()[0]["code"] == action_tag.code
    for statement, table in zip(
        db.statements,
        ("activity_category", "activity_action_tag"),
        strict=True,
    ):
        sql = str(statement)
        values = statement.compile().params.values()
        assert f"{table}.deleted_at IS NULL" in sql
        assert f"ORDER BY public.{table}.position" in sql
        assert member.team_id in values


def test_detail_and_patch_share_scope_and_patch_revalidates_range():
    member = _member()
    activity = _activity(member)
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    detail_db = _Db(
        _Result(rows=[_row(activity, member)]),
        _Result(scalar=None),  # 연결된 AI 브리핑 없음
    )
    with _client(detail_db, member) as client:
        detail = client.get(f"/api/activities/{activity.id}")
    assert detail.status_code == 200

    patch_db = _Db(
        _Result(scalar=activity),
        _Result(rows=[(contact, company.id, company.name)]),
        _Result(rows=[_row(activity, member, contact, company)]),
    )
    with _client(patch_db, member) as client:
        updated = client.patch(
            f"/api/activities/{activity.id}",
            headers={"Origin": ORIGIN},
            json={
                "customer_contact_id": str(contact.id),
                "starts_at": "2026-08-17T12:00:00+09:00",
                "ends_at": None,
                "note": None,
            },
        )
    assert updated.status_code == 200
    assert updated.json()["customer_contact_id"] == str(contact.id)
    assert updated.json()["ends_at"] is None
    assert updated.json()["note"] is None
    assert activity.updated_at > NOW
    assert "FOR UPDATE" in str(patch_db.statements[0])
    assert patch_db.flush_count == patch_db.commit_count == 1

    invalid_activity = _activity(member)
    invalid_db = _Db(_Result(scalar=invalid_activity))
    with _client(invalid_db, member) as client:
        invalid = client.patch(
            f"/api/activities/{invalid_activity.id}",
            headers={"Origin": ORIGIN},
            json={"starts_at": "2026-08-17T12:00:00+09:00"},
        )
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "invalid_activity_range"}
    assert invalid_db.flush_count == invalid_db.commit_count == 0
    assert invalid_db.rollback_count == 1


def test_cross_team_activity_is_hidden_and_delete_is_soft():
    member = _member()
    hidden_db = _Db(_Result(rows=[]), _Result(scalar=None))
    activity_id = uuid4()
    with _client(hidden_db, member) as client:
        hidden_detail = client.get(f"/api/activities/{activity_id}")
        hidden_delete = client.delete(
            f"/api/activities/{activity_id}",
            headers={"Origin": ORIGIN},
        )
    assert hidden_detail.status_code == hidden_delete.status_code == 404
    assert hidden_detail.json() == hidden_delete.json() == {"detail": "activity_not_found"}
    assert hidden_db.rollback_count == 1

    activity = _activity(member)
    delete_db = _Db(_Result(scalar=activity))
    with _client(delete_db, member) as client:
        deleted = client.delete(
            f"/api/activities/{activity.id}",
            headers={"Origin": ORIGIN},
        )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert activity.deleted_at is not None
    assert activity.updated_at == activity.deleted_at
    assert delete_db.flush_count == delete_db.commit_count == 1
    assert "FOR UPDATE" in str(delete_db.statements[0])


def test_write_failure_rolls_back_transaction():
    member = _member()
    db = _Db(
        _Result(scalar=_category(member.team_id)),
        flush_error=RuntimeError("synthetic failure"),
    )

    with _client(db, member) as client, pytest.raises(RuntimeError, match="synthetic failure"):
        client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "visit",
                "title": "합성 일정",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    assert db.commit_count == 0
    assert db.rollback_count == 1


def test_schedule_management_run_id_queues_briefing_after_activity_commit(monkeypatch):
    """AI 추천 후보를 승인해서 등록하면 등록 성공 뒤 브리핑 실행이 자동으로 큐잉된다."""
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))
    scheduled: list[UUID] = []

    async def _fake_execute(run_id: UUID) -> None:
        scheduled.append(run_id)

    monkeypatch.setattr(agent_run_service, "execute", _fake_execute)

    async def _fake_build_briefing_snapshot(db, member, activity_id):
        return {"customer_company": {"id": "company-1", "name": "합성 고객사"}}

    monkeypatch.setattr(
        contract_schedule_snapshots, "build_briefing_snapshot", _fake_build_briefing_snapshot
    )

    member = _member()
    category = _category(member.team_id, code="demo")
    parent_run = SimpleNamespace(
        id=uuid4(),
        team_id=member.team_id,
        agent_code="schedule_management",
        status_code="completed",
    )
    db = _Db(
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=None),  # agent_runs 멱등키 조회: 기존 실행 없음
        _Result(scalar=parent_run),  # _parent_run_or_409
        _Result(scalar=None),  # contract_next_meeting_suggestion 조회: 해당 없음
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "schedule_management_run_id": str(parent_run.id),
            },
        )

    assert response.status_code == 201
    assert response.json()["briefing_queue_warning"] is None
    assert len(db.added) == 2
    briefing_run = db.added[1]
    assert briefing_run.agent_code == "contract_management_briefing"
    assert briefing_run.parent_run_id == parent_run.id
    assert briefing_run.source_refs["activity_id"] == str(db.added[0].id)
    assert scheduled == [briefing_run.id]
    assert db.commit_count == 2
    assert db.rollback_count == 0


def test_schedule_management_run_id_failure_surfaces_warning_but_keeps_activity(monkeypatch):
    """브리핑 큐잉이 실패해도 이미 커밋된 일정 등록은 되돌리지 않고 경고만 응답에 싣는다."""
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))

    member = _member()
    category = _category(member.team_id, code="demo")
    missing_run_id = uuid4()
    db = _Db(
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=None),  # agent_runs 멱등키 조회: 기존 실행 없음
        _Result(scalar=None),  # _parent_run_or_409: 부모 실행을 찾지 못함
        _Result(scalar=None),  # contract_next_meeting_suggestion 조회: 해당 없음
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "schedule_management_run_id": str(missing_run_id),
            },
        )

    assert response.status_code == 201
    assert response.json()["briefing_queue_warning"] == "parent_run_not_found"
    assert len(db.added) == 1
    assert db.commit_count == 1
    assert db.rollback_count == 1


def test_patch_cannot_set_completed_at():
    """완료 여부는 전용 endpoint 로만 바꾼다. 일반 PATCH 는 받지 않는다."""
    with pytest.raises(ValidationError):
        ActivityPatch(completed_at="2026-08-17T10:00:00+09:00")


def test_complete_sets_completed_at():
    member = _member()
    activity = _activity(member)

    complete_db = _Db(
        _Result(scalar=activity),
        _Result(rows=[_row(activity, member)]),
    )
    with _client(complete_db, member) as client:
        completed = client.post(
            f"/api/activities/{activity.id}/complete",
            headers={"Origin": ORIGIN},
        )
    assert completed.status_code == 200
    assert completed.json()["completed_at"] is not None
    assert activity.completed_at is not None
    assert activity.updated_at == activity.completed_at
    assert "FOR UPDATE" in str(complete_db.statements[0])
    assert complete_db.flush_count == complete_db.commit_count == 1


def test_complete_rejects_already_completed():
    member = _member()
    done = _activity(member)
    done.completed_at = NOW

    repeat_db = _Db(_Result(scalar=done))
    with _client(repeat_db, member) as client:
        repeated = client.post(
            f"/api/activities/{done.id}/complete",
            headers={"Origin": ORIGIN},
        )
    assert repeated.status_code == 409
    assert repeated.json() == {"detail": "already_completed"}
    assert repeat_db.commit_count == 0
    assert repeat_db.rollback_count == 1


def test_reopen_endpoint_does_not_exist():
    """유스케이스는 완료만 정의한다. 재개 endpoint 를 두지 않는다."""
    member = _member()
    with _client(_Db(), member) as client:
        response = client.post(
            f"/api/activities/{uuid4()}/reopen",
            headers={"Origin": ORIGIN},
        )
    assert response.status_code == 404


def test_complete_hides_other_scope_activity():
    member = _member()
    hidden_db = _Db(_Result(scalar=None))
    with _client(hidden_db, member) as client:
        hidden = client.post(
            f"/api/activities/{uuid4()}/complete",
            headers={"Origin": ORIGIN},
        )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "activity_not_found"}
    assert hidden_db.commit_count == 0
    assert hidden_db.rollback_count == 1


def test_follow_up_filters_drop_the_date_range_and_sort_by_due():
    """미완료 후속업무는 기간이 아니라 상태로 묶는다. 대시보드 카드와 같은 조건이라야 한다."""
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    product = _product(member.team_id)
    activity = _activity(member, contact_id=contact.id, product_id=product.id)
    db = _Db(
        _Result(scalar=1),
        _Result(
            rows=[
                _row(
                    activity,
                    member,
                    contact,
                    company,
                    product,
                    _category(member.team_id),
                    _action_tag(member.team_id),
                )
            ]
        ),
    )

    with _client(db, member) as client:
        response = client.get(
            "/api/activities",
            params=[
                ("completed", "false"),
                ("sort", "due_at"),
            ],
        )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    sql = str(db.statements[-1])
    # 대시보드 후속업무 카드가 세는 조건과 글자 그대로 같아야 한다.
    assert "activity.completed_at IS NULL" in sql
    assert "activity.starts_at >=" not in sql
    assert "ORDER BY public.activity.due_at, public.activity.id" in sql


def test_end_date_without_start_date_is_rejected():
    member = _member()
    db = _Db()
    with _client(db, member) as client:
        response = client.get("/api/activities?end_date=2026-08-17")
    assert response.status_code == 422
    assert not db.statements
