from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.crm import CustomerCompany, SupportRequest, SupportResponse
from app.models.sales import SalesDeal
from app.models.workspace import Member
from app.schemas.support import (
    SupportRequestCreate,
    SupportRequestPageParams,
    SupportResponseCreate,
    SupportTransition,
)
from app.services import contract_next_meeting_pipeline

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 17, 9, tzinfo=UTC)
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
            if isinstance(value, SupportRequest) and value.registered_at is None:
                value.registered_at = NOW
            if isinstance(value, SupportResponse) and value.responded_at is None:
                value.responded_at = NOW

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
        display_name="합성 담당자",
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


def _deal(owner: Member, company: CustomerCompany) -> SalesDeal:
    return SalesDeal(
        id=uuid4(),
        team_id=owner.team_id,
        deal_no="D-2026-0001",
        customer_company_id=company.id,
        customer_contact_id=None,
        owner_member_id=owner.id,
        product_id=uuid4(),
        sales_pipeline_id=uuid4(),
        sales_pipeline_stage_id=uuid4(),
        title="합성 계약건",
        description=None,
        sales_deal_type_id=uuid4(),
        deal_amount=1_000_000,
        opened_on=NOW.date(),
        contract_no="C-2026-0001",
        warranty_terms="납품 후 1년",
        stage_position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _request(
    assignee: Member,
    deal: SalesDeal,
    *,
    status_code: str = "in_progress",
) -> SupportRequest:
    return SupportRequest(
        id=uuid4(),
        team_id=assignee.team_id,
        customer_company_id=deal.customer_company_id,
        sales_deal_id=deal.id,
        assignee_member_id=assignee.id,
        title="합성 문의",
        body="합성 문의 본문",
        is_urgent=True,
        status_code=status_code,
        occurred_at=NOW,
        registered_at=NOW,
    )


def _support_response(request: SupportRequest, responder: Member) -> SupportResponse:
    return SupportResponse(
        id=uuid4(),
        support_request_id=request.id,
        responder_member_id=responder.id,
        body="합성 답변",
        responded_at=NOW,
    )


def _row(
    request: SupportRequest,
    deal: SalesDeal,
    company: CustomerCompany,
    assignee: Member,
    product_name: str | None = "합성 제품",
):
    return (
        request,
        company.name,
        deal.deal_no,
        deal.contract_no,
        deal.title,
        product_name,
        deal.warranty_terms,
        assignee.display_name,
    )


def _client(db: _Db, member: Member) -> TestClient:
    async def override_db():
        yield db

    async def override_member():
        return member

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_member] = override_member
    return TestClient(app)


def _payload(deal: SalesDeal, **overrides):
    values = {
        "customer_company_id": str(deal.customer_company_id),
        "sales_deal_id": str(deal.id),
        "title": " 합성 문의 ",
        "body": " 합성 문의 본문 ",
        "is_urgent": True,
        "status_code": "in_progress",
        "occurred_at": "2026-08-17T18:00:00+09:00",
    }
    return values | overrides


def test_support_write_models_are_strict_and_allow_only_four_status_codes():
    company_id = uuid4()
    deal_id = uuid4()
    valid = {
        "customer_company_id": company_id,
        "sales_deal_id": deal_id,
        "title": "문의",
        "body": "본문",
        "is_urgent": True,
        "status_code": "in_progress",
        "occurred_at": NOW,
    }
    parsed = SupportRequestCreate(**valid | {"title": " 문의 ", "body": " 본문 "})
    assert parsed.title == "문의"
    assert parsed.body == "본문"
    assert parsed.occurred_at == NOW
    for code in ("received", "diagnosing", "in_progress", "completed"):
        assert SupportRequestCreate(**valid | {"status_code": code}).status_code == code
    assert SupportRequestPageParams(
        status_code=["received", "diagnosing", "in_progress", "completed"]
    )

    invalid_payloads = (
        {"body": " "},
        {"status_code": "처리중"},
        {"status_code": "resolved"},
        {"is_urgent": 1},
        {"unknown": "value"},
        # 계약건 연결은 필수다. 하나라도 빠지면 등록이 아니라 거절이어야 한다.
        {"sales_deal_id": None},
        {"customer_company_id": None},
        {"occurred_at": None},
    )
    for invalid in invalid_payloads:
        with pytest.raises(ValidationError):
            SupportRequestCreate(**valid | invalid)
    with pytest.raises(ValidationError):
        SupportResponseCreate(body=" ")
    with pytest.raises(ValidationError):
        SupportTransition(expected_status_code="in_progress", status_code="done")


def test_member_list_and_detail_are_scoped_and_include_response_history():
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    request = _request(member, deal)
    response_item = _support_response(request, member)
    list_db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(request, deal, company, member)]),
        _Result(rows=[("in_progress", 1)]),
        _Result(rows=[(response_item, member.display_name)]),
    )

    with _client(list_db, member) as client:
        response = client.get(
            "/api/support-requests",
            params=[("q", " 합성 "), ("status_code", "in_progress")],
        )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": str(request.id),
                "customer_company_id": str(company.id),
                "customer_company_name": company.name,
                "sales_deal_id": str(deal.id),
                "deal_no": deal.deal_no,
                "contract_no": deal.contract_no,
                "deal_title": deal.title,
                "product_name": "합성 제품",
                "warranty_terms": deal.warranty_terms,
                "assignee_member_id": str(member.id),
                "assignee_display_name": member.display_name,
                "title": request.title,
                "body": request.body,
                "is_urgent": True,
                "status_code": "in_progress",
                "occurred_at": "2026-08-17T18:00:00+09:00",
                "registered_at": "2026-08-17T18:00:00+09:00",
                "responses": [
                    {
                        "id": str(response_item.id),
                        "support_request_id": str(request.id),
                        "responder_member_id": str(member.id),
                        "responder_display_name": member.display_name,
                        "body": response_item.body,
                        "responded_at": "2026-08-17T18:00:00+09:00",
                    }
                ],
            }
        ],
        "skip": 0,
        "limit": 30,
        "total": 1,
        "has_more": False,
        "next_skip": None,
        "counts": {"in_progress": 1},
    }
    for statement in list_db.statements[:2]:
        assert member.id in statement.compile().params.values()
        assert member.team_id in statement.compile().params.values()
        assert "%합성%" in statement.compile().params.values()
    assert member.team_id in list_db.statements[3].compile().params.values()

    detail_db = _Db(
        _Result(rows=[_row(request, deal, company, member)]),
        _Result(rows=[(response_item, member.display_name)]),
    )
    with _client(detail_db, member) as client:
        detail = client.get(f"/api/support-requests/{request.id}")
    assert detail.status_code == 200
    assert detail.json()["responses"][0]["body"] == response_item.body


def test_manager_reads_team_request_without_member_self_filter():
    manager = _member(role="manager")
    assignee = _member(team_id=manager.team_id)
    company = _company(manager.team_id)
    deal = _deal(assignee, company)
    request = _request(assignee, deal)
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[_row(request, deal, company, assignee)]),
        _Result(rows=[("in_progress", 1)]),
        _Result(rows=[]),
    )

    with _client(db, manager) as client:
        response = client.get("/api/support-requests")

    assert response.status_code == 200
    assert response.json()["items"][0]["assignee_member_id"] == str(assignee.id)
    assert manager.id not in db.statements[0].compile().params.values()


def test_create_uses_visible_deal_and_current_member_as_assignee():
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    db = _Db(_Result(rows=[(deal, company.name, "합성 제품")]))

    with _client(db, member) as client:
        response = client.post(
            "/api/support-requests",
            headers={"Origin": ORIGIN},
            json=_payload(deal, status_code="received"),
        )

    assert response.status_code == 201
    data = response.json()
    assert data["assignee_member_id"] == str(member.id)
    assert data["status_code"] == "received"
    assert data["title"] == "합성 문의"
    assert data["responses"] == []
    # 관련 제품과 워런티는 딜에서 따라온다. 불만이 따로 받지 않는다.
    assert data["product_name"] == "합성 제품"
    assert data["warranty_terms"] == deal.warranty_terms
    assert data["contract_no"] == deal.contract_no
    assert data["occurred_at"] == "2026-08-17T18:00:00+09:00"
    assert response.headers["location"] == f"/api/support-requests/{data['id']}"
    created = db.added[0]
    assert isinstance(created, SupportRequest)
    assert created.team_id == member.team_id
    assert created.assignee_member_id == member.id
    assert created.sales_deal_id == deal.id
    assert created.customer_company_id == company.id
    assert member.id in db.statements[0].compile().params.values()
    assert db.flush_count == db.commit_count == 1
    assert db.rollback_count == 0

    # 팀 밖이거나 계약 전 단계인 딜은 조회 자체가 비어 돌아온다.
    hidden_db = _Db(_Result(rows=[]))
    with _client(hidden_db, member) as client:
        hidden = client.post(
            "/api/support-requests",
            headers={"Origin": ORIGIN},
            json=_payload(deal),
        )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "sales_deal_not_found"}
    assert hidden_db.added == []
    assert hidden_db.commit_count == 0
    assert hidden_db.rollback_count == 1


def test_create_rejects_a_company_that_does_not_own_the_chosen_deal():
    """화면이 회사를 바꾸고 계약건을 비우지 않으면 두 값이 어긋난 채로 올라온다.

    DB 의 복합 외래키가 막기는 하지만 그때는 500 으로 새어 나간다. 앱이 먼저 뜻이
    보이는 409 를 내고 저장은 한 건도 하지 않아야 한다.
    """
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    db = _Db(_Result(rows=[(deal, company.name, "합성 제품")]))

    with _client(db, member) as client:
        response = client.post(
            "/api/support-requests",
            headers={"Origin": ORIGIN},
            json=_payload(deal, customer_company_id=str(uuid4())),
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "company_deal_mismatch"}
    assert db.added == []
    assert db.commit_count == 0
    assert db.rollback_count == 1


def test_create_narrows_deal_candidates_by_phase_and_owner():
    """등록이 거르는 조건은 화면이 아니라 서버가 건다.

    화면이 보낸 딜 id 를 그대로 믿으면 팀 경계가 요청 본문 하나로 뚫린다. 계약 전
    단계의 딜에는 아직 불만이 생길 수 없고, 팀원은 자기 딜에만 걸 수 있다.
    """
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    db = _Db(_Result(rows=[(deal, company.name, None)]))

    with _client(db, member) as client:
        assert (
            client.post(
                "/api/support-requests",
                headers={"Origin": ORIGIN},
                json=_payload(deal),
            ).status_code
            == 201
        )

    params = db.statements[0].compile().params.values()
    # 계약이 맺어진 뒤의 단계만 후보다. 영업·견적 단계는 빠진다.
    assert ["contract", "order", "closed"] in params
    assert member.team_id in params
    # 팀원은 자기 딜에만 걸 수 있다.
    assert member.id in params

    # 팀장은 팀 전체의 딜을 쓴다. 자기 id 로 좁히지 않는다.
    manager = _member(role="manager")
    manager_company = _company(manager.team_id)
    manager_deal = _deal(manager, manager_company)
    manager_db = _Db(_Result(rows=[(manager_deal, manager_company.name, None)]))
    with _client(manager_db, manager) as client:
        client.post(
            "/api/support-requests",
            headers={"Origin": ORIGIN},
            json=_payload(manager_deal),
        )
    assert manager.id not in manager_db.statements[0].compile().params.values()


def test_transition_walks_all_four_states(monkeypatch):
    """상태가 넷으로 늘어도 낙관적 잠금은 그대로다. 접수부터 완료까지 이어 밟는다.

    in_progress 로 넘어가는 순간 계약관리 파이프라인 트리거가 걸린다(support.py
    transition_support_request) — 이 테스트는 그 트리거 자체를 검증하지 않으므로 실제
    백그라운드 실행이 붙지 않게 큐잉만 무력화한다.
    """
    monkeypatch.setattr(contract_next_meeting_pipeline, "queue", lambda *_args, **_kwargs: None)
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)

    for expected, following in (
        ("received", "diagnosing"),
        ("diagnosing", "in_progress"),
        ("in_progress", "completed"),
        # 되돌리기도 같은 방법으로 열려 있다.
        ("completed", "received"),
    ):
        request = _request(member, deal, status_code=expected)
        db = _Db(
            _Result(scalar=request),
            _Result(rows=[_row(request, deal, company, member)]),
            _Result(rows=[]),
        )
        with _client(db, member) as client:
            response = client.post(
                f"/api/support-requests/{request.id}/transition",
                headers={"Origin": ORIGIN},
                json={"expected_status_code": expected, "status_code": following},
            )
        assert response.status_code == 200
        assert response.json()["status_code"] == following


def test_transition_uses_stale_guard_and_rejects_noop():
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    request = _request(member, deal)
    db = _Db(
        _Result(scalar=request),
        _Result(rows=[_row(request, deal, company, member)]),
        _Result(rows=[]),
    )

    with _client(db, member) as client:
        response = client.post(
            f"/api/support-requests/{request.id}/transition",
            headers={"Origin": ORIGIN},
            json={"expected_status_code": "in_progress", "status_code": "completed"},
        )

    assert response.status_code == 200
    assert response.json()["status_code"] == "completed"
    assert "FOR UPDATE" in str(db.statements[0])
    assert db.flush_count == db.commit_count == 1

    for payload in (
        {"expected_status_code": "completed", "status_code": "in_progress"},
        {"expected_status_code": "in_progress", "status_code": "in_progress"},
    ):
        current = _request(member, deal)
        stale_db = _Db(_Result(scalar=current))
        with _client(stale_db, member) as client:
            stale = client.post(
                f"/api/support-requests/{current.id}/transition",
                headers={"Origin": ORIGIN},
                json=payload,
            )
        assert stale.status_code == 409
        assert stale.json() == {"detail": "invalid_state_transition"}
        assert stale_db.flush_count == stale_db.commit_count == 0
        assert stale_db.rollback_count == 1


def test_response_creation_uses_current_member_and_hides_invisible_request():
    manager = _member(role="manager")
    assignee = _member(team_id=manager.team_id)
    company = _company(manager.team_id)
    deal = _deal(assignee, company)
    request = _request(assignee, deal)
    db = _Db(_Result(scalar=request))

    with _client(db, manager) as client:
        response = client.post(
            f"/api/support-requests/{request.id}/responses",
            headers={"Origin": ORIGIN},
            json={"body": " 합성 처리 답변 "},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["support_request_id"] == str(request.id)
    assert data["responder_member_id"] == str(manager.id)
    assert data["responder_display_name"] == manager.display_name
    assert data["body"] == "합성 처리 답변"
    assert data["responded_at"] == "2026-08-17T18:00:00+09:00"
    assert response.headers["location"].endswith(f"/responses/{data['id']}")
    assert isinstance(db.added[0], SupportResponse)
    assert db.flush_count == db.commit_count == 1

    hidden_db = _Db(_Result(scalar=None))
    with _client(hidden_db, manager) as client:
        hidden = client.post(
            f"/api/support-requests/{uuid4()}/responses",
            headers={"Origin": ORIGIN},
            json={"body": "합성 답변"},
        )
    assert hidden.status_code == 404
    assert hidden.json() == {"detail": "support_request_not_found"}
    assert hidden_db.added == []
    assert hidden_db.rollback_count == 1


def test_manager_support_assignee_filter_narrows_to_the_chosen_members():
    manager = _member(role="manager")
    first = _member(team_id=manager.team_id)
    second = _member(team_id=manager.team_id)
    db = _Db(
        _Result(scalar_values=[first.id, second.id]),
        _Result(scalar=0),
        _Result(rows=[]),
        _Result(rows=[]),
    )

    with _client(db, manager) as client:
        response = client.get(
            "/api/support-requests",
            params={"assignee_member_id": [str(first.id), str(second.id)]},
        )

    assert response.status_code == 200
    # 첫 문장은 범위 검증이고, 그 다음이 개수·목록·탭 건수다. 셋 다 같은 담당자로 좁혀야
    # 목록과 탭 숫자가 어긋나지 않는다.
    for statement in db.statements[1:]:
        assert [first.id, second.id] in statement.compile().params.values()


def test_member_support_assignee_filter_is_denied_before_any_query():
    member = _member()
    db = _Db()

    with _client(db, member) as client:
        response = client.get(
            "/api/support-requests",
            params={"assignee_member_id": [str(uuid4())]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "scope_not_allowed"
    assert not db.statements


def test_manager_support_assignee_filter_rejects_a_member_outside_the_team():
    manager = _member(role="manager")
    db = _Db(_Result(scalar_values=[]))

    with _client(db, manager) as client:
        response = client.get(
            "/api/support-requests",
            params={"assignee_member_id": [str(uuid4())]},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "scope_not_allowed"
    assert len(db.statements) == 1


def test_tab_counts_ignore_the_chosen_status_but_keep_other_filters():
    """탭 옆 건수는 고른 상태만 빼고 센다.

    상태까지 적용해 세면 고른 탭에만 숫자가 남고 나머지 탭이 모두 0 이 되어, 다른 탭에
    무엇이 얼마나 있는지 알 수 없다. 반대로 검색어까지 빼고 세면 탭 숫자가 실제로 열리는
    목록보다 커진다.
    """
    member = _member()
    db = _Db(
        _Result(scalar=1),
        _Result(rows=[]),
        _Result(rows=[("in_progress", 1), ("completed", 4)]),
    )

    with _client(db, member) as client:
        response = client.get(
            "/api/support-requests",
            params=[("q", "합성"), ("status_code", "in_progress")],
        )

    assert response.status_code == 200
    body = response.json()
    # 목록은 고른 상태로 좁혀 1건, 탭 건수는 상태를 빼고 세어 다른 탭도 함께 나온다.
    assert body["total"] == 1
    assert body["counts"] == {"in_progress": 1, "completed": 4}

    counts_sql = str(db.statements[2])
    assert "GROUP BY" in counts_sql
    # 상태 조건은 빠지고 검색어 조건은 남아야 한다.
    assert "support_request.status_code IN" not in counts_sql
    assert "%합성%" in db.statements[2].compile().params.values()
