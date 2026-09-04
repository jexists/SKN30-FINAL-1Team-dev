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
from app.models.agent import ContractNextMeetingSuggestion
from app.models.configuration import ActivityActionTag, ActivityCategory
from app.models.crm import Activity, CustomerCompany, CustomerContact
from app.models.sales import Product, SalesDeal
from app.models.workspace import Member
from app.schemas.activities import ActivityCreate, ActivityPageParams, ActivityPatch
from app.services import agent_runs as agent_run_service
from app.services import contract_next_meeting_pipeline, contract_schedule_snapshots

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


def _deal(*, team_id: UUID, company_id: UUID, owner_id: UUID) -> SalesDeal:
    """일정에 붙일 딜. 고객사가 일정의 고객사와 같아야 등록이 통과한다."""
    return SalesDeal(
        id=uuid4(),
        team_id=team_id,
        deal_no="SL-DL-TEST-0001",
        customer_company_id=company_id,
        customer_contact_id=uuid4(),
        owner_member_id=owner_id,
        deleted_at=None,
    )


def _activity(
    member: Member,
    *,
    contact_id: UUID | None = None,
    product_id: UUID | None = None,
    sales_deal_id: UUID | None = None,
    company_id: UUID | None = None,
):
    # 20260903_0020 뒤로 딜도 고객사도 빈 일정은 남지 않는다. 기본값을 비워 두면 딜을
    # 다시 보게 만드는 수정 경로가 실제와 다른 상태에서 돌아간다.
    return Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        customer_contact_id=contact_id,
        customer_company_id=company_id or uuid4(),
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
        sales_deal_id=sales_deal_id or uuid4(),
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
        assert "sales_deal_1.customer_company_id = customer_company_1.id" in sql
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


def test_create_uses_authenticated_owner_and_same_team_references(monkeypatch):
    # 딜이 붙은 등록은 계약 에이전트를 백그라운드로 부른다. TestClient 는 그 작업을
    # 응답 뒤에 그대로 돌리므로, 막지 않으면 목이 아니라 진짜 DB 로 붙는다.
    monkeypatch.setattr(contract_next_meeting_pipeline, "queue", lambda *_a, **_k: None)
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    product = _product(member.team_id)
    category = _category(member.team_id, code="demo")
    action_tag = _action_tag(member.team_id, code="demo_in_progress")
    deal = _deal(team_id=member.team_id, company_id=contact.company_id, owner_id=member.id)
    db = _Db(
        _Result(rows=[(contact, company.id, company.name)]),
        _Result(scalar=product),
        _Result(scalar=deal),
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
                "sales_deal_id": str(deal.id),
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
    # 고객사는 담당자에게서 나오고, 딜은 그 고객사의 것이어야 한다.
    assert activity.customer_company_id == contact.company_id
    assert activity.sales_deal_id == deal.id
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
    company = _company(member.team_id)
    sales_deal_id = uuid4()
    db = _Db(
        _Result(scalar=None),  # _team_sales_deal: 남의 딜은 보이지 않는다
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "sales_deal_id": str(sales_deal_id),
                "customer_company_id": str(company.id),
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


def test_create_rejects_contact_and_deal_from_different_companies():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    deal = SimpleNamespace(id=uuid4(), customer_company_id=uuid4())
    db = _Db(
        _Result(rows=[(contact, company.id, company.name)]),
        _Result(scalar=deal),
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "customer_contact_id": str(contact.id),
                "sales_deal_id": str(deal.id),
                "category_code": "visit",
                "title": "서로 다른 고객사의 일정",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "contact_company_mismatch"}
    assert db.added == []
    assert db.rollback_count == 1


def test_patch_rejects_contact_and_existing_deal_from_different_companies():
    member = _member()
    company = _company(member.team_id)
    contact = _contact(company.id, member.id)
    deal = SimpleNamespace(id=uuid4(), customer_company_id=uuid4())
    activity = _activity(member)
    activity.sales_deal_id = deal.id
    db = _Db(
        _Result(scalar=activity),
        _Result(rows=[(contact, company.id, company.name)]),
        _Result(scalar=deal),
    )

    with _client(db, member) as client:
        response = client.patch(
            f"/api/activities/{activity.id}",
            headers={"Origin": ORIGIN},
            json={"customer_contact_id": str(contact.id)},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "contact_company_mismatch"}
    assert activity.customer_contact_id is None
    assert db.commit_count == 0
    assert db.rollback_count == 1


def test_create_accepts_an_activity_without_a_sales_deal(monkeypatch):
    """딜은 비워 둘 수 있다 — 인사차 방문처럼 영업 건과 무관한 만남이 있다."""
    monkeypatch.setattr(contract_next_meeting_pipeline, "queue", lambda *_a, **_k: None)
    member = _member()
    company = _company(member.team_id)
    db = _Db(
        _Result(scalar=_category(member.team_id)),
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
        _Result(rows=[]),  # _sole_open_deal_id: 이 회사에 열린 딜이 없다
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(company.id),
                "category_code": "visit",
                "title": "인사차 방문",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    assert response.status_code == 201
    assert response.json()["sales_deal_id"] is None
    assert db.added[0].sales_deal_id is None
    assert db.commit_count == 1


def test_create_fills_the_deal_when_the_company_has_exactly_one(monkeypatch):
    """딜을 고르지 않아도, 고를 여지가 없으면 대신 골라 준다.

    회사에 열린 딜이 하나뿐이면 사람이 정하는 것과 같은 답이다. 둘 이상이면 찍지 않는다 —
    틀린 딜이 붙는 편이 안 붙는 것보다 나쁘다.
    """
    monkeypatch.setattr(contract_next_meeting_pipeline, "queue", lambda *_a, **_k: None)
    member = _member()
    company = _company(member.team_id)
    only_deal_id = uuid4()

    def _post(db: _Db):
        with _client(db, member) as client:
            return client.post(
                "/api/activities",
                headers={"Origin": ORIGIN},
                json={
                    "customer_company_id": str(company.id),
                    "category_code": "visit",
                    "title": "딜을 고르지 않은 방문",
                    "starts_at": "2026-08-17T10:00:00+09:00",
                },
            )

    single_db = _Db(
        _Result(scalar=_category(member.team_id)),
        _Result(scalar=company.name),  # _team_company
        _Result(rows=[(only_deal_id,)]),  # _sole_open_deal_id
    )
    assert _post(single_db).status_code == 201
    assert single_db.added[0].sales_deal_id == only_deal_id
    sql = str(single_db.statements[-1])
    # 끝난 딜과 지운 딜은 후보가 아니고, 하나뿐인지만 보면 되므로 두 건까지만 읽는다.
    assert "sales_pipeline_stage.phase_code !=" in sql
    assert "sales_deal.deleted_at IS NULL" in sql
    assert "LIMIT" in sql

    many_db = _Db(
        _Result(scalar=_category(member.team_id)),
        _Result(scalar=company.name),
        _Result(rows=[(uuid4(),), (uuid4(),)]),  # 둘 이상이면 고르지 않는다
    )
    assert _post(many_db).status_code == 201
    assert many_db.added[0].sales_deal_id is None


def test_create_rejects_a_sales_deal_from_another_company(monkeypatch):
    """딜을 붙였다면 그 딜은 이 일정의 고객사 것이어야 한다."""
    monkeypatch.setattr(contract_next_meeting_pipeline, "queue", lambda *_a, **_k: None)
    member = _member()
    company = _company(member.team_id)
    other_company_deal = _deal(team_id=member.team_id, company_id=uuid4(), owner_id=member.id)
    db = _Db(
        _Result(scalar=other_company_deal),  # _team_sales_deal
        _Result(scalar=_category(member.team_id)),
        _Result(scalar=company.name),  # _team_company
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(company.id),
                "sales_deal_id": str(other_company_deal.id),
                "category_code": "visit",
                "title": "남의 회사 딜",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "contact_company_mismatch"}
    assert not db.added


def test_create_without_a_contact_still_answers_with_the_company(monkeypatch):
    """담당자 없이 고객사만 지정한 등록도 응답에 회사가 실려야 한다.

    저장은 되는데 응답만 비어 나가면 화면이 방금 만든 일정을 잘못 그린다. 회사를
    담당자 조회 결과에서만 가져오던 탓이었다.
    """
    monkeypatch.setattr(contract_next_meeting_pipeline, "queue", lambda *_a, **_k: None)
    member = _member()
    company = _company(member.team_id)
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    db = _Db(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=_category(member.team_id)),
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
                "category_code": "visit",
                "title": "담당자 없이 회사만",
                "starts_at": "2026-08-17T10:00:00+09:00",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["customer_contact_id"] is None
    assert body["customer_company_id"] == str(company.id)
    assert body["customer_company_name"] == company.name
    assert db.added[0].customer_company_id == company.id


def test_patch_can_clear_the_deal_but_not_move_it_to_another_company():
    """딜은 비울 수 있다. 다만 남는 딜이 다른 회사 것이 되는 것은 막는다."""
    member = _member()
    company = _company(member.team_id)
    activity = _activity(member)

    cleared_db = _Db(
        _Result(scalar=activity),
        _Result(scalar="합성 고객사"),  # _team_company: 이름을 돌려준다
        _Result(rows=[_row(activity, member)]),
    )
    with _client(cleared_db, member) as client:
        cleared = client.patch(
            f"/api/activities/{activity.id}",
            headers={"Origin": ORIGIN},
            json={"sales_deal_id": None},
        )
    assert cleared.status_code == 200
    assert activity.sales_deal_id is None
    assert cleared_db.commit_count == 1

    # 고객사만 옮겨도 원래 딜이 다른 회사 것이 되므로 함께 다시 본다.
    moved = _activity(member)
    stale_deal = _deal(team_id=member.team_id, company_id=uuid4(), owner_id=member.id)
    moved.sales_deal_id = stale_deal.id
    moved_db = _Db(
        _Result(scalar=moved),
        _Result(scalar=company.name),  # _team_company
        _Result(scalar=stale_deal),  # _team_sales_deal
    )
    with _client(moved_db, member) as client:
        response = client.patch(
            f"/api/activities/{moved.id}",
            headers={"Origin": ORIGIN},
            json={"customer_company_id": str(company.id), "customer_contact_id": None},
        )
    assert response.status_code == 422
    assert response.json() == {"detail": "contact_company_mismatch"}
    assert moved_db.commit_count == 0


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

    # 담당자를 바꾸면 딜과 고객사의 짝을 다시 본다 — 그 사이 딜이 다른 회사 것이 될 수 있다.
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    activity.sales_deal_id = deal.id
    patch_db = _Db(
        _Result(scalar=activity),
        _Result(rows=[(contact, company.id, company.name)]),
        _Result(scalar=deal),  # _team_sales_deal
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
    company = _company(member.team_id)
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    db = _Db(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=_category(member.team_id)),
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
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
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
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
    company = _company(member.team_id)
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    category = _category(member.team_id, code="demo")
    parent_run = SimpleNamespace(
        id=uuid4(),
        team_id=member.team_id,
        agent_code="schedule_management",
        status_code="completed",
    )
    db = _Db(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
        _Result(scalar=None),  # _claim_suggestion: 선점할 제안 없음
        _Result(scalar=None),  # agent_runs 멱등키 조회: 기존 실행 없음
        _Result(scalar=parent_run),  # _parent_run_or_409
        _Result(rows=[]),  # 겹침 확인: 같은 시간대 일정 없음
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
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


def test_approving_a_suggestion_warns_when_the_slot_is_already_taken(monkeypatch):
    """제안은 미리 계산해 둔 값이라 승인할 때쯤 그 자리에 다른 일정이 생겼을 수 있다.

    등록은 이미 커밋됐으므로 되돌리지 않고, 겹친 일정을 경고로만 알린다.
    """
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))

    async def _fake_execute(run_id: UUID) -> None:
        return None

    monkeypatch.setattr(agent_run_service, "execute", _fake_execute)

    async def _fake_build_briefing_snapshot(db, member, activity_id):
        return {"customer_company": {"id": "company-1", "name": "합성 고객사"}}

    monkeypatch.setattr(
        contract_schedule_snapshots, "build_briefing_snapshot", _fake_build_briefing_snapshot
    )

    member = _member()
    company = _company(member.team_id)
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    category = _category(member.team_id, code="demo")
    parent_run = SimpleNamespace(
        id=uuid4(),
        team_id=member.team_id,
        agent_code="schedule_management",
        status_code="completed",
    )
    db = _Db(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
        _Result(scalar=None),  # _claim_suggestion: 선점할 제안 없음
        _Result(scalar=None),  # agent_runs 멱등키 조회: 기존 실행 없음
        _Result(scalar=parent_run),  # _parent_run_or_409
        _Result(rows=[("기존 방문", datetime(2026, 8, 17, 1, tzinfo=UTC))]),  # 겹치는 일정
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
                "schedule_management_run_id": str(parent_run.id),
            },
        )

    # 등록 자체는 성공한다 — 경고는 알림일 뿐 거절이 아니다.
    assert response.status_code == 201
    body = response.json()
    assert "기존 방문" in body["schedule_conflict_warning"]
    assert db.rollback_count == 0

    sql = str(db.statements[-1])
    # 같은 담당자의 미삭제 일정만, 자기 자신은 빼고 본다.
    assert "activity.owner_member_id" in sql
    assert "activity.deleted_at IS NULL" in sql
    assert "activity.id !=" in sql


def test_schedule_management_run_id_failure_surfaces_warning_but_keeps_activity(monkeypatch):
    """브리핑 큐잉이 실패해도 이미 커밋된 일정 등록은 되돌리지 않고 경고만 응답에 싣는다."""
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))

    expired = False
    member = _member()
    company = _company(member.team_id)
    member_getattribute = Member.__getattribute__
    activity_getattribute = Activity.__getattribute__

    def _guard_member(self, name):
        if expired and self is member and name in {"id", "team_id"}:
            raise AssertionError("rollback 뒤 member ORM 객체에 접근했습니다")
        return member_getattribute(self, name)

    def _guard_activity(self, name):
        if expired and name in {"id", "sales_deal_id", "starts_at", "ends_at"}:
            raise AssertionError("rollback 뒤 activity ORM 객체에 접근했습니다")
        return activity_getattribute(self, name)

    monkeypatch.setattr(Member, "__getattribute__", _guard_member)
    monkeypatch.setattr(Activity, "__getattribute__", _guard_activity)

    class _ExpiringDb(_Db):
        async def rollback(self):
            nonlocal expired
            await super().rollback()
            expired = True

    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    category = _category(member.team_id, code="demo")
    missing_run_id = uuid4()
    db = _ExpiringDb(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
        _Result(scalar=None),  # _claim_suggestion: 선점할 제안 없음
        _Result(scalar=None),  # agent_runs 멱등키 조회: 기존 실행 없음
        _Result(scalar=None),  # _parent_run_or_409: 부모 실행을 찾지 못함
        _Result(rows=[]),  # 겹침 확인: 같은 시간대 일정 없음
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
                "schedule_management_run_id": str(missing_run_id),
            },
        )

    assert response.status_code == 201
    assert response.json()["briefing_queue_warning"] == "parent_run_not_found"
    assert len(db.added) == 1
    assert db.commit_count == 1
    assert db.rollback_count == 1


def _pending_suggestion(member: Member, schedule_run_id: UUID) -> ContractNextMeetingSuggestion:
    return ContractNextMeetingSuggestion(
        id=uuid4(),
        team_id=member.team_id,
        sales_deal_id=uuid4(),
        schedule_management_run_id=schedule_run_id,
        status_code="pending",
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
        updated_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def test_approving_a_suggestion_claims_it_before_the_activity_is_created(monkeypatch):
    """승인하면 제안이 등록과 같은 트랜잭션에서 accepted 로 넘어간다."""
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))

    member = _member()
    company = _company(member.team_id)
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    category = _category(member.team_id, code="demo")
    schedule_run_id = uuid4()
    suggestion = _pending_suggestion(member, schedule_run_id)
    db = _Db(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
        _Result(scalar=suggestion),  # _claim_suggestion: 아직 pending
        _Result(scalar=None),  # agent_runs 멱등키 조회: 기존 실행 없음
        _Result(scalar=None),  # _parent_run_or_409: 부모 실행을 찾지 못함
        _Result(rows=[]),  # 겹침 확인: 같은 시간대 일정 없음
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
                "schedule_management_run_id": str(schedule_run_id),
            },
        )

    assert response.status_code == 201
    assert suggestion.status_code == "accepted"
    # 선점이 등록보다 먼저다 — 커밋 한 번에 둘이 함께 저장된다.
    assert len(db.added) == 1
    assert db.commit_count == 1


def test_claim_scopes_the_suggestion_to_the_team_and_owner(monkeypatch):
    """실행 ID 만 보면 그 값을 아는 사람이 남의 제안을 내려 버릴 수 있다."""
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))

    member = _member()
    company = _company(member.team_id)
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    category = _category(member.team_id, code="demo")
    db = _Db(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
        _Result(scalar=None),  # _claim_suggestion: 범위 안에 없음
        _Result(scalar=None),  # agent_runs 멱등키 조회
        _Result(scalar=None),  # _parent_run_or_409
        _Result(rows=[]),  # 겹침 확인
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
                "schedule_management_run_id": str(uuid4()),
            },
        )

    # 범위 밖이면 남의 제안을 건드리지 않고 등록만 진행한다.
    assert response.status_code == 201
    claim_sql = str(db.statements[3])
    assert "contract_next_meeting_suggestion.team_id" in claim_sql
    assert "sales_deal.owner_member_id" in claim_sql  # role_code == "member"
    # of= 로 지정한 대상은 PostgreSQL 방언에서만 "OF ..." 로 붙어, 기본 컴파일에는
    # FOR UPDATE 까지만 나온다. 잠금을 걸었다는 것만 여기서 확인한다.
    assert "FOR UPDATE" in claim_sql


def test_approving_an_already_accepted_suggestion_is_rejected(monkeypatch):
    """같은 추천을 두 번 승인하면 두 번째는 409 다 — 일정이 두 개 생기면 안 된다."""
    monkeypatch.setattr(type(settings), "llm_configured", property(lambda self: True))

    member = _member()
    company = _company(member.team_id)
    deal = _deal(team_id=member.team_id, company_id=company.id, owner_id=member.id)
    category = _category(member.team_id, code="demo")
    schedule_run_id = uuid4()
    suggestion = _pending_suggestion(member, schedule_run_id)
    suggestion.status_code = "accepted"  # 먼저 온 요청이 이미 가져갔다
    db = _Db(
        _Result(scalar=deal),  # _team_sales_deal
        _Result(scalar=category),  # _active_activity_category
        _Result(scalar=company.name),  # _team_company: 등록 응답이 쓸 회사 이름
        _Result(scalar=suggestion),  # _claim_suggestion: 이미 accepted
    )

    with _client(db, member) as client:
        response = client.post(
            "/api/activities",
            headers={"Origin": ORIGIN},
            json={
                "category_code": "demo",
                "title": "AI 추천 일정 승인",
                "starts_at": "2026-08-17T10:00:00+09:00",
                "customer_company_id": str(company.id),
                "sales_deal_id": str(deal.id),
                "schedule_management_run_id": str(schedule_run_id),
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "suggestion_already_processed"
    assert db.added == []
    assert db.commit_count == 0
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
