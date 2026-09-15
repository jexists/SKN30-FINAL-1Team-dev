"""실제 LLM으로 계약 1차 제안 → 일정 추천 → 계약 브리핑을 확인한다."""

import json

import pytest

from app.agents import contract_management, schedule_management
from app.core.config import settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not settings.run_integration_tests or not settings.llm_configured,
        reason="실통합 테스트 비활성화 또는 LLM 미설정",
    ),
]


def _print_json(title: str, value) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _standalone_candidate_selection_input() -> dict:
    """담당자가 맡은 딜 세 건. 위험 신호 심각도와 개수가 서로 다르다."""
    return {
        "candidates": [
            {
                "customer_company_id": "company-urgent-1",
                "customer_company_name": "긴급 병원",
                "sales_deal_id": "deal-urgent-1",
                "sales_deal_title": "긴급 병원 계약 갱신",
                "stage_code": "contract_review",
                "stage_phase_code": "contract",
                "risk_signals": [
                    {
                        "code": "contract_expiring",
                        "severity": "high",
                        "sales_deal_id": "deal-urgent-1",
                        "source_refs": [{"type": "sales_deal", "id": "deal-urgent-1"}],
                        "detail": "contract_ends_on=2026-09-01",
                    },
                    {
                        "code": "unresolved_support",
                        "severity": "high",
                        "sales_deal_id": None,
                        "source_refs": [{"type": "support_request", "id": "support-1"}],
                        "detail": "장비 오작동 미해결 C/S",
                    },
                ],
            },
            {
                "customer_company_id": "company-mild-1",
                "customer_company_name": "여유 병원",
                "sales_deal_id": "deal-mild-1",
                "sales_deal_title": "여유 병원 후속 미팅",
                "stage_code": "product_demo",
                "stage_phase_code": "negotiation",
                "risk_signals": [
                    {
                        "code": "follow_up_overdue",
                        "severity": "medium",
                        "sales_deal_id": "deal-mild-1",
                        "source_refs": [{"type": "sales_deal", "id": "deal-mild-1"}],
                        "detail": "days_since_contact=32",
                    }
                ],
            },
            {
                "customer_company_id": "company-quote-1",
                "customer_company_name": "견적 병원",
                "sales_deal_id": "deal-quote-1",
                "sales_deal_title": "견적 병원 견적 만료 임박",
                "stage_code": "quote_sent",
                "stage_phase_code": "quotation",
                "risk_signals": [
                    {
                        "code": "quote_expiring",
                        "severity": "high",
                        "sales_deal_id": "deal-quote-1",
                        "source_refs": [{"type": "sales_deal", "id": "deal-quote-1"}],
                        "detail": "quote_valid_until=2026-08-27",
                    }
                ],
            },
        ]
    }


def _standalone_contract_input() -> dict:
    return {
        "customer_company": {"id": "company-demo-1", "name": "AI 브리핑 테스트 병원"},
        "sales_deals": [
            {
                "id": "deal-demo-1",
                "deal_no": "DEMO-AI-001",
                "title": "의료기기 신규 도입",
                "stage_code": "product_demo",
                "stage_name": "제품 시연 평가",
                "deal_amount": 10_000_000,
                "quote_valid_until": "2026-09-08",
            }
        ],
        "risk_signals": [
            {
                "code": "quote_expiring",
                "severity": "high",
                "message": "견적 유효기간이 14일 이내로 남았습니다.",
                "source_refs": [{"type": "sales_deal", "id": "deal-demo-1"}],
            }
        ],
        "recent_approved_reports": [],
    }


def _standalone_schedule_input() -> dict:
    target_date = schedule_management._now().date().isoformat()
    return {
        "sales_deal_id": "deal-demo-1",
        "target_date": target_date,
        "target_time": None,
        "reason": "견적 만료 전에 의사결정권자 미팅이 필요합니다.",
        "recommendation_status": "pending",
        "deal_outcome_code": "in_progress",
        "excluded_dates": [],
        "current_datetime": schedule_management._now().isoformat(),
        "timezone": "Asia/Seoul",
    }


def _standalone_briefing_input() -> dict:
    return {
        "customer_company": {"id": "company-demo-1", "name": "AI 브리핑 테스트 병원"},
        "sales_deals": _standalone_contract_input()["sales_deals"],
        "recent_reports": [
            {
                "id": "report-demo-1",
                "sales_deal_id": "deal-demo-1",
                "source_activity_id": "activity-previous-1",
                "report_date": "2026-08-25",
                "content": {
                    "values": {
                        "body": "고객은 제품 시연 후 도입 범위와 최종 견적을 검토하기로 했습니다."
                    }
                },
            }
        ],
        "approved_next_meeting": {
            "activity_id": "activity-approved-candidate-1",
            "sales_deal_id": "deal-demo-1",
            "title": "제품 도입 최종 검토 미팅",
            "starts_at": "2026-09-02T14:00:00+09:00",
            "ends_at": "2026-09-02T15:00:00+09:00",
            "location": "AI 브리핑 테스트 병원",
        },
    }


@pytest.mark.anyio
async def test_select_next_meeting_candidates_with_real_llm():
    agent_input = _standalone_candidate_selection_input()
    llm_input = contract_management._CandidateSelectionLLMInput(**agent_input).model_dump()

    _print_json("SELECT CANDIDATES INPUT", llm_input)
    output = await contract_management.select_next_meeting_candidates(agent_input)
    _print_json("SELECT CANDIDATES OUTPUT", output.model_dump())

    known_deal_ids = {c["sales_deal_id"] for c in agent_input["candidates"]}
    assert output.candidates, "위험 신호가 있는데도 아무 딜도 선별하지 않았습니다."
    assert all(c.sales_deal_id in known_deal_ids for c in output.candidates)
    assert all(c.reason.strip() for c in output.candidates)


@pytest.mark.anyio
async def test_contract_next_meeting_with_real_llm():
    agent_input = _standalone_contract_input()
    llm_input = contract_management._NextMeetingLLMInput(
        **agent_input,
        current_datetime=contract_management._now().isoformat(),
        excluded_dates=[],
    ).model_dump()

    _print_json("CONTRACT NEXT MEETING INPUT", llm_input)
    output = await contract_management.propose_next_meeting(agent_input)
    _print_json("CONTRACT NEXT MEETING OUTPUT", output.model_dump())

    assert "internal_member_email" not in llm_input


@pytest.mark.anyio
async def test_schedule_management_with_real_llm():
    agent_input = _standalone_schedule_input()
    llm_input = schedule_management._ScheduleLLMInput(
        **{key: agent_input[key] for key in schedule_management._ScheduleLLMInput.model_fields},
    ).model_dump()

    _print_json("SCHEDULE MANAGEMENT INPUT", llm_input)
    output = await schedule_management.run(agent_input)
    _print_json("SCHEDULE MANAGEMENT OUTPUT", output.model_dump())

    assert output.decision == "valid"


@pytest.mark.anyio
async def test_contract_briefing_with_real_llm():
    agent_input = _standalone_briefing_input()
    llm_input = contract_management._BriefingLLMInput(**agent_input).model_dump()

    _print_json("CONTRACT BRIEFING INPUT", llm_input)
    output = await contract_management.generate_briefing(agent_input)
    _print_json("CONTRACT BRIEFING OUTPUT", output.model_dump())

    assert output.highlights
    assert llm_input["approved_next_meeting"]["activity_id"]


@pytest.mark.anyio
async def test_contract_schedule_briefing_pipeline_with_real_llm():
    contract_input = {
        "customer_company": {"id": "company-demo-1", "name": "AI 브리핑 테스트 병원"},
        "sales_deals": [
            {
                "id": "deal-demo-1",
                "deal_no": "DEMO-AI-001",
                "title": "의료기기 신규 도입",
                "stage_code": "product_demo",
                "stage_name": "제품 시연 평가",
                "deal_amount": 10_000_000,
                "quote_valid_until": "2026-09-08",
            }
        ],
        "risk_signals": [
            {
                "code": "quote_expiring",
                "severity": "high",
                "message": "견적 유효기간이 14일 이내로 남았습니다.",
                "source_refs": [{"type": "sales_deal", "id": "deal-demo-1"}],
            }
        ],
        "recent_approved_reports": [
            {
                "id": "report-demo-1",
                "report_date": "2026-08-25",
                "content": {
                    "customer_need": "제품 시연 후 도입 범위와 최종 견적 검토",
                    "next_action": "견적 만료 전 의사결정권자 미팅",
                },
            }
        ],
        "internal_member_email": "should-not-be-sent@example.com",
    }
    contract_llm_input = contract_management._NextMeetingLLMInput(
        customer_company=contract_input["customer_company"],
        sales_deals=contract_input["sales_deals"],
        risk_signals=contract_input["risk_signals"],
        recent_approved_reports=contract_input["recent_approved_reports"],
        current_datetime=contract_management._now().isoformat(),
        excluded_dates=[],
    ).model_dump()
    _print_json("1. CONTRACT NEXT MEETING INPUT", contract_llm_input)
    proposal = await contract_management.propose_next_meeting(contract_input)
    _print_json("1. CONTRACT NEXT MEETING OUTPUT", proposal.model_dump())

    suggestion = proposal.next_meeting_suggestion
    if suggestion is None:
        print(
            "\n[INFO] 계약 에이전트가 미팅 제안을 생략했습니다. "
            "세 단계 확인을 위해 테스트 기본 일정 범위를 사용합니다."
        )

    schedule_input = {
        "sales_deal_id": suggestion.sales_deal_id if suggestion else "deal-demo-1",
        "target_date": (
            suggestion.target_date.isoformat()
            if suggestion
            else schedule_management._now().date().isoformat()
        ),
        "target_time": (
            suggestion.target_time.isoformat() if suggestion and suggestion.target_time else None
        ),
        "reason": (
            suggestion.reason
            if suggestion
            else "견적 유효기간 전에 제품 도입 범위와 최종 견적을 검토해야 합니다."
        ),
        "recommendation_status": "pending",
        "deal_outcome_code": "in_progress",
        "excluded_dates": [],
        "current_datetime": schedule_management._now().isoformat(),
        "timezone": "Asia/Seoul",
    }
    schedule_llm_input = schedule_management._ScheduleLLMInput(
        **{key: schedule_input[key] for key in schedule_management._ScheduleLLMInput.model_fields},
    ).model_dump()
    _print_json("2. SCHEDULE MANAGEMENT INPUT", schedule_llm_input)
    schedule = await schedule_management.run(schedule_input)
    _print_json("2. SCHEDULE MANAGEMENT OUTPUT", schedule.model_dump())

    assert schedule.decision == "valid"
    # 사용자 승인 단계: 60분과 10시를 선택했다고 가정한다.
    approved_activity_id = "activity-created-from-candidate-1"
    _print_json(
        "USER APPROVAL (FIRST CANDIDATE)",
        {
            "selected_duration_minutes": 60,
            "selected_start_time": "10:00",
            "created_activity_id": approved_activity_id,
        },
    )

    briefing_input = {
        "customer_company": contract_input["customer_company"],
        "sales_deals": contract_input["sales_deals"],
        "recent_reports": [
            {
                "id": "report-demo-1",
                "sales_deal_id": "deal-demo-1",
                "source_activity_id": "activity-previous-1",
                "report_date": "2026-08-25",
                "content": {
                    "values": {
                        "body": "고객은 제품 시연 후 도입 범위와 최종 견적을 검토하기로 했습니다."
                    }
                },
            }
        ],
        "approved_next_meeting": {
            "activity_id": approved_activity_id,
            "sales_deal_id": schedule_input["sales_deal_id"],
            "title": "제품 도입 최종 검토 미팅",
            "starts_at": f"{schedule_input['target_date']}T10:00:00+09:00",
            "ends_at": f"{schedule_input['target_date']}T11:00:00+09:00",
            "location": "AI 브리핑 테스트 병원",
        },
    }
    briefing_llm_input = contract_management._BriefingLLMInput(
        customer_company=briefing_input["customer_company"],
        sales_deals=briefing_input["sales_deals"],
        approved_next_meeting=briefing_input["approved_next_meeting"],
        recent_reports=briefing_input["recent_reports"],
    ).model_dump()
    _print_json("3. CONTRACT BRIEFING INPUT", briefing_llm_input)
    briefing = await contract_management.generate_briefing(briefing_input)
    _print_json("3. CONTRACT BRIEFING OUTPUT", briefing.model_dump())

    assert "internal_member_email" not in contract_llm_input
    assert schedule_llm_input["target_date"] == schedule_input["target_date"]
    assert briefing.highlights
    assert briefing_input["approved_next_meeting"]["activity_id"] == approved_activity_id
