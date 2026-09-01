import copy
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.agents import contract_management
from app.models.agent import AgentRun
from app.models.crm import Activity, CustomerCompany
from app.models.sales import SalesDeal, SalesPipelineStage
from app.models.workspace import Member
from app.services import contract_schedule_snapshots as snapshots

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

    def all(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.scalar_values)


class _Db:
    def __init__(self, *results: _Result):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        assert self.results, "예상보다 많은 쿼리가 실행되었습니다."
        return self.results.pop(0)


def _member() -> Member:
    return Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )


def _deal(member: Member, **overrides) -> SalesDeal:
    defaults = dict(
        id=uuid4(),
        team_id=member.team_id,
        deal_no="D-1",
        customer_company_id=uuid4(),
        owner_member_id=member.id,
        title="테스트 딜",
        deal_amount=1_000_000,
        opened_on=date(2026, 1, 1),
        contract_no=None,
        contract_signed_on=None,
        contract_ends_on=None,
        quote_valid_until=None,
        expected_delivery_at=None,
        deleted_at=None,
    )
    defaults.update(overrides)
    return SalesDeal(**defaults)


def _stage(**overrides) -> SalesPipelineStage:
    defaults = dict(
        id=uuid4(),
        sales_pipeline_id=uuid4(),
        stage_code="negotiation",
        name="협상",
        tone="info",
        phase_code="negotiation",
        outcome_code="open",
        position=1,
    )
    defaults.update(overrides)
    return SalesPipelineStage(**defaults)


# ---- _deal_risk_signals: DB 없이 순수 판정 로직만 확인 ----


def test_contract_and_quote_expiring_within_threshold():
    today = date(2026, 8, 24)
    member = _member()
    deal = _deal(
        member,
        contract_ends_on=today + timedelta(days=5),
        quote_valid_until=today + timedelta(days=10),
    )
    stage = _stage(phase_code="negotiation")
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    signals = snapshots._deal_risk_signals(deal, stage, recent_activity, today)

    codes = {signal["code"] for signal in signals}
    assert codes == {"contract_expiring", "quote_expiring"}
    contract_signal = next(s for s in signals if s["code"] == "contract_expiring")
    assert contract_signal["severity"] == "high"  # 7일 이내


def test_far_future_dates_do_not_trigger_risk():
    today = date(2026, 8, 24)
    member = _member()
    deal = _deal(
        member,
        contract_ends_on=today + timedelta(days=200),
        quote_valid_until=today + timedelta(days=200),
    )
    stage = _stage(phase_code="negotiation")
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    signals = snapshots._deal_risk_signals(deal, stage, recent_activity, today)

    assert signals == []


def test_follow_up_overdue_uses_opened_on_when_no_activity_but_not_for_new_deals():
    today = date(2026, 8, 24)
    member = _member()
    stage = _stage(phase_code="negotiation")

    old_deal = _deal(member, opened_on=date(2026, 6, 1))
    overdue = snapshots._deal_risk_signals(old_deal, stage, None, today)
    assert any(s["code"] == "follow_up_overdue" for s in overdue)

    new_deal = _deal(member, opened_on=today)
    not_overdue = snapshots._deal_risk_signals(new_deal, stage, None, today)
    assert not any(s["code"] == "follow_up_overdue" for s in not_overdue)


def test_delivery_delay_risk_when_expected_delivery_in_past():
    today = date(2026, 8, 24)
    member = _member()
    deal = _deal(member, expected_delivery_at=datetime(2026, 8, 1, tzinfo=UTC))
    stage = _stage(phase_code="negotiation")
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    signals = snapshots._deal_risk_signals(deal, stage, recent_activity, today)

    assert any(s["code"] == "delivery_delay_risk" and s["severity"] == "high" for s in signals)


def test_missing_contract_information_only_flagged_in_contract_phase():
    today = date(2026, 8, 24)
    member = _member()
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    deal = _deal(member, contract_no=None)
    contract_stage = _stage(phase_code="contract")
    negotiation_stage = _stage(phase_code="negotiation")

    assert any(
        s["code"] == "missing_contract_information"
        for s in snapshots._deal_risk_signals(deal, contract_stage, recent_activity, today)
    )
    assert not any(
        s["code"] == "missing_contract_information"
        for s in snapshots._deal_risk_signals(deal, negotiation_stage, recent_activity, today)
    )


def test_contract_revisit_due_absent_before_seven_days():
    today = date(2026, 8, 24)
    member = _member()
    deal = _deal(member, contract_signed_on=today - timedelta(days=6))
    stage = _stage(phase_code="negotiation")
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    signals = snapshots._deal_risk_signals(deal, stage, recent_activity, today)

    assert not any(s["code"] == "contract_revisit_due" for s in signals)


def test_contract_revisit_due_medium_after_seven_days():
    today = date(2026, 8, 24)
    member = _member()
    deal = _deal(member, contract_signed_on=today - timedelta(days=7))
    stage = _stage(phase_code="negotiation")
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    signals = snapshots._deal_risk_signals(deal, stage, recent_activity, today)

    revisit = next(s for s in signals if s["code"] == "contract_revisit_due")
    assert revisit["severity"] == "medium"


def test_contract_revisit_due_high_after_fourteen_days():
    today = date(2026, 8, 24)
    member = _member()
    deal = _deal(member, contract_signed_on=today - timedelta(days=14))
    stage = _stage(phase_code="negotiation")
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    signals = snapshots._deal_risk_signals(deal, stage, recent_activity, today)

    revisit = next(s for s in signals if s["code"] == "contract_revisit_due")
    assert revisit["severity"] == "high"


def test_contract_revisit_due_absent_without_signed_date():
    today = date(2026, 8, 24)
    member = _member()
    deal = _deal(member, contract_signed_on=None)
    stage = _stage(phase_code="negotiation")
    recent_activity = datetime(2026, 8, 24, tzinfo=UTC)

    signals = snapshots._deal_risk_signals(deal, stage, recent_activity, today)

    assert not any(s["code"] == "contract_revisit_due" for s in signals)


# ---- 빌더 함수: DB 조회 결합 확인 ----


@pytest.mark.anyio
async def test_build_candidate_selection_snapshot_with_no_open_deals():
    member = _member()
    db = _Db(_Result(rows=[]))  # _member_open_deals

    snapshot = await snapshots.build_candidate_selection_snapshot(db, member)

    assert snapshot == {"candidates": []}


@pytest.mark.anyio
async def test_build_candidate_selection_snapshot_filters_deals_without_risk_signals():
    """위험 신호가 없는 딜은 애초에 후보로 올리지 않는다 — LLM 선별 이전에 결정적으로 걸러진다."""
    member = _member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="테스트 병원")
    stage = _stage(phase_code="negotiation")
    today = date.today()

    risky_deal = _deal(
        member,
        title="위험 딜",
        contract_ends_on=today + timedelta(days=5),
    )
    safe_deal = _deal(
        member,
        title="안전 딜",
        contract_ends_on=today + timedelta(days=200),
        # opened_on 을 오늘로 두어 follow_up_overdue 신호까지 함께 켜지지 않게 한다.
        opened_on=today,
    )

    db = _Db(
        _Result(rows=[(risky_deal, stage, company), (safe_deal, stage, company)]),
        _Result(rows=[]),  # _last_activity_by_deal
        _Result(rows=[]),  # _deal_ids_with_upcoming_activity
    )

    snapshot = await snapshots.build_candidate_selection_snapshot(db, member)

    assert [c["sales_deal_id"] for c in snapshot["candidates"]] == [str(risky_deal.id)]
    candidate = snapshot["candidates"][0]
    assert candidate["customer_company_id"] == str(company.id)
    assert candidate["customer_company_name"] == "테스트 병원"
    assert candidate["sales_deal_title"] == "위험 딜"
    assert candidate["stage_code"] == "negotiation"
    assert candidate["stage_phase_code"] == "negotiation"
    assert any(s["code"] == "contract_expiring" for s in candidate["risk_signals"])


@pytest.mark.anyio
async def test_build_candidate_selection_snapshot_skips_deals_with_upcoming_activity():
    """계약 만료일 같은 신호는 미팅을 잡아도 사라지지 않는다 — 이미 앞으로 잡힌 일정이
    있는 딜은 위험 신호가 남아 있어도 후보에서 뺀다."""
    member = _member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="테스트 병원")
    stage = _stage(phase_code="negotiation")
    today = date.today()

    booked_deal = _deal(
        member,
        title="이미 미팅 잡힌 딜",
        contract_ends_on=today + timedelta(days=5),
    )
    open_deal = _deal(
        member,
        title="아직 안 잡힌 딜",
        contract_ends_on=today + timedelta(days=5),
    )

    db = _Db(
        _Result(rows=[(booked_deal, stage, company), (open_deal, stage, company)]),
        _Result(rows=[]),  # _last_activity_by_deal
        _Result(rows=[(booked_deal.id,)]),  # _deal_ids_with_upcoming_activity
    )

    snapshot = await snapshots.build_candidate_selection_snapshot(db, member)

    assert [c["sales_deal_id"] for c in snapshot["candidates"]] == [str(open_deal.id)]


@pytest.mark.anyio
async def test_build_candidate_selection_snapshot_exposes_stage_code():
    """0차 선별 프롬프트의 단계별 중요도 기준은 stage_code로 판단한다 — phase_code와
    다른 값이어도 stage_code가 그대로 전달돼야 한다."""
    member = _member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="테스트 병원")
    stage = _stage(stage_code="contract_completed", phase_code="contract")
    today = date.today()

    deal = _deal(member, contract_ends_on=today + timedelta(days=5))

    db = _Db(
        _Result(rows=[(deal, stage, company)]),
        _Result(rows=[]),  # _last_activity_by_deal
        _Result(rows=[]),  # _deal_ids_with_upcoming_activity
    )

    snapshot = await snapshots.build_candidate_selection_snapshot(db, member)

    candidate = snapshot["candidates"][0]
    assert candidate["stage_code"] == "contract_completed"
    assert candidate["stage_phase_code"] == "contract"


@pytest.mark.anyio
async def test_build_next_meeting_snapshot_with_no_open_deals():
    member = _member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="테스트 병원")
    db = _Db(
        _Result(scalar=company),  # _company_or_404
        _Result(rows=[]),  # _open_deals
        _Result(scalar_values=[]),  # _unresolved_support_signals
    )

    snapshot = await snapshots.build_next_meeting_snapshot(db, member, company.id)

    assert snapshot["customer_company"]["id"] == str(company.id)
    assert snapshot["sales_deals"] == []
    assert snapshot["risk_signals"] == []
    assert snapshot["recent_approved_reports"] == []


@pytest.mark.anyio
async def test_recent_finalized_reports_are_linked_by_report_deal():
    member = _member()
    sales_deal_id = uuid4()
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=None,
        report_date=date(2026, 8, 17),
        content={"hospital": "한빛병원"},
    )
    section = SimpleNamespace(
        sales_deal_id=sales_deal_id,
        content={"summary": "승인 보고서"},
    )
    db = _Db(_Result(rows=[(report, section)]))

    recent = await snapshots._recent_finalized_reports(db, member, [sales_deal_id])

    assert recent[0]["sales_deal_id"] == str(sales_deal_id)
    assert recent[0]["source_activity_id"] is None
    assert recent[0]["content"] == {**report.content, **section.content}
    sql = str(db.statements[0])
    assert "report_deal.sales_deal_id IN" in sql
    assert "JOIN public.activity" not in sql
    assert ["approved", "submitted"] in db.statements[0].compile().params.values()


@pytest.mark.anyio
async def test_contract_report_context_includes_shared_bodies_without_ml_or_ai(monkeypatch):
    member = _member()
    sales_deal_id = uuid4()
    content = {
        "title": "해당 딜 보고서",
        "values": {"body": "담당자가 검토한 해당 딜의 계약 협의 내용"},
        "meeting_shared": {
            "run_id": str(uuid4()),
            "common_report": {
                "body": "미팅 공통 배경",
                "evidence_ids": ["S0001"],
                "edited": True,
                "ai_body": "수정 전 AI 공통 초안",
            },
            "unassigned_report": {
                "body": "딜 미지정 · 확인 필요: 아직 딜을 정하지 못한 내용",
                "evidence_ids": ["S0002"],
            },
            "ml_result": "제외",
        },
        "deal_assessment": {"label": "high", "high_probability": 0.99},
        "ai_values": {"body": "아직 검토하지 않은 AI 초안"},
        "ai_evidence": "AI 생성 근거 표시",
        "ml_result": "제외",
        "transcript": "제외",
    }
    shared = content.pop("meeting_shared")
    original = copy.deepcopy(content)
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=uuid4(),
        report_date=date(2026, 8, 17),
        content={"meeting_shared": shared},
        transcript="여러 딜의 전체 미팅 원문",
        ai_evidence={"deal_assessment": {"label": "high"}},
        source_snapshot={"evidence": "원문 근거 장부"},
    )
    section = SimpleNamespace(sales_deal_id=sales_deal_id, content=content)
    db = _Db(_Result(rows=[(report, section)]))

    recent = await snapshots._recent_finalized_reports(db, member, [sales_deal_id])

    assert recent == [
        {
            "id": str(report.id),
            "sales_deal_id": str(sales_deal_id),
            "source_activity_id": str(report.source_activity_id),
            "report_date": "2026-08-17",
            "content": {
                "title": content["title"],
                "values": content["values"],
                "meeting_shared": {
                    "common_report": {"body": "미팅 공통 배경"},
                    "unassigned_report": {
                        "body": "딜 미지정 · 확인 필요: 아직 딜을 정하지 못한 내용"
                    },
                },
            },
        }
    ]
    assert section.content is content and content == original

    async def generate(**kwargs):
        assert json.loads(kwargs["input_text"])["recent_approved_reports"] == recent
        assert "해당 딜의 확정 사실·약속·계약 조건으로 배정하지 말고" in kwargs["instructions"]
        assert "모든 선택 딜에 명시적으로 적용된 합의·조건은" in kwargs["instructions"]
        return contract_management.NextMeetingProposalOutput()

    monkeypatch.setattr(contract_management, "generate_structured", generate)
    await contract_management.propose_next_meeting({"recent_approved_reports": recent})


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changed_body,same_activity,conflict",
    [
        ("common_report", True, True),
        ("unassigned_report", True, True),
        (None, True, False),
        ("common_report", False, False),
        ("unassigned_report", False, False),
    ],
)
async def test_contract_report_context_checks_shared_body_consistency(
    changed_body, same_activity, conflict
):
    member = _member()
    activity_id = uuid4()
    reports = [
        SimpleNamespace(
            id=uuid4(),
            source_activity_id=activity_id if index == 0 or same_activity else uuid4(),
            report_date=date(2026, 8, 17),
            content={
                "meeting_shared": {
                    "run_id": str(uuid4()),
                    "common_report": {
                        "body": "공통 본문",
                        "evidence_ids": [f"S000{index + 1}"],
                    },
                    "unassigned_report": {"body": "미지정 본문", "edited": bool(index)},
                },
            },
        )
        for index in range(2)
    ]
    sections = [
        SimpleNamespace(
            sales_deal_id=uuid4(),
            content={"values": {"body": f"딜 {index + 1}의 확정 본문"}},
        )
        for index in range(2)
    ]
    if changed_body is not None:
        reports[1].content["meeting_shared"][changed_body]["body"] = "서로 다른 본문"
    originals = copy.deepcopy([report.content for report in reports])
    db = _Db(_Result(rows=list(zip(reports, sections, strict=True))))
    deal_ids = [section.sales_deal_id for section in sections]

    if conflict:
        with pytest.raises(HTTPException) as error:
            await snapshots._recent_finalized_reports(db, member, deal_ids)
        assert error.value.status_code == 409
        assert error.value.detail == "report_source_shared_conflict"
    else:
        recent = await snapshots._recent_finalized_reports(db, member, deal_ids)
        assert len(recent) == 2
        for source, section, result in zip(reports, sections, recent, strict=True):
            assert result["sales_deal_id"] == str(section.sales_deal_id)
            assert result["content"]["values"] == section.content["values"]
            assert result["content"]["meeting_shared"] == {
                name: {"body": source.content["meeting_shared"][name]["body"]}
                for name in ("common_report", "unassigned_report")
            }
    assert [report.content for report in reports] == originals


@pytest.mark.anyio
@pytest.mark.parametrize(
    "content,has_activity,detail",
    [
        (None, True, "report_source_content_invalid"),
        ({"meeting_shared": "손상된 값"}, True, "report_source_shared_invalid"),
        ({"meeting_shared": {"common_report": {}}}, True, "report_source_shared_invalid"),
        (
            {"meeting_shared": {"unassigned_report": {"body": 123}}},
            True,
            "report_source_shared_invalid",
        ),
        (
            {"meeting_shared": {"common_report": {"body": "공통 내용"}}},
            False,
            "report_source_shared_invalid",
        ),
    ],
)
async def test_contract_report_context_rejects_malformed_shared(content, has_activity, detail):
    member = _member()
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=uuid4() if has_activity else None,
        report_date=date(2026, 8, 17),
        content=content,
    )
    section = SimpleNamespace(sales_deal_id=uuid4(), content={})
    with pytest.raises(HTTPException) as error:
        await snapshots._recent_finalized_reports(
            _Db(_Result(rows=[(report, section)])), member, [section.sales_deal_id]
        )
    assert error.value.status_code == 422
    assert error.value.detail == detail


@pytest.mark.anyio
async def test_build_schedule_snapshot_uses_parent_run_preferred_window():
    member = _member()
    deal = _deal(member)
    parent = AgentRun(
        id=uuid4(),
        team_id=member.team_id,
        agent_code="contract_management_next_meeting",
        status_code="completed",
        output_snapshot={
            "next_meeting_suggestion": {
                "sales_deal_id": str(deal.id),
                "reason": "계약 갱신 협의",
                "preferred_starts_at": "2026-08-25T00:00:00+09:00",
                "preferred_ends_at": "2026-08-28T00:00:00+09:00",
                "duration_minutes": 45,
            }
        },
    )
    activity = Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=deal.owner_member_id,
        title="기존 미팅",
        starts_at=datetime(2026, 8, 26, 9, tzinfo=UTC),
        ends_at=datetime(2026, 8, 26, 10, tzinfo=UTC),
        all_day=False,
        deleted_at=None,
    )
    db = _Db(
        _Result(scalar=deal),  # SalesDeal 조회
        _Result(scalar_values=[activity]),  # Activity 조회
    )

    snapshot = await snapshots.build_schedule_snapshot(
        db, member, deal.id, parent, None, None, None
    )

    assert snapshot["duration_minutes"] == 45
    assert snapshot["reason"] == "계약 갱신 협의"
    assert snapshot["activities"] == [
        {
            "id": str(activity.id),
            "owner_member_id": str(activity.owner_member_id),
            "starts_at": activity.starts_at.isoformat(),
            "ends_at": activity.ends_at.isoformat(),
            "all_day": False,
        }
    ]


@pytest.mark.anyio
async def test_build_schedule_snapshot_without_parent_uses_request_preferred_window():
    member = _member()
    deal = _deal(member)
    db = _Db(
        _Result(scalar=deal),
        _Result(scalar_values=[]),
    )

    snapshot = await snapshots.build_schedule_snapshot(
        db,
        member,
        deal.id,
        None,
        "2099-09-01T00:00:00+09:00",
        "2099-09-03T00:00:00+09:00",
        30,
    )

    assert snapshot["preferred_starts_at"] == "2099-09-01T00:00:00+09:00"
    assert snapshot["duration_minutes"] == 30
    assert snapshot["reason"] is None


@pytest.mark.anyio
async def test_schedule_snapshot_normalizes_naive_preferred_window():
    """시간대 없는 입력은 UTC 로 못 박아 내보낸다.

    원본 문자열을 그대로 흘려보내면 이 단계는 UTC 로, contract_management 는
    Asia/Seoul 로 읽어 같은 글자가 9시간 다르게 해석된다.
    """
    member = _member()
    deal = _deal(member)
    db = _Db(
        _Result(scalar=deal),
        _Result(scalar_values=[]),
    )

    snapshot = await snapshots.build_schedule_snapshot(
        db,
        member,
        deal.id,
        None,
        "2026-12-01T09:00:00",  # offset 없음
        "2026-12-03T18:00:00",
        60,
    )

    start = datetime.fromisoformat(snapshot["preferred_starts_at"])
    end = datetime.fromisoformat(snapshot["preferred_ends_at"])
    assert start.tzinfo is not None
    assert end.tzinfo is not None
    assert start.utcoffset() == timedelta(0)
    assert start == datetime(2026, 12, 1, 9, tzinfo=UTC)


@pytest.mark.anyio
async def test_schedule_snapshot_pulls_a_past_start_up_to_now():
    """시작이 이미 지났으면 지금으로 당긴다 — 끝이 미래면 창 자체는 살린다."""
    member = _member()
    deal = _deal(member)
    db = _Db(
        _Result(scalar=deal),
        _Result(scalar_values=[]),
    )
    before = datetime.now(UTC)

    snapshot = await snapshots.build_schedule_snapshot(
        db,
        member,
        deal.id,
        None,
        "2020-01-01T00:00:00+00:00",  # 한참 과거
        "2026-12-03T18:00:00+00:00",  # 끝은 미래
        60,
    )

    start = datetime.fromisoformat(snapshot["preferred_starts_at"])
    assert start >= before
    assert start <= datetime.now(UTC)


@pytest.mark.anyio
async def test_schedule_snapshot_drops_an_inverted_preferred_window():
    """시작이 끝보다 늦으면 탐색 범위가 성립하지 않는다 — 기본 범위로 넘긴다."""
    member = _member()
    deal = _deal(member)
    db = _Db(
        _Result(scalar=deal),
        _Result(scalar_values=[]),
    )

    snapshot = await snapshots.build_schedule_snapshot(
        db,
        member,
        deal.id,
        None,
        "2026-12-05T09:00:00+00:00",  # 시작이
        "2026-12-03T18:00:00+00:00",  # 끝보다 늦다
        60,
    )

    assert snapshot["preferred_starts_at"] is None
    assert snapshot["preferred_ends_at"] is None


# ---- build_next_meeting_snapshot: 딜 범위 한정 ----


@pytest.mark.anyio
async def test_recent_reports_prioritizes_the_required_report():
    """확정 트리거 보고서는 날짜·UUID 순서와 무관하게 5건 제한 안에 먼저 둔다."""
    member = _member()
    deal_id = uuid4()
    report_id = uuid4()
    report = SimpleNamespace(
        id=report_id,
        content={},
        source_activity_id=None,
        report_date=date(2026, 8, 1),
    )
    section = SimpleNamespace(sales_deal_id=deal_id, content={})
    db = _Db(_Result(rows=[(report, section)]))

    output = await snapshots._recent_finalized_reports(db, member, [deal_id], report_id)

    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert sql.index("public.report.id =") < sql.index("public.report.report_date DESC")
    assert report_id in compiled.params.values()
    assert output[0]["id"] == str(report_id)


@pytest.mark.anyio
async def test_next_meeting_snapshot_narrows_to_the_triggering_deal():
    """같은 회사에 딜이 둘이면 트리거 딜만 넣는다.

    둘 다 넣으면 LLM 이 다른 딜을 골라 답할 수 있고, 그 답이 트리거 딜의 제안으로
    저장된다(contract_next_meeting_pipeline).
    """
    member = _member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="테스트 병원")
    triggered = _deal(member, deal_no="D-1", customer_company_id=company.id, title="트리거 딜")
    other = _deal(member, deal_no="D-2", customer_company_id=company.id, title="다른 딜")
    stage = _stage(phase_code="negotiation")
    db = _Db(
        _Result(scalar=company),  # _company_or_404
        _Result(rows=[(triggered, stage), (other, stage)]),  # _open_deals
        _Result(rows=[]),  # _last_activity_by_deal
        _Result(scalar_values=[]),  # _unresolved_support_signals
        _Result(scalar_values=[]),  # _recent_finalized_reports
    )

    snapshot = await snapshots.build_next_meeting_snapshot(db, member, company.id, triggered.id)

    ids = [deal["id"] for deal in snapshot["sales_deals"]]
    assert ids == [str(triggered.id)]
    assert str(other.id) not in ids


@pytest.mark.anyio
async def test_next_meeting_snapshot_keeps_every_deal_without_a_deal_id():
    """딜 id 를 주지 않는 기존 호출부(POST /agent-runs)는 회사 단위 그대로 돈다."""
    member = _member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="테스트 병원")
    first = _deal(member, deal_no="D-1", customer_company_id=company.id)
    second = _deal(member, deal_no="D-2", customer_company_id=company.id)
    stage = _stage(phase_code="negotiation")
    db = _Db(
        _Result(scalar=company),
        _Result(rows=[(first, stage), (second, stage)]),
        _Result(rows=[]),
        _Result(scalar_values=[]),
        _Result(scalar_values=[]),
    )

    snapshot = await snapshots.build_next_meeting_snapshot(db, member, company.id)

    assert len(snapshot["sales_deals"]) == 2


@pytest.mark.anyio
async def test_next_meeting_snapshot_rejects_a_deal_outside_the_company():
    """이 회사의 열린 딜이 아니면 빈 스냅샷 대신 404 로 끊는다 — LLM 이 지어내지 않게."""
    member = _member()
    company = CustomerCompany(id=uuid4(), team_id=member.team_id, name="테스트 병원")
    open_deal = _deal(member, customer_company_id=company.id)
    db = _Db(
        _Result(scalar=company),
        _Result(rows=[(open_deal, _stage(phase_code="negotiation"))]),
    )

    with pytest.raises(HTTPException) as error:
        await snapshots.build_next_meeting_snapshot(db, member, company.id, uuid4())

    assert error.value.status_code == 404
    assert error.value.detail == "sales_deal_not_found"
