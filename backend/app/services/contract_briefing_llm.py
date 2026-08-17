"""계약 브리핑을 종합하는 자리. 실제 LLM을 부르는 인터페이스를 먼저 만들고,
API 키가 없는 지금은 같은 인터페이스를 만족하는 목업을 대신 꽂아 둔다.

위험 탐지 자체는 이미 결정적으로 끝나 있다(contract_risk_engine). 여기서는
그 결과를 근거로 브리핑 문장, 우선순위, 고객 인사이트 종합만 만든다 — 여러
데이터를 엮어 판단하는 부분이라 실제로 LLM이 값어치를 하는 지점이다.
"""

from typing import Protocol

from app.core.config import Settings
from app.schemas.contract_briefing import (
    ApprovedMeetingInsight,
    BriefingPriority,
    ContractBriefingSynthesis,
    ContractEvidenceBundle,
    ContractRiskAssessment,
)

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


class ContractBriefingSynthesizer(Protocol):
    async def synthesize(self, evidence: ContractEvidenceBundle) -> ContractBriefingSynthesis: ...


class MockContractBriefingSynthesizer:
    """실제 LLM 대신 인터페이스 계약만 만족하는 대역.

    나중에 AnthropicContractBriefingSynthesizer로 바꿔도 호출부
    (get_contract_briefing_synthesizer 사용처)는 그대로다.
    """

    async def synthesize(self, evidence: ContractEvidenceBundle) -> ContractBriefingSynthesis:
        priority, priority_reason = _determine_priority(evidence.risk_assessment)
        return ContractBriefingSynthesis(
            narrative=_build_narrative(evidence),
            priority=priority,
            priority_reason=priority_reason,
            customer_insight_summary=_customer_insight_summary(evidence.approved_meeting_insight),
            cited_evidence=_cited_evidence(evidence),
        )


class AnthropicContractBriefingSynthesizer:
    """실 연동 자리. API 키가 오면 이 클래스 안쪽만 채운다.

    지금은 패키지도 안 깔려 있고 키도 없어서, 생성 시점에 명확한 이유와
    함께 실패한다 — 죽은 코드가 아니라 다음 단계를 위한 자리라는 뜻이다.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-5") -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "anthropic 패키지가 설치돼 있지 않습니다. "
                "실제 연동 시 `uv add anthropic`으로 추가하세요."
            ) from exc
        self._api_key = api_key
        self._model = model

    async def synthesize(self, evidence: ContractEvidenceBundle) -> ContractBriefingSynthesis:
        raise NotImplementedError(
            "AnthropicContractBriefingSynthesizer는 아직 실제 호출 로직이 없습니다. "
            "tool_choice로 ContractBriefingSynthesis 스키마를 강제하는 구조적 출력을 "
            "구현하세요."
        )


def get_contract_briefing_synthesizer(settings: Settings) -> ContractBriefingSynthesizer:
    if settings.llm_provider == "mock":
        return MockContractBriefingSynthesizer()
    if settings.anthropic_api_key is None:
        raise RuntimeError("llm_provider가 anthropic인데 anthropic_api_key가 비어 있습니다.")
    return AnthropicContractBriefingSynthesizer(
        api_key=settings.anthropic_api_key.get_secret_value()
    )


def _determine_priority(assessment: ContractRiskAssessment) -> tuple[BriefingPriority, str]:
    if not assessment.risks:
        if assessment.next_meeting.is_needed:
            return "low", "위험 신호는 없지만 접촉 공백이 있어 다음 미팅을 권장합니다."
        return "low", "위험 신호와 접촉 공백이 모두 없습니다."
    top_risk = max(assessment.risks, key=lambda risk: _SEVERITY_RANK[risk.severity])
    reason = f"{top_risk.kind} 위험이 {top_risk.severity} 등급입니다: {top_risk.message}"
    return top_risk.severity, reason


def _build_narrative(evidence: ContractEvidenceBundle) -> str:
    contract = evidence.contract
    assessment = evidence.risk_assessment
    insight = evidence.approved_meeting_insight

    identifier = contract.contract_no or contract.deal_no
    lines = [f"{contract.customer_company_name} · {contract.title} ({identifier})"]

    if assessment.risks:
        for risk in sorted(
            assessment.risks, key=lambda risk: _SEVERITY_RANK[risk.severity], reverse=True
        ):
            lines.append(f"- {risk.message}")
    else:
        lines.append("- 현재 감지된 위험 신호가 없습니다.")

    if assessment.next_meeting.is_needed and assessment.next_meeting.candidate_date is not None:
        lines.append(f"- 다음 미팅을 {assessment.next_meeting.candidate_date} 무렵 권장합니다.")
    else:
        lines.append("- 다음 미팅이 아직 시급하지 않습니다.")

    if insight is None:
        lines.append("- 승인된 미팅 분석 결과 연동 대기 중입니다.")
    else:
        if insight.needs:
            lines.append(f"- 확인된 니즈: {', '.join(insight.needs)}")
        if insight.purchase_barriers:
            lines.append(f"- 확인된 구매 장벽: {', '.join(insight.purchase_barriers)}")
        if insight.contact_signals:
            lines.append(f"- 접촉 필요 신호: {', '.join(insight.contact_signals)}")
        if insight.next_meeting_agenda:
            lines.append(f"- 다음 미팅 권장 의제: {', '.join(insight.next_meeting_agenda)}")

    return "\n".join(lines)


def _customer_insight_summary(
    insight: ApprovedMeetingInsight | None,
) -> dict[str, list[str]] | None:
    if insight is None:
        return None
    summary = {
        key: value
        for key, value in (
            ("needs", insight.needs),
            ("purchase_barriers", insight.purchase_barriers),
            ("contact_signals", insight.contact_signals),
            ("next_meeting_agenda", insight.next_meeting_agenda),
        )
        if value
    }
    return summary or None


def _cited_evidence(evidence: ContractEvidenceBundle) -> list[str]:
    cited: list[str] = [f"risk:{risk.kind}" for risk in evidence.risk_assessment.risks]
    if evidence.risk_assessment.next_meeting.triggered_by:
        cited.append("next_meeting_candidate")
    if evidence.approved_meeting_insight is not None:
        cited.append("approved_meeting_insight")
    return cited
