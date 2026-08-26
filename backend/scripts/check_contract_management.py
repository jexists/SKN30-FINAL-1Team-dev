"""합성 딜 입력으로 실제 계약관리 에이전트(선별·1차 제안·브리핑)를 확인한다."""

import asyncio
import json
import os
import sys

_URGENT_DEAL_ID = "deal-urgent-1"
_MILD_DEAL_ID = "deal-mild-1"
_STAGE_EARLY_DEAL_ID = "deal-stage-early-1"
_STAGE_LATE_DEAL_ID = "deal-stage-late-1"

_CANDIDATE_SELECTION_SNAPSHOT = {
    "candidates": [
        {
            "customer_company_id": "company-urgent-1",
            "customer_company_name": "긴급 병원",
            "sales_deal_id": _URGENT_DEAL_ID,
            "sales_deal_title": "긴급 병원 계약 갱신",
            "stage_code": "contract_review",
            "stage_phase_code": "contract",
            "risk_signals": [
                {
                    "code": "contract_expiring",
                    "severity": "high",
                    "sales_deal_id": _URGENT_DEAL_ID,
                    "source_refs": [{"type": "sales_deal", "id": _URGENT_DEAL_ID}],
                    "detail": "contract_ends_on=2026-09-01",
                }
            ],
        },
        {
            "customer_company_id": "company-mild-1",
            "customer_company_name": "여유 병원",
            "sales_deal_id": _MILD_DEAL_ID,
            "sales_deal_title": "여유 병원 후속 미팅",
            "stage_code": "product_demo",
            "stage_phase_code": "negotiation",
            "risk_signals": [
                {
                    "code": "follow_up_overdue",
                    "severity": "medium",
                    "sales_deal_id": _MILD_DEAL_ID,
                    "source_refs": [{"type": "sales_deal", "id": _MILD_DEAL_ID}],
                    "detail": "days_since_contact=32",
                }
            ],
        },
        # 위험 신호(종류·심각도)는 동일하게 두고 영업 단계만 다르게 해서, 프롬프트에 넣은
        # 단계별 중요도 기준(needs_validation < ... < contract_completed)만으로 실제 priority
        # 순서가 바뀌는지 확인한다.
        {
            "customer_company_id": "company-stage-early-1",
            "customer_company_name": "초기 단계 병원",
            "sales_deal_id": _STAGE_EARLY_DEAL_ID,
            "sales_deal_title": "초기 단계 병원 니즈 검증",
            "stage_code": "needs_validation",
            "stage_phase_code": "sales",
            "risk_signals": [
                {
                    "code": "follow_up_overdue",
                    "severity": "medium",
                    "sales_deal_id": _STAGE_EARLY_DEAL_ID,
                    "source_refs": [{"type": "sales_deal", "id": _STAGE_EARLY_DEAL_ID}],
                    "detail": "days_since_contact=32",
                }
            ],
        },
        {
            "customer_company_id": "company-stage-late-1",
            "customer_company_name": "계약완료 단계 병원",
            "sales_deal_id": _STAGE_LATE_DEAL_ID,
            "sales_deal_title": "계약완료 단계 병원 후속 관리",
            "stage_code": "contract_completed",
            "stage_phase_code": "contract",
            "risk_signals": [
                {
                    "code": "follow_up_overdue",
                    "severity": "medium",
                    "sales_deal_id": _STAGE_LATE_DEAL_ID,
                    "source_refs": [{"type": "sales_deal", "id": _STAGE_LATE_DEAL_ID}],
                    "detail": "days_since_contact=32",
                }
            ],
        },
    ]
}

_NEXT_MEETING_SNAPSHOT = {
    "customer_company": {"id": "company-demo-1", "name": "합성 테스트 병원"},
    "sales_deals": [
        {
            "id": "deal-demo-1",
            "title": "의료기기 신규 도입",
            "stage_phase_code": "product_demo",
            "deal_amount": 10_000_000,
            "quote_valid_until": "2026-09-08",
        }
    ],
    "risk_signals": [
        {
            "code": "quote_expiring",
            "severity": "high",
            "sales_deal_id": "deal-demo-1",
            "source_refs": [{"type": "sales_deal", "id": "deal-demo-1"}],
            "detail": "quote_valid_until=2026-09-08",
        }
    ],
    "recent_approved_reports": [],
}

_BRIEFING_SNAPSHOT = {
    "customer_company": {"id": "company-demo-1", "name": "합성 테스트 병원"},
    "sales_deals": _NEXT_MEETING_SNAPSHOT["sales_deals"],
    "approved_next_meeting": {
        "activity_id": "activity-demo-1",
        "sales_deal_id": "deal-demo-1",
        "title": "도입 범위 및 견적 검토",
        "starts_at": "2026-09-02T14:00:00+09:00",
        "ends_at": "2026-09-02T14:30:00+09:00",
        "location": "합성 테스트 병원",
    },
    "document_summaries": [],
}


async def check() -> None:
    os.environ["DEBUG"] = "false"

    from app.agents import contract_management
    from app.core.config import settings

    if not settings.llm_configured:
        raise RuntimeError("LLM_API_URL, LLM_API_KEY, LLM_MODEL 설정이 필요합니다.")

    print("[0차 선별 요청]")
    print(json.dumps(_CANDIDATE_SELECTION_SNAPSHOT, ensure_ascii=False, indent=2))
    selection = await contract_management.select_next_meeting_candidates(
        _CANDIDATE_SELECTION_SNAPSHOT
    )
    print("[0차 선별 응답]")
    print(json.dumps(selection.model_dump(), ensure_ascii=False, indent=2))

    if not selection.candidates:
        raise ValueError("위험 신호가 있는데도 아무 딜도 선별하지 않았습니다.")
    known_deal_ids = {_URGENT_DEAL_ID, _MILD_DEAL_ID, _STAGE_EARLY_DEAL_ID, _STAGE_LATE_DEAL_ID}
    for candidate in selection.candidates:
        if candidate.sales_deal_id not in known_deal_ids:
            raise ValueError(f"입력에 없는 딜을 선별했습니다: {candidate.sales_deal_id}")
        if not candidate.reason.strip():
            raise ValueError("선별 이유가 비어 있습니다.")

    # 위험 신호는 동일하고 영업 단계만 다른 두 딜로, 단계별 중요도 기준이 실제 priority 순서를
    # 바꾸는지 확인한다. priority는 숫자가 작을수록 시급하다 — 계약 완료 단계가 니즈 검증
    # 단계보다 우선(더 작은 숫자)이어야 한다.
    priority_by_deal = {c.sales_deal_id: c.priority for c in selection.candidates}
    if _STAGE_EARLY_DEAL_ID not in priority_by_deal or _STAGE_LATE_DEAL_ID not in priority_by_deal:
        raise ValueError("영업 단계 비교용 두 딜(초기/계약완료) 중 일부가 선별되지 않았습니다.")
    early_priority = priority_by_deal[_STAGE_EARLY_DEAL_ID]
    late_priority = priority_by_deal[_STAGE_LATE_DEAL_ID]
    if late_priority >= early_priority:
        raise ValueError(
            "영업 단계가 뒤인(계약 완료) 딜의 priority가 앞선(니즈 검증) 딜보다 시급하지"
            f" 않습니다: early(니즈 검증)={early_priority}, late(계약 완료)={late_priority}"
        )

    print("\n[1차 제안 요청]")
    print(json.dumps(_NEXT_MEETING_SNAPSHOT, ensure_ascii=False, indent=2))
    proposal = await contract_management.propose_next_meeting(_NEXT_MEETING_SNAPSHOT)
    print("[1차 제안 응답]")
    print(json.dumps(proposal.model_dump(), ensure_ascii=False, indent=2))

    known_codes = {signal["code"] for signal in _NEXT_MEETING_SNAPSHOT["risk_signals"]}
    for risk in proposal.risks:
        if risk.code not in known_codes:
            raise ValueError(f"risk_signals에 없는 위험을 만들었습니다: {risk.code}")
        if not risk.source_refs:
            raise ValueError("근거 없는 위험 판정이 있습니다.")

    print("\n[브리핑 요청]")
    print(json.dumps(_BRIEFING_SNAPSHOT, ensure_ascii=False, indent=2))
    briefing = await contract_management.generate_briefing(_BRIEFING_SNAPSHOT)
    print("[브리핑 응답]")
    print(json.dumps(briefing.model_dump(), ensure_ascii=False, indent=2))

    if not briefing.contract_summary.strip():
        raise ValueError("contract_summary가 비어 있습니다.")


def main() -> int:
    try:
        asyncio.run(check())
    except Exception as error:
        print(f"[실패] {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print("\n[성공] 실제 계약관리 에이전트(선별·1차 제안·브리핑) 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
