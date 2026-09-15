"""캘린더 "AI 추천 일정" 패널이 조회하는 선계산 제안 API를 확인한다.

패널은 LLM을 직접 부르지 않는다 — 트리거가 미리 만들어 둔 값만 읽는다
(docs/technical/multiagent/계약에이전트_설계.md 3장·11장).
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.agent import AgentRun, ContractNextMeetingSuggestion
from app.models.crm import CustomerCompany
from app.models.sales import SalesDeal
from app.models.workspace import Member

ORIGIN = settings.cors_origin_list[0]
NOW = datetime(2026, 8, 29, 9, tzinfo=UTC)
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
        return self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행됐습니다."
        return self.results.pop(0)

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
    return CustomerCompany(id=uuid4(), team_id=team_id, name="합성 병원")


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
        stage_position=0,
        deleted_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _run(
    team_id: UUID,
    *,
    agent_code: str,
    status_code: str = "completed",
    output=None,
    parent_run_id: UUID | None = None,
) -> AgentRun:
    return AgentRun(
        id=uuid4(),
        team_id=team_id,
        parent_run_id=parent_run_id,
        requested_by_member_id=None,
        agent_code=agent_code,
        trigger_code="system",
        idempotency_key=None,
        status_code=status_code,
        llm_model_name="synthetic",
        prompt_version="v1",
        source_refs={},
        input_snapshot={},
        output_snapshot=output,
        evidence=None,
        error_message=None,
        started_at=NOW,
        finished_at=NOW,
    )


def _suggestion(deal: SalesDeal, schedule_run_id: UUID, *, status_code: str = "pending"):
    return ContractNextMeetingSuggestion(
        id=uuid4(),
        team_id=deal.team_id,
        sales_deal_id=deal.id,
        schedule_management_run_id=schedule_run_id,
        target_date=datetime(2026, 9, 20).date(),
        target_time=None,
        selected_duration_minutes=None,
        excluded_dates=[],
        refresh_reason=None,
        applied_activity_id=None,
        status_code=status_code,
        created_at=NOW,
        updated_at=NOW,
    )


def _client(db: _Db, member: Member) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_member] = lambda: member
    return TestClient(app)


def test_list_returns_one_stored_date_without_calling_the_llm():
    """패널이 그대로 그릴 값이 저장된 실행에서 나온다 — 조회 한 번으로 끝난다."""
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    next_meeting_run = _run(
        member.team_id,
        agent_code="contract_management_next_meeting",
        output={
            "risks": [{"code": "contract_expiring", "severity": "high", "message": "만료 임박"}],
            "next_meeting_suggestion": {"sales_deal_id": str(deal.id), "reason": "계약 갱신 협의"},
        },
    )
    schedule_run = _run(
        member.team_id,
        agent_code="schedule_management",
        parent_run_id=next_meeting_run.id,
        output={"decision": "valid", "reason_code": "recommendation_valid"},
    )
    suggestion = _suggestion(deal, schedule_run.id)
    db = _Db(
        _Result(rows=[(suggestion, deal, company.name, member.display_name)]),
        _Result(scalar_values=[schedule_run]),
        _Result(scalar_values=[next_meeting_run]),
    )

    with _client(db, member) as client:
        response = client.get("/api/contract-next-meeting-suggestions", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    [item] = response.json()
    assert item["sales_deal_id"] == str(deal.id)
    assert item["customer_company_name"] == "합성 병원"
    assert item["reason"] == "계약 갱신 협의"
    assert item["target_date"] == "2026-09-20"
    assert item["target_time"] is None
    assert item["duration_options"] == [30, 60, 90]
    assert [risk["code"] for risk in item["risks"]] == ["contract_expiring"]
    # 팀원은 자기가 맡은 딜만 본다.
    assert member.id in db.statements[0].compile().params.values()


def test_list_skips_suggestions_whose_run_has_not_finished():
    """아직 돌고 있거나 실패한 실행은 보여줄 내용이 없다 — 다음 트리거가 다시 채운다."""
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    running_run = _run(member.team_id, agent_code="schedule_management", status_code="running")
    suggestion = _suggestion(deal, running_run.id)
    db = _Db(
        _Result(rows=[(suggestion, deal, company.name, member.display_name)]),
        _Result(scalar_values=[running_run]),
    )

    with _client(db, member) as client:
        response = client.get("/api/contract-next-meeting-suggestions", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.json() == []


def test_manager_sees_the_whole_team_and_empty_list_skips_extra_queries():
    member = _member(role="manager")
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        response = client.get("/api/contract-next-meeting-suggestions", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.json() == []
    assert member.id not in db.statements[0].compile().params.values()


def test_reject_replaces_the_suggestion_and_excludes_the_old_date(monkeypatch):
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    suggestion = _suggestion(deal, uuid4())
    db = _Db(_Result(rows=[(suggestion, deal)]))
    captured = {}

    async def regenerate(sales_deal_id, **kwargs):
        captured.update({"sales_deal_id": sales_deal_id, **kwargs})
        return True

    monkeypatch.setattr(
        "app.api.contract_suggestions.contract_next_meeting_pipeline.regenerate", regenerate
    )

    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/reject",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 204
    assert suggestion.status_code == "rejected"
    assert captured["sales_deal_id"] == deal.id
    assert captured["excluded_dates"] == [suggestion.target_date]
    assert db.commit_count == 1

    already = _suggestion(deal, uuid4(), status_code="accepted")
    repeat_db = _Db(_Result(rows=[(already, deal)]))
    with _client(repeat_db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/reject",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 409
    assert repeat_db.commit_count == 0


def test_reject_hides_other_owners_suggestion_as_not_found():
    member = _member()
    other = _member(team_id=member.team_id)
    company = _company(member.team_id)
    deal = _deal(other, company)
    db = _Db(_Result(rows=[(_suggestion(deal, uuid4()), deal)]))

    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/reject",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 404
    assert db.commit_count == 0


def test_reject_keeps_the_card_when_regeneration_queue_fails(monkeypatch):
    """계약관리 작업을 예약하지 못하면 기존 카드를 숨기지 않는다."""
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    suggestion = _suggestion(deal, uuid4())
    db = _Db(_Result(rows=[(suggestion, deal)]))

    async def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic queue failure")

    monkeypatch.setattr(
        "app.api.contract_suggestions.contract_next_meeting_pipeline.regenerate", fail
    )

    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/reject",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "recommendation_refresh_failed"
    assert suggestion.status_code == "pending"
    assert db.commit_count == 0


def test_reject_requires_an_existing_suggestion():
    member = _member()
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{uuid4()}/reject",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 404


def test_apply_date_only_requires_a_supported_duration():
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    suggestion = _suggestion(deal, uuid4())

    db = _Db(_Result(rows=[(suggestion, deal)]))
    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/apply",
            headers={"Origin": ORIGIN},
            json={"duration_minutes": 60},
        )

    assert response.status_code == 200
    assert response.json()["target_date"] == "2026-09-20"
    assert suggestion.selected_duration_minutes == 60
    assert suggestion.status_code == "accepted"

    invalid_db = _Db()
    with _client(invalid_db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/apply",
            headers={"Origin": ORIGIN},
            json={"duration_minutes": 45},
        )
    assert response.status_code == 422


def test_refresh_replaces_only_when_schedule_agent_requests_it(monkeypatch):
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    suggestion = _suggestion(deal, uuid4())
    suggestion.target_date = datetime(2026, 9, 14).date()
    captured = {}

    async def run(snapshot):
        captured["snapshot"] = snapshot
        return SimpleNamespace(
            decision="refresh_required",
            reason="추천 날짜가 지나 새 날짜 논의가 필요합니다.",
        )

    async def regenerate(sales_deal_id, **kwargs):
        captured.update({"sales_deal_id": sales_deal_id, **kwargs})
        return True

    monkeypatch.setattr("app.api.contract_suggestions.schedule_management.run", run)
    monkeypatch.setattr(
        "app.api.contract_suggestions.contract_next_meeting_pipeline.regenerate", regenerate
    )
    db = _Db(_Result(rows=[(suggestion, deal, "in_progress")]))

    with _client(db, member) as client:
        response = client.post(
            "/api/contract-next-meeting-suggestions/refresh",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 200
    assert response.json() == {"checked_count": 1, "replaced_count": 1}
    assert captured["sales_deal_id"] == deal.id
    assert captured["excluded_dates"] == [suggestion.target_date]


def test_refresh_failure_keeps_the_existing_card(monkeypatch):
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    suggestion = _suggestion(deal, uuid4())

    async def fail(_snapshot):
        raise RuntimeError("synthetic agent failure")

    monkeypatch.setattr("app.api.contract_suggestions.schedule_management.run", fail)
    db = _Db(_Result(rows=[(suggestion, deal, "in_progress")]))

    with _client(db, member) as client:
        response = client.post(
            "/api/contract-next-meeting-suggestions/refresh",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 200
    assert response.json() == {"checked_count": 1, "replaced_count": 0}
    assert suggestion.status_code == "pending"
    assert db.commit_count == 0
