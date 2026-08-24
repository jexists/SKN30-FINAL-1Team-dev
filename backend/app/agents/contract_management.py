"""영업·계약 데이터를 근거로 위험과 다음 행동을 제안하는 Agent."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.llm import generate_structured

PROMPT_VERSION = "contract_management.v2"
SYSTEM_PROMPT = (
    "너는 B2B 영업·계약관리 보조 AI다. 제공된 스냅샷만 근거로 계약 현황, 위험, "
    "누락 정보와 다음 행동을 제안하라. 확인되지 않은 사실은 만들지 말고 누락 정보로 표시하라. "
    "계약이나 업무 데이터를 직접 변경한다고 표현하지 말라. "
    "각 위험에는 제공된 원천 ID를 근거로 남겨라. "
    "risks의 code와 severity는 입력의 risk_signals에 있는 값만 그대로 사용하라. "
    "risk_signals에 없는 위험은 만들지 말고, 근거가 있는 risk_signals 항목은 빠뜨리지 말라."
)

RiskCode = Literal[
    "contract_expiring",
    "quote_expiring",
    "delivery_delay_risk",
    "unresolved_support",
    "follow_up_overdue",
    "missing_contract_information",
]


class SourceRef(BaseModel):
    """Agent가 제시한 판단이 어떤 원천 데이터에 근거하는지 식별한다.

    위험 설명에 원문 전체를 복제하는 대신 원천 종류와 ID만 남겨, 결과를 검토하거나
    감사할 때 실제 DB 행을 다시 찾을 수 있게 한다.
    """

    model_config = ConfigDict(extra="forbid")
    type: Literal["sales_deal", "report", "support_request", "activity"]
    id: str = Field(min_length=1, max_length=128)


class ContractRisk(BaseModel):
    """계약관리 Agent가 발견한 위험 한 건의 구조를 정의한다.

    코드와 심각도는 후속 화면 표시 및 업무 분기에 사용하고, 사람에게 보여줄 설명과
    판단 근거가 된 원천 데이터 목록을 함께 보관한다.
    """

    model_config = ConfigDict(extra="forbid")
    code: RiskCode
    severity: Literal["low", "medium", "high"]
    message: str = Field(min_length=1, max_length=1_000)
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=20)


class NextMeetingSuggestion(BaseModel):
    """계약 위험이나 후속 조치에 따라 필요한 다음 미팅의 조건을 제안한다.

    이 값은 실제 일정을 생성하지 않으며, 일정관리 Agent가 후보 시간을 계산할 때 사용할
    대상 딜, 사유, 선호 기간 및 예상 소요 시간만 전달한다.
    """

    model_config = ConfigDict(extra="forbid")
    sales_deal_id: str
    reason: str = Field(min_length=1, max_length=1_000)
    preferred_starts_at: str | None = None
    preferred_ends_at: str | None = None
    duration_minutes: int = Field(default=60, ge=5, le=480)


class ContractManagementOutput(BaseModel):
    """LLM이 반환해야 하는 계약관리 Agent의 최종 구조화 출력이다.

    계약 현황 요약, 위험, 누락 정보, 권장 행동과 선택적인 다음 미팅 제안을 하나의
    검증 가능한 결과로 묶어 `agent_run.output_snapshot`에 저장할 수 있게 한다.
    """

    model_config = ConfigDict(extra="forbid")
    contract_summary: str = Field(max_length=3_000)
    risks: list[ContractRisk] = Field(default_factory=list, max_length=50)
    missing_information: list[str] = Field(default_factory=list, max_length=50)
    recommended_actions: list[str] = Field(default_factory=list, max_length=50)
    next_meeting_suggestion: NextMeetingSuggestion | None = None


async def run(snapshot: dict[str, Any]) -> ContractManagementOutput:
    """실행 시점의 입력 스냅샷으로 LLM을 호출하고 검증된 계약관리 결과를 반환한다.

    DB 조회나 업무 데이터 수정은 이 함수가 담당하지 않는다. 호출 서비스가 권한 검증 후
    만든 스냅샷을 전달하며, 공통 LLM 경계가 JSON Schema에 맞지 않는 응답을 거절한다.
    """

    return await generate_structured(
        instructions=SYSTEM_PROMPT,
        input_text=json.dumps(snapshot, ensure_ascii=False, default=str),
        schema=ContractManagementOutput,
        schema_name="contract_management",
    )
