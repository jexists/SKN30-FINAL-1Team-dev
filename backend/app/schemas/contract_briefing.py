from datetime import date
from typing import Literal

from pydantic import BaseModel

RiskKind = Literal["expiry", "delivery", "stale_contact"]
RiskSeverity = Literal["low", "medium", "high"]


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
