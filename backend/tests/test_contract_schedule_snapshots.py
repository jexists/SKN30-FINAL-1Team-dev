import copy
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import MultipleResultsFound

from app.agents import contract_management
from app.models.agent import AgentRun
from app.models.crm import Activity, CustomerCompany, SupportRequest, SupportResponse
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

    def one_or_none(self):
        if len(self.rows) > 1:
            raise MultipleResultsFound
        return self.rows[0] if self.rows else None

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

    async def rollback(self):
        pass


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
        _Result(rows=[]),  # 고객사 확정 보고서
        _Result(rows=[]),  # _meeting_history
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
        common_body=None,
        unassigned_body=None,
        content={"hospital": "한빛병원"},
    )
    section = SimpleNamespace(
        sales_deal_id=sales_deal_id,
        title=None,
        body="승인 보고서",
        content={"values": {"body": "승인 보고서"}},
    )
    db = _Db(_Result(rows=[(report, section)]))

    recent = await snapshots._recent_finalized_reports(db, member, [sales_deal_id])

    assert recent[0]["sales_deal_id"] == str(sales_deal_id)
    assert recent[0]["source_activity_id"] is None
    assert recent[0]["content"] == {"values": {"body": "승인 보고서"}}
    sql = str(db.statements[0])
    assert "report_deal.sales_deal_id IN" in sql
    assert "JOIN public.activity" not in sql
    assert ["approved", "submitted"] in db.statements[0].compile().params.values()


@pytest.mark.anyio
async def test_unresolved_support_signals_cover_every_open_status():
    """끝나지 않은 C/S 는 상태와 무관하게 모두 위험 신호가 된다.

    in_progress 만 조회하면 접수(received)·원인파악(diagnosing) 단계의 요청이 통째로 빠져,
    브리핑과 다음 미팅 제안 양쪽에서 그 위험이 보이지 않는다.
    """
    member = _member()
    company_id = uuid4()
    db = _Db(_Result(scalar_values=[]))

    await snapshots._unresolved_support_signals(db, member, company_id)

    params = list(db.statements[0].compile().params.values())
    assert ["received", "diagnosing", "in_progress"] in params
    assert "completed" not in str(db.statements[0].compile().params)


@pytest.mark.anyio
async def test_recent_finalized_reports_limits_reports_before_joining_deal_sections():
    """한 보고서의 여러 딜 섹션이 최근 보고서 5건 제한을 잠식하지 않는다."""
    member = _member()
    deal_ids = [uuid4(), uuid4()]
    reports = [
        SimpleNamespace(
            id=uuid4(),
            source_activity_id=None,
            report_date=date(2026, 8, 17 - index),
            content={},
        )
        for index in range(5)
    ]
    sections = [
        SimpleNamespace(sales_deal_id=deal_ids[0], content={}),
        SimpleNamespace(sales_deal_id=deal_ids[1], content={}),
    ]
    rows = [(reports[0], section) for section in sections]
    rows.extend(
        (report, SimpleNamespace(sales_deal_id=deal_ids[0], content={})) for report in reports[1:]
    )
    db = _Db(_Result(rows=rows))

    recent = await snapshots._recent_finalized_reports(db, member, deal_ids)

    assert len({item["id"] for item in recent}) == 5
    assert len(recent) == 6
    assert {item["sales_deal_id"] for item in recent if item["id"] == str(reports[0].id)} == {
        str(deal_id) for deal_id in deal_ids
    }
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "GROUP BY public.report.id" in sql
    assert sql.count("LIMIT") == 1
    assert sql.index("LIMIT") < sql.rindex("JOIN public.report_deal")


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
        common_body=shared["common_report"]["body"],
        unassigned_body=shared["unassigned_report"]["body"],
        content={"meeting_shared": shared},
        transcript="여러 딜의 전체 미팅 원문",
        ai_evidence={"deal_assessment": {"label": "high"}},
        source_snapshot={"evidence": "원문 근거 장부"},
    )
    section = SimpleNamespace(
        sales_deal_id=sales_deal_id,
        title=content["title"],
        body=content["values"]["body"],
        content=content,
    )
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

    monkeypatch.setattr(contract_management, "configured_chat_model", lambda: object())

    def create(model, **kwargs):
        instructions = kwargs["system_prompt"]
        assert "해당 딜의 확정 사실·약속·계약 조건으로 배정하지 말고" in instructions
        assert "모든 선택 딜에 명시적으로 적용된 합의·조건은" in instructions
        assert "딜 연결을 요구하거나" in instructions
        assert "sales_deal_id는 null로 두고" in instructions

        class Agent:
            async def ainvoke(self, payload, config):
                llm_input = json.loads(payload["messages"][0]["content"])
                assert llm_input["recent_approved_reports"] == recent
                return {
                    "messages": payload["messages"],
                    "structured_response": contract_management.NextMeetingProposalOutput(
                        next_meeting_suggestion=contract_management.NextMeetingSuggestion(
                            reason="후속 미팅", target_date="2099-01-01"
                        )
                    ),
                }

        return Agent()

    monkeypatch.setattr(contract_management, "create_agent", create)
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
            common_body="공통 본문",
            unassigned_body="미지정 본문",
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
            title=None,
            body=f"딜 {index + 1}의 확정 본문",
            content={"values": {"body": f"딜 {index + 1}의 확정 본문"}},
        )
        for index in range(2)
    ]
    if changed_body is not None:
        field = "common_body" if changed_body == "common_report" else "unassigned_body"
        setattr(reports[1], field, "서로 다른 본문")
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
            assert result["content"]["values"] == {"body": section.body}
            assert result["content"]["meeting_shared"] == {
                "common_report": {"body": source.common_body},
                "unassigned_report": {"body": source.unassigned_body},
            }
    assert [report.content for report in reports] == originals


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body,common_body,unassigned_body,has_activity,detail",
    [
        (123, None, None, True, "report_source_content_invalid"),
        ("본문", {}, None, True, "report_source_shared_invalid"),
        ("본문", None, 123, True, "report_source_shared_invalid"),
        ("본문", "공통 내용", None, False, "report_source_shared_invalid"),
    ],
)
async def test_contract_report_context_rejects_malformed_normalized_body(
    body, common_body, unassigned_body, has_activity, detail
):
    member = _member()
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=uuid4() if has_activity else None,
        report_date=date(2026, 8, 17),
        common_body=common_body,
        unassigned_body=unassigned_body,
        content={},
    )
    section = SimpleNamespace(sales_deal_id=uuid4(), title=None, body=body, content={})
    with pytest.raises(HTTPException) as error:
        await snapshots._recent_finalized_reports(
            _Db(_Result(rows=[(report, section)])), member, [section.sales_deal_id]
        )
    assert error.value.status_code == 422
    assert error.value.detail == detail


@pytest.mark.anyio
async def test_build_schedule_snapshot_uses_parent_target_without_widening():
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
                "target_date": "2026-09-20",
                "target_time": "11:00:00",
            }
        },
    )
    db = _Db(_Result(rows=[(deal, "in_progress")]))

    snapshot = await snapshots.build_schedule_snapshot(db, member, deal.id, parent, None, None)

    assert snapshot["target_date"] == "2026-09-20"
    assert snapshot["target_time"] == "11:00:00"
    assert snapshot["reason"] == "계약 갱신 협의"
    assert "duration_minutes" not in snapshot
    assert "preferred_starts_at" not in snapshot
    assert "activities" not in snapshot


@pytest.mark.anyio
async def test_build_schedule_snapshot_accepts_direct_single_date():
    member = _member()
    deal = _deal(member)
    db = _Db(_Result(rows=[(deal, "in_progress")]))

    snapshot = await snapshots.build_schedule_snapshot(
        db,
        member,
        deal.id,
        None,
        date(2026, 9, 22),
        None,
        excluded_dates=[date(2026, 9, 20)],
    )

    assert snapshot["target_date"] == "2026-09-22"
    assert snapshot["target_time"] is None
    assert snapshot["excluded_dates"] == ["2026-09-20"]
    assert snapshot["deal_outcome_code"] == "in_progress"
    assert snapshot["timezone"] == "Asia/Seoul"


@pytest.mark.anyio
async def test_build_schedule_snapshot_requires_a_valid_target_date():
    member = _member()
    deal = _deal(member)

    with pytest.raises(HTTPException) as missing:
        await snapshots.build_schedule_snapshot(
            _Db(_Result(rows=[(deal, "in_progress")])),
            member,
            deal.id,
            None,
            None,
            None,
        )
    assert missing.value.detail == "target_date_required"

    with pytest.raises(HTTPException) as invalid:
        await snapshots.build_schedule_snapshot(
            _Db(_Result(rows=[(deal, "in_progress")])),
            member,
            deal.id,
            None,
            "not-a-date",
            None,
        )
    assert invalid.value.detail == "invalid_target_date"


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
        _Result(rows=[]),  # _meeting_history
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
        _Result(rows=[]),
    )

    snapshot = await snapshots.build_next_meeting_snapshot(db, member, company.id)

    assert len(snapshot["sales_deals"]) == 2
    assert snapshot["_scope_sales_deal_id"] is None
    assert snapshot["_meeting_history"]["is_first_meeting"] is True


@pytest.mark.anyio
async def test_meeting_history_computes_cycle_weekdays_and_upcoming_meetings():
    member = _member()
    rows = [  # DB는 최신순으로 돌려준다. 서울 기준 2주 간격 화요일 10시 미팅.
        (datetime(2999, 1, 1, 1, 0, tzinfo=UTC), False),
        (datetime(2020, 2, 4, 1, 0, tzinfo=UTC), False),
        (datetime(2020, 1, 21, 1, 0, tzinfo=UTC), False),
        (datetime(2020, 1, 7, 1, 0, tzinfo=UTC), True),
    ]

    history = await snapshots._meeting_history(_Db(_Result(rows=rows)), member, uuid4())

    assert history["past_meetings"][0] == {"date": "2020-01-07", "weekday": "화", "time": None}
    assert history["past_meetings"][-1] == {"date": "2020-02-04", "weekday": "화", "time": "10:00"}
    assert history["upcoming_meetings"] == [
        {"date": "2999-01-01", "weekday": "화", "time": "10:00"}
    ]
    assert history["interval_days"] == [14, 14]
    assert history["median_interval_days"] == 14
    assert history["weekday_counts"] == {"화": 3}
    assert history["is_first_meeting"] is False


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


# ---- build_briefing_snapshot: 자료요약 RAG 연결 ----


def _briefing_db(
    member,
    company,
    activity,
    deals,
    *,
    reports=None,
    has_prior_meeting=None,
    mentioned_products=None,
    product_documents=None,
    support_requests=None,
    support_responses=None,
):
    """build_briefing_snapshot 이 순서대로 실행하는 DB 조회에 답한다."""
    recent_rows = []
    for report, section in reports or []:
        snapshot = {
            "title": getattr(report, "title", None),
            "common_body": getattr(report, "common_body", None),
            "unassigned_body": getattr(report, "unassigned_body", None),
            "deals": (
                []
                if section is None
                else [
                    {
                        "sales_deal_id": str(section.sales_deal_id),
                        "title": getattr(section, "title", None),
                        "body": getattr(section, "body", None),
                    }
                ]
            ),
        }
        recent_rows.append(
            (
                report,
                SimpleNamespace(
                    id=uuid4(),
                    submitted_at=datetime(2026, 9, 2, tzinfo=UTC),
                    snapshot=snapshot,
                ),
            )
        )
    contact = SimpleNamespace(
        id=activity.customer_contact_id,
        name="김테스트",
        department="영업기획",
        job_title="팀장",
    )
    results = [
        _Result(rows=[(activity, company, contact)]),  # 일정 + 고객사 + 참석자
        _Result(scalar=company),  # _company_or_404
        _Result(rows=deals),  # _company_deals
        _Result(rows=recent_rows),  # recent_reports
        _Result(
            scalar=(
                uuid4()
                if (bool(reports) if has_prior_meeting is None else has_prior_meeting)
                else None
            )
        ),  # 이전 미팅
        _Result(scalar_values=support_requests or []),  # 고객사 C/S
    ]
    if support_requests:
        results.append(_Result(scalar_values=support_responses or []))  # C/S 대응 기록
    results.append(_Result(rows=[]))  # 거래 문서별 최신 현재 상태
    if deals:
        results.extend(
            [_Result(scalar_values=[]), _Result(scalar_values=[])]  # 딜·견적 제품
        )
    if reports:
        results.append(_Result(rows=mentioned_products or []))
    if mentioned_products:
        results.append(_Result(rows=product_documents or []))
        results.append(_Result(scalar_values=[name for _, name in mentioned_products]))
    return _Db(*results)


def _briefing_fixture():
    member = _member()
    company = CustomerCompany(
        id=uuid4(),
        team_id=member.team_id,
        name="테스트 병원",
    )
    deal = _deal(member, customer_company_id=company.id, title="초음파 장비 계약")
    activity = Activity(
        id=uuid4(),
        team_id=member.team_id,
        owner_member_id=member.id,
        customer_contact_id=uuid4(),
        sales_deal_id=deal.id,
        title="계약 갱신 미팅",
        starts_at=datetime(2026, 9, 3, 5, tzinfo=UTC),
        ends_at=datetime(2026, 9, 3, 6, tzinfo=UTC),
        all_day=False,
        location="본원 3층",
        note="납기와 설치 조건을 확인합니다.",
        deleted_at=None,
    )
    return member, company, deal, activity


@pytest.mark.anyio
async def test_briefing_snapshot_searches_documents_by_company(monkeypatch):
    """일정은 회사 범위이고, 딜 자료도 고객사를 거쳐 조회한다."""
    member, company, deal, activity = _briefing_fixture()
    captured = {}
    context = {"query": "테스트 병원", "summaries": [], "sources": [{"document_id": "doc-1"}]}

    async def _retrieve(_db, **kwargs):
        captured.update(kwargs)
        return context

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)

    db = _briefing_db(member, company, activity, [(deal, _stage())])
    snapshot = await snapshots.build_briefing_snapshot(db, member, activity.id)

    assert captured["sales_deal_id"] is None
    assert captured["customer_company_id"] == company.id
    assert captured["team_id"] == member.team_id
    # 검색어는 결정적으로 조립한다 — 여기서 LLM 을 한 번 더 부르지 않는다.
    assert captured["query"].startswith("테스트 병원 계약 갱신 미팅")
    assert "초음파 장비 계약" in captured["query"]
    assert snapshot["document_context"]["sources"] == context["sources"]
    assert snapshot["document_context"]["product_documents"] == []
    assert "activity.customer_company_id = public.customer_company.id" in str(db.statements[0])


def _support_request(member, company, **overrides):
    values = {
        "id": uuid4(),
        "team_id": member.team_id,
        "customer_company_id": company.id,
        "sales_deal_id": uuid4(),
        "assignee_member_id": member.id,
        "title": "초음파 화면 깜빡임",
        "body": "검사 중 화면이 꺼졌다 켜집니다.",
        "is_urgent": False,
        "status_code": "received",
        "occurred_at": datetime(2026, 9, 1, 1, tzinfo=UTC),
        "deleted_at": None,
    }
    values.update(overrides)
    return SupportRequest(**values)


@pytest.mark.anyio
async def test_briefing_snapshot_orders_open_support_requests_for_the_tool(monkeypatch):
    """미해결 C/S는 긴급 건부터, 처리완료 건은 최근 몇 건만 담고 원문은 도구로만 넘긴다."""
    member, company, _deal, activity = _briefing_fixture()
    normal = _support_request(member, company, title="일반 미해결")
    urgent = _support_request(
        member,
        company,
        title="긴급 미해결",
        is_urgent=True,
        status_code="in_progress",
        occurred_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    done = [
        _support_request(
            member,
            company,
            title=f"처리완료 {index}",
            status_code="completed",
            occurred_at=datetime(2026, 8, 10 - index, tzinfo=UTC),
        )
        for index in range(4)
    ]
    responses = [
        SupportResponse(
            id=uuid4(),
            support_request_id=urgent.id,
            responder_member_id=member.id,
            body=f"대응 {index}",
            responded_at=datetime(2026, 9, 2, index, tzinfo=UTC),
        )
        for index in (4, 3, 2, 1)  # 최신 대응부터 조회된다.
    ]

    async def _retrieve(_db, **_kwargs):
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)
    db = _briefing_db(
        member,
        company,
        activity,
        [],
        support_requests=[normal, urgent, *done],
        support_responses=responses,
    )

    snapshot = await snapshots.build_briefing_snapshot(db, member, activity.id)

    assert [item["title"] for item in snapshot["support_requests"]] == [
        "긴급 미해결",
        "일반 미해결",
        "처리완료 0",
        "처리완료 1",
        "처리완료 2",
    ]
    assert snapshot["open_support_request_count"] == 2
    # 건마다 최근 대응 3건만, 오래된 것부터 읽히게 담는다.
    assert [item["body"] for item in snapshot["support_requests"][0]["recent_responses"]] == [
        "대응 2",
        "대응 3",
        "대응 4",
    ]
    assert snapshot["support_requests"][0]["occurred_at"] == "2026-08-20T09:00:00+09:00"
    # 팀원은 C/S 화면과 같은 규칙으로 자기가 맡은 건만 본다.
    support_query = str(db.statements[5].compile(dialect=postgresql.dialect()))
    assert "support_request.assignee_member_id" in support_query
    assert "support_request.deleted_at IS NULL" in support_query


@pytest.mark.anyio
async def test_briefing_snapshot_without_support_requests_skips_the_response_query(monkeypatch):
    member, company, _deal, activity = _briefing_fixture()

    async def _retrieve(_db, **_kwargs):
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)

    snapshot = await snapshots.build_briefing_snapshot(
        _briefing_db(member, company, activity, []), member, activity.id
    )

    assert snapshot["support_requests"] == []
    assert snapshot["open_support_request_count"] == 0


@pytest.mark.anyio
async def test_briefing_snapshot_keeps_latest_state_sources_ahead_of_general_rag(monkeypatch):
    member, company, _deal, activity = _briefing_fixture()
    state_source = {
        "document_id": "latest-contract",
        "chunk_id": "latest-contract-chunk",
        "file_name": "최신 계약서.pdf",
        "content": "계약금 30%, 잔금 70%입니다.",
        "source_role": "current_sales_state",
    }
    rag_source = {
        "document_id": "older-quote",
        "chunk_id": "older-quote-chunk",
        "file_name": "이전 견적서.pdf",
        "content": "구매 여부는 미확정입니다.",
    }

    async def _state_sources(_db, **_kwargs):
        return [state_source]

    async def _retrieve(_db, **_kwargs):
        return {
            "query": "테스트 병원",
            "summaries": [],
            # 범용 RAG가 같은 상태 청크를 돌려도 프롬프트에는 한 번만 들어가야 한다.
            "sources": [state_source, rag_source],
        }

    monkeypatch.setattr(snapshots.sales_context, "retrieve_current_state_sources", _state_sources)
    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)

    snapshot = await snapshots.build_briefing_snapshot(
        _briefing_db(member, company, activity, []), member, activity.id
    )

    context = snapshot["document_context"]
    assert context["current_state_sources"] == [state_source]
    assert [source["chunk_id"] for source in context["sources"]] == [
        "latest-contract-chunk",
        "older-quote-chunk",
    ]


@pytest.mark.anyio
async def test_briefing_snapshot_uses_recent_company_deals_when_activity_has_no_deal(monkeypatch):
    member, company, deal, activity = _briefing_fixture()
    activity.sales_deal_id = None
    captured = {}

    async def _retrieve(_db, **kwargs):
        captured.update(kwargs)
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)
    db = _briefing_db(member, company, activity, [(deal, _stage())])

    snapshot = await snapshots.build_briefing_snapshot(db, member, activity.id)

    assert [item["id"] for item in snapshot["sales_deals"]] == [str(deal.id)]
    assert snapshot["briefing_mode"] == "first_meeting"
    assert "sales_deal_id" not in snapshot["approved_next_meeting"]
    assert "candidate_sales_deal_ids" not in snapshot["approved_next_meeting"]
    assert snapshot["approved_next_meeting"]["note"] == "납기와 설치 조건을 확인합니다."
    assert snapshot["approved_next_meeting"]["customer_contact"] == {
        "id": str(activity.customer_contact_id),
        "name": "김테스트",
        "department": "영업기획",
        "job_title": "팀장",
    }
    assert captured["customer_company_id"] == company.id
    open_deals_query = db.statements[2].compile(dialect=postgresql.dialect())
    assert "phase_code !=" not in str(open_deals_query)
    assert "LIMIT" not in str(open_deals_query)


@pytest.mark.anyio
async def test_briefing_snapshot_does_not_call_a_later_meeting_first_when_reports_are_empty(
    monkeypatch,
):
    member, company, _deal_row, activity = _briefing_fixture()

    async def _retrieve(_db, **_kwargs):
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)
    db = _briefing_db(member, company, activity, [], has_prior_meeting=True)

    snapshot = await snapshots.build_briefing_snapshot(db, member, activity.id)

    assert snapshot["recent_reports"] == []
    assert snapshot["briefing_mode"] == "relationship"


@pytest.mark.anyio
async def test_briefing_snapshot_carries_three_recent_reports_instead_of_risks(monkeypatch):
    member, company, deal, activity = _briefing_fixture()
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=None,
        report_date=date(2026, 9, 1),
        common_body=None,
        unassigned_body=None,
    )
    section = SimpleNamespace(
        sales_deal_id=deal.id,
        title="계약 협의",
        body="고객이 납기 확인을 요청했습니다.",
    )

    async def _retrieve(_db, **_kwargs):
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)

    db = _briefing_db(member, company, activity, [(deal, _stage())], reports=[(report, section)])
    snapshot = await snapshots.build_briefing_snapshot(db, member, activity.id)

    assert snapshot["recent_reports"][0]["id"] == str(report.id)
    assert snapshot["briefing_mode"] == "relationship"
    assert snapshot["recent_reports"][0]["deal_reports"][0]["body"] == (
        "고객이 납기 확인을 요청했습니다."
    )
    assert "risk_signals" not in snapshot
    report_query = db.statements[3].compile(dialect=postgresql.dialect())
    assert 4 in report_query.params.values()


@pytest.mark.anyio
async def test_briefing_snapshot_carries_company_common_report_without_an_open_deal(monkeypatch):
    member, company, _deal_row, activity = _briefing_fixture()
    activity.sales_deal_id = None
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=uuid4(),
        report_date=date(2026, 9, 15),
        common_body="고객사가 오늘 저녁에 다시 논의하기로 했습니다.",
        unassigned_body=None,
    )

    async def _retrieve(_db, **_kwargs):
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)

    db = _briefing_db(member, company, activity, [], reports=[(report, None)])
    snapshot = await snapshots.build_briefing_snapshot(db, member, activity.id)

    assert snapshot["sales_deals"] == []
    assert snapshot["recent_reports"] == [
        {
            "id": str(report.id),
            "submission_id": snapshot["recent_reports"][0]["submission_id"],
            "source_activity_id": str(report.source_activity_id),
            "report_date": "2026-09-15",
            "submitted_at": "2026-09-02T00:00:00+00:00",
            "title": None,
            "meeting_shared": {
                "common_report": "고객사가 오늘 저녁에 다시 논의하기로 했습니다.",
                "unassigned_report": None,
            },
            "deal_reports": [],
        }
    ]
    report_query = str(db.statements[3])
    assert "report_submission.id = public.report.current_submission_id" in report_query


@pytest.mark.anyio
async def test_briefing_snapshot_links_product_document_mentioned_in_prior_report(monkeypatch):
    member, company, _deal_row, activity = _briefing_fixture()
    activity.sales_deal_id = None
    product_id = uuid4()
    report = SimpleNamespace(
        id=uuid4(),
        source_activity_id=uuid4(),
        report_date=date(2026, 9, 15),
        common_body="다음 미팅에서는 LR1000 도입 조건을 논의합니다.",
        unassigned_body=None,
    )
    document = SimpleNamespace(
        id=uuid4(),
        document_no="DOC-1",
        category_code="product_brochure",
        title="LR1000 상품설명서",
    )
    file_row = SimpleNamespace(
        id=uuid4(),
        file_name="LR1000.pdf",
        version_no=1,
        summary_markdown="LR1000 제품 요약",
        uploaded_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    captured = {}

    async def _retrieve(_db, **kwargs):
        captured.update(kwargs)
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)
    db = _briefing_db(
        member,
        company,
        activity,
        [],
        reports=[(report, None)],
        mentioned_products=[(product_id, "LR1000")],
        product_documents=[(document, file_row)],
    )

    snapshot = await snapshots.build_briefing_snapshot(db, member, activity.id)

    assert captured["product_ids"] == {product_id}
    assert captured["query"].endswith("LR1000")
    assert snapshot["document_context"]["product_documents"][0]["document_id"] == str(document.id)


@pytest.mark.anyio
async def test_briefing_snapshot_sends_meeting_time_in_seoul(monkeypatch):
    """화면이 서울 시간으로 보여 주는 미팅을 LLM 이 UTC 로 받으면 본문 시각이 어긋난다."""
    member, company, deal, activity = _briefing_fixture()

    async def _retrieve(_db, **_kwargs):
        return {"query": "", "summaries": [], "sources": []}

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)

    snapshot = await snapshots.build_briefing_snapshot(
        _briefing_db(member, company, activity, [(deal, _stage())]),
        member,
        activity.id,
    )

    # 2026-09-03 05:00 UTC == 같은 날 14:00 KST
    assert snapshot["approved_next_meeting"]["starts_at"] == "2026-09-03T14:00:00+09:00"
    assert snapshot["approved_next_meeting"]["ends_at"] == "2026-09-03T15:00:00+09:00"


@pytest.mark.anyio
async def test_briefing_snapshot_keeps_working_when_document_search_fails(monkeypatch):
    """자료요약이 멈춰도 브리핑은 나와야 한다 — 빈 문맥으로 되돌린다."""
    member, company, deal, activity = _briefing_fixture()

    async def _retrieve(_db, **_kwargs):
        raise snapshots.EmbeddingError("embedding_provider_error:500")

    monkeypatch.setattr(snapshots.sales_context, "retrieve_briefing_context", _retrieve)

    snapshot = await snapshots.build_briefing_snapshot(
        _briefing_db(member, company, activity, [(deal, _stage())]),
        member,
        activity.id,
    )

    assert snapshot["document_context"]["summaries"] == []
    assert snapshot["document_context"]["sources"] == []
    # 브리핑 본체는 그대로 만들어진다.
    assert snapshot["customer_company"]["name"] == "테스트 병원"
    assert snapshot["approved_next_meeting"]["activity_id"] == str(activity.id)
