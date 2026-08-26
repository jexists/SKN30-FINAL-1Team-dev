import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.agents import contract_management


def test_risk_rejects_unknown_code_and_extra_fields():
    valid_risk = {
        "code": "contract_expiring",
        "severity": "high",
        "message": "계약 종료일이 임박했습니다.",
        "source_refs": [{"type": "sales_deal", "id": "deal-1"}],
    }

    risk = contract_management.ContractRisk(**valid_risk)
    assert risk.code == "contract_expiring"
    assert risk.source_refs[0].id == "deal-1"

    with pytest.raises(ValidationError):
        contract_management.ContractRisk(
            **{**valid_risk, "code": "invented_risk"},
        )

    with pytest.raises(ValidationError):
        contract_management.NextMeetingProposalOutput(
            risks=[],
            unexpected="허용되지 않는 값",
        )


def test_risk_requires_at_least_one_source_ref():
    """근거 없는 위험 판정을 막는다 — source_refs가 비어 있으면 거절한다."""
    with pytest.raises(ValidationError):
        contract_management.ContractRisk(
            code="contract_expiring",
            severity="high",
            message="계약 종료일이 임박했습니다.",
            source_refs=[],
        )


def test_source_ref_accepts_document_type_for_rag_citations():
    ref = contract_management.SourceRef(type="document", id="doc-1")
    assert ref.type == "document"


def test_briefing_output_source_refs_default_empty_and_accept_document_refs():
    empty = contract_management.ContractBriefingOutput(contract_summary="자료 없음")
    assert empty.source_refs == []

    cited = contract_management.ContractBriefingOutput(
        contract_summary="자료실 문서를 근거로 작성했습니다.",
        source_refs=[contract_management.SourceRef(type="document", id="doc-1")],
    )
    assert cited.source_refs[0].type == "document"


def test_next_meeting_duration_is_bounded():
    valid = {
        "sales_deal_id": "deal-1",
        "reason": "계약 종료 전 조건 협의가 필요합니다.",
    }

    assert contract_management.NextMeetingSuggestion(**valid).duration_minutes == 60

    with pytest.raises(ValidationError):
        contract_management.NextMeetingSuggestion(**valid, duration_minutes=4)

    with pytest.raises(ValidationError):
        contract_management.NextMeetingSuggestion(**valid, duration_minutes=481)


def test_next_meeting_proposal_output_has_no_briefing_field():
    """1차 실행 출력에는 브리핑이 없어야 한다 — 브리핑은 재진입 실행에서만 만든다."""
    assert "contract_summary" not in contract_management.NextMeetingProposalOutput.model_fields


def test_briefing_output_has_no_next_meeting_field():
    """재진입 실행 출력에는 다음 미팅 제안이 없어야 한다 — 이미 1차 실행에서 결정됐다."""
    assert "next_meeting_suggestion" not in contract_management.ContractBriefingOutput.model_fields


@pytest.mark.anyio
async def test_select_next_meeting_candidates_uses_dedicated_prompt_schema_and_snapshot(
    monkeypatch,
):
    captured = {}
    expected = contract_management.SelectNextMeetingCandidatesOutput(
        candidates=[
            contract_management.SelectedNextMeetingCandidate(
                customer_company_id="company-1",
                sales_deal_id="deal-1",
                reason="계약 만료가 7일 남았습니다.",
                priority=90,
            )
        ]
    )

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(contract_management, "generate_structured", fake_generate_structured)
    candidates = [
        {
            "customer_company_id": "company-1",
            "customer_company_name": "테스트 병원",
            "sales_deal_id": "deal-1",
            "sales_deal_title": "테스트 딜",
            "stage_code": "contract_review",
            "stage_phase_code": "contract",
            "risk_signals": [{"code": "contract_expiring", "severity": "high"}],
        }
    ]
    snapshot = {"candidates": candidates}

    result = await contract_management.select_next_meeting_candidates(snapshot)

    assert result == expected
    assert captured["instructions"] == contract_management.SELECT_CANDIDATES_SYSTEM_PROMPT
    assert captured["schema"] is contract_management.SelectNextMeetingCandidatesOutput
    assert captured["schema_name"] == "contract_management_select_candidates"
    assert json.loads(captured["input_text"]) == {"candidates": candidates}


@pytest.mark.anyio
async def test_select_next_meeting_candidates_drops_unknown_deal_ids(monkeypatch):
    """LLM이 입력에 없는 딜을 지어내면 걸러낸다 — 근거 없는 선택은 통과시키지 않는다."""

    async def fake_generate_structured(**kwargs):
        return contract_management.SelectNextMeetingCandidatesOutput(
            candidates=[
                contract_management.SelectedNextMeetingCandidate(
                    customer_company_id="company-1",
                    sales_deal_id="deal-1",
                    reason="입력에 있는 딜",
                    priority=80,
                ),
                contract_management.SelectedNextMeetingCandidate(
                    customer_company_id="company-9",
                    sales_deal_id="deal-invented",
                    reason="입력에 없는 딜",
                    priority=99,
                ),
            ]
        )

    monkeypatch.setattr(contract_management, "generate_structured", fake_generate_structured)
    snapshot = {
        "candidates": [
            {
                "customer_company_id": "company-1",
                "customer_company_name": "테스트 병원",
                "sales_deal_id": "deal-1",
                "sales_deal_title": "테스트 딜",
                "stage_code": "contract_review",
                "stage_phase_code": "contract",
                "risk_signals": [{"code": "contract_expiring", "severity": "high"}],
            }
        ]
    }

    result = await contract_management.select_next_meeting_candidates(snapshot)

    assert [c.sales_deal_id for c in result.candidates] == ["deal-1"]


@pytest.mark.anyio
async def test_propose_next_meeting_uses_dedicated_prompt_schema_and_snapshot(monkeypatch):
    fixed_now = datetime(2026, 8, 26, 9, 0, tzinfo=contract_management._SEOUL)
    monkeypatch.setattr(contract_management, "_now", lambda: fixed_now)
    captured = {}
    expected = contract_management.NextMeetingProposalOutput(
        risks=[
            contract_management.ContractRisk(
                code="quote_expiring",
                severity="medium",
                message="견적 유효기간이 임박했습니다.",
                source_refs=[contract_management.SourceRef(type="sales_deal", id="deal-1")],
            )
        ],
        missing_information=[],
        recommended_actions=["견적 갱신 여부를 확인합니다."],
    )

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(contract_management, "generate_structured", fake_generate_structured)
    risk_signals = [
        {
            "code": "quote_expiring",
            "severity": "medium",
            "sales_deal_id": "deal-1",
        }
    ]
    snapshot = {
        "customer_company": {"id": "company-1", "name": "테스트 병원"},
        "risk_signals": risk_signals,
        # 허용 목록에 없는 값은 LLM에 전달되면 안 된다.
        "internal_notes": "이 값은 프롬프트로 나가면 안 된다",
    }

    result = await contract_management.propose_next_meeting(snapshot)

    assert result == expected
    assert captured["instructions"] == contract_management.PROPOSE_NEXT_MEETING_SYSTEM_PROMPT
    assert captured["schema"] is contract_management.NextMeetingProposalOutput
    assert captured["schema_name"] == "contract_management_propose_next_meeting"
    assert json.loads(captured["input_text"]) == {
        "customer_company": {"id": "company-1", "name": "테스트 병원"},
        "sales_deals": [],
        "risk_signals": risk_signals,
        "recent_approved_reports": [],
        "current_date": fixed_now.isoformat(),
    }


@pytest.mark.anyio
async def test_generate_briefing_uses_dedicated_prompt_schema_and_snapshot(monkeypatch):
    captured = {}
    expected = contract_management.ContractBriefingOutput(
        contract_summary="다음 미팅이 승인되어 계약 갱신 협의를 진행 중입니다.",
        risks=[],
        missing_information=["승인된 미팅 분석 결과 연동 대기 중입니다."],
        recommended_actions=[],
    )

    async def fake_generate_structured(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(contract_management, "generate_structured", fake_generate_structured)
    approved_next_meeting = {
        "sales_deal_id": "deal-1",
        "starts_at": "2026-08-25T14:00:00+09:00",
    }
    snapshot = {
        "customer_company": {"id": "company-1", "name": "테스트 병원"},
        "approved_next_meeting": approved_next_meeting,
        "document_summaries": [],
        # 허용 목록에 없는 값은 LLM에 전달되면 안 된다.
        "internal_notes": "이 값은 프롬프트로 나가면 안 된다",
    }

    result = await contract_management.generate_briefing(snapshot)

    assert result == expected
    assert captured["instructions"] == contract_management.GENERATE_BRIEFING_SYSTEM_PROMPT
    assert captured["schema"] is contract_management.ContractBriefingOutput
    assert captured["schema_name"] == "contract_management_generate_briefing"
    assert json.loads(captured["input_text"]) == {
        "customer_company": {"id": "company-1", "name": "테스트 병원"},
        "sales_deals": [],
        "approved_next_meeting": approved_next_meeting,
        "document_summaries": [],
    }
