"""캘린더 "AI 추천 일정" 패널이 조회하는 선계산 제안 API를 확인한다.

패널은 LLM을 직접 부르지 않는다 — 트리거가 미리 만들어 둔 값만 읽는다
(docs/technical/multiagent/계약에이전트_설계.md 3장·11장).
"""

from datetime import UTC, datetime, timedelta
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


def _candidate(candidate_id: str, starts_at: datetime, *, priority: int = 1) -> dict:
    """후보 하나. 조회가 실제 현재 시각으로 지난 후보를 거르므로 시각은 상대값으로 만든다."""
    return {
        "candidate_id": candidate_id,
        "title": "계약 갱신 미팅",
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
        "priority": priority,
        "reason": "가장 이른 빈 시간",
    }


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
        status_code=status_code,
        created_at=NOW,
        updated_at=NOW,
    )


def _client(db: _Db, member: Member) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_member] = lambda: member
    return TestClient(app)


def test_list_returns_stored_candidates_without_calling_the_llm():
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
        output={
            "schedule_candidates": [
                _candidate("candidate-1", datetime.now(UTC) + timedelta(days=1))
            ]
        },
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
    assert item["schedule_candidates"][0]["candidate_id"] == "candidate-1"
    assert [risk["code"] for risk in item["risks"]] == ["contract_expiring"]
    # 팀원은 자기가 맡은 딜만 본다.
    assert member.id in db.statements[0].compile().params.values()


def test_list_drops_candidates_whose_time_has_passed():
    """제안은 만들 때만 미래였다. 지나간 시간대는 조회에서 뺀다.

    제안을 다시 계산하지 않으므로, 걸러 내지 않으면 "9월 13일에 9월 4일을 제안"하는 카드가
    그대로 뜬다.
    """
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    now = datetime.now(UTC)
    schedule_run = _run(
        member.team_id,
        agent_code="schedule_management",
        output={
            "schedule_candidates": [
                _candidate("지난-후보", now - timedelta(days=3)),
                _candidate("남을-후보", now + timedelta(days=2), priority=2),
            ]
        },
    )
    suggestion = _suggestion(deal, schedule_run.id)
    db = _Db(
        _Result(rows=[(suggestion, deal, company.name, member.display_name)]),
        _Result(scalar_values=[schedule_run]),
    )

    with _client(db, member) as client:
        response = client.get("/api/contract-next-meeting-suggestions", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    [item] = response.json()
    assert [c["candidate_id"] for c in item["schedule_candidates"]] == ["남을-후보"]


def test_list_hides_a_suggestion_whose_candidates_have_all_passed():
    """고를 수 있는 시간대가 하나도 남지 않았으면 보여 줄 것이 없다."""
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    now = datetime.now(UTC)
    schedule_run = _run(
        member.team_id,
        agent_code="schedule_management",
        output={
            "schedule_candidates": [
                _candidate("지난-후보-1", now - timedelta(days=9)),
                _candidate("지난-후보-2", now - timedelta(days=4), priority=2),
            ]
        },
    )
    suggestion = _suggestion(deal, schedule_run.id)
    db = _Db(
        _Result(rows=[(suggestion, deal, company.name, member.display_name)]),
        _Result(scalar_values=[schedule_run]),
    )

    with _client(db, member) as client:
        response = client.get("/api/contract-next-meeting-suggestions", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.json() == []


def test_list_keeps_a_candidate_whose_time_cannot_be_read():
    """형식이 낯설다는 이유로 멀쩡한 후보를 감추지 않는다. 지난 것이 확실할 때만 뺀다."""
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    schedule_run = _run(
        member.team_id,
        agent_code="schedule_management",
        output={"schedule_candidates": [{"candidate_id": "형식-이상", "starts_at": "언젠가"}]},
    )
    suggestion = _suggestion(deal, schedule_run.id)
    db = _Db(
        _Result(rows=[(suggestion, deal, company.name, member.display_name)]),
        _Result(scalar_values=[schedule_run]),
    )

    with _client(db, member) as client:
        response = client.get("/api/contract-next-meeting-suggestions", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    [item] = response.json()
    assert [c["candidate_id"] for c in item["schedule_candidates"]] == ["형식-이상"]


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


def test_dismiss_marks_the_suggestion_and_rejects_repeats():
    member = _member()
    company = _company(member.team_id)
    deal = _deal(member, company)
    suggestion = _suggestion(deal, uuid4())
    db = _Db(_Result(rows=[(suggestion, deal)]))

    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/dismiss",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 204
    assert suggestion.status_code == "dismissed"
    assert db.commit_count == 1

    already = _suggestion(deal, uuid4(), status_code="dismissed")
    repeat_db = _Db(_Result(rows=[(already, deal)]))
    with _client(repeat_db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/dismiss",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 409
    assert repeat_db.commit_count == 0


def test_dismiss_hides_other_owners_suggestion_as_not_found():
    member = _member()
    other = _member(team_id=member.team_id)
    company = _company(member.team_id)
    deal = _deal(other, company)
    db = _Db(_Result(rows=[(_suggestion(deal, uuid4()), deal)]))

    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{deal.id}/dismiss",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 404
    assert db.commit_count == 0


def test_dismiss_requires_an_existing_suggestion():
    member = _member()
    db = _Db(_Result(rows=[]))

    with _client(db, member) as client:
        response = client.post(
            f"/api/contract-next-meeting-suggestions/{uuid4()}/dismiss",
            headers={"Origin": ORIGIN},
        )

    assert response.status_code == 404
