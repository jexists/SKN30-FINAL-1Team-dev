from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.schemas.sales_deals import SalesDealRead

RiskKind = Literal["expiry", "delivery", "stale_contact"]
RiskSeverity = Literal["low", "medium", "high"]
BriefingPriority = Literal["low", "medium", "high"]


class RiskItem(BaseModel):
    kind: RiskKind
    severity: RiskSeverity
    message: str
    evidence: dict[str, int | str]


class NextMeetingCandidate(BaseModel):
    is_needed: bool
    candidate_date: date | None
    triggered_by: list[str]


class ContractRiskAssessment(BaseModel):
    risks: list[RiskItem]
    next_meeting: NextMeetingCandidate


class ApprovedMeetingInsight(BaseModel):
    """미팅분석 Agent가 승인된 미팅에서 뽑아줄 값. 아직 그쪽 출력 스키마가
    없어 전부 optional로 두고, 안 오면 브리핑에서 '연동 대기'로 표시한다."""

    needs: list[str] | None = None
    purchase_barriers: list[str] | None = None
    contact_signals: list[str] | None = None
    next_meeting_agenda: list[str] | None = None


class ContractEvidenceBundle(BaseModel):
    """LLM 합성 레이어의 입력. 결정적으로 계산된 값만 담는다."""

    contract: SalesDealRead
    risk_assessment: ContractRiskAssessment
    approved_meeting_insight: ApprovedMeetingInsight | None = None


class ContractBriefingSynthesis(BaseModel):
    """LLM(또는 목업)이 근거를 종합해 만든 결과."""

    narrative: str
    priority: BriefingPriority
    priority_reason: str
    customer_insight_summary: dict[str, list[str]] | None
    cited_evidence: list[str]


class NextMeetingSuggestion(BaseModel):
    """일정관리 Agent로 넘길 값의 자리. 텍스트 제안으로 줄지 activity 초안으로
    줄지 아직 미정이라(ADR 6절 참고), 지금은 형식 중립적인 최소 정보만
    담는다. 실제 전달 형식이 정해지면 이 스키마를 그 형식에 맞게 확장한다."""

    is_needed: bool
    suggested_date: date | None
    reason: str
    agenda: list[str] | None = None
