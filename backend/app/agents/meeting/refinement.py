"""동결 CRM 조회 도구와 미해결 근거의 재귀속."""

import asyncio
import copy
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models import BaseChatModel

from app.agents.meeting.transcript import MeetingContentAgentInput, basic_crm
from app.schemas.meeting_content import (
    MeetingContentAnalysisOutput,
    MeetingEvidenceLedger,
    build_evidence_ledger,
)
from app.services.agent_logging import log_agent_error
from app.services.llm import LLMError


async def run(
    agent_input: MeetingContentAgentInput,
    ledger: MeetingEvidenceLedger,
    model: BaseChatModel,
    budget: AsyncCallbackHandler,
    on_lookup: Callable[[dict[str, Any]], None] | None,
    *,
    model_call_limit: int,
    lookup_limit: int,
    system_prompt: str,
) -> MeetingEvidenceLedger:
    unresolved = {
        item.segment.segment_id for item in ledger.items if item.applicability.scope == "unresolved"
    }
    lookups = 0
    received_context = False
    cached: dict[tuple[str, UUID | None], dict[str, Any]] = {}
    lookup_lock = asyncio.Lock()

    crm = agent_input.crm_context
    refinement = crm.get("refinement_context")
    refinement = refinement if isinstance(refinement, dict) else {}

    def company_trade_history() -> dict[str, Any]:
        if "company_trade_history" in refinement:
            value = refinement["company_trade_history"]
            return (
                copy.deepcopy(value)
                if isinstance(value, dict)
                else {"error": "context_not_available"}
            )
        if "trade_history" not in crm or not isinstance(crm["trade_history"], list):
            return {"error": "context_not_available"}
        history = crm["trade_history"]
        metadata = crm.get("trade_history_metadata")
        return {
            "kind": "trade_history",
            "items": copy.deepcopy(history),
            **(copy.deepcopy(metadata) if isinstance(metadata, dict) else {}),
        }

    def deal_context(kind: str, sales_deal_id: UUID) -> dict[str, Any]:
        if kind == "previous_reports":
            if "previous_reports" not in crm:
                return {"error": "context_not_available"}
            values = crm["previous_reports"]
        else:
            if "product_details" not in refinement:
                return {"error": "context_not_available"}
            values = refinement["product_details"]
        if not isinstance(values, list):
            return {"error": "context_not_available"}
        for value in values:
            if isinstance(value, dict) and str(value.get("sales_deal_id")) == str(sales_deal_id):
                return copy.deepcopy(value)
        return {"kind": kind, "sales_deal_id": str(sales_deal_id), "items": []}

    async def read(
        kind: str,
        sales_deal_id: UUID | None,
        value: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        nonlocal lookups, received_context
        if sales_deal_id is not None and sales_deal_id not in ledger.selected_deal_ids:
            return {"error": "deal_not_selected"}
        # 병렬로 요청한 같은 frozen snapshot 조각도 한 번만 읽고 기록한다.
        async with lookup_lock:
            key = (kind, sales_deal_id)
            if key in cached:
                return {**cached[key], "no_new_information": True}
            if lookups >= lookup_limit:
                return {"error": "meeting_content_lookup_limit"}
            lookups += 1
            try:
                result = value()
            except Exception as error:
                log_agent_error(
                    error,
                    stage="meeting_content.crm_lookup",
                    error_code="crm_lookup_failed",
                    sales_deal_id=str(sales_deal_id) if sales_deal_id is not None else None,
                    lookup_kind=kind,
                )
                return {"error": "crm_lookup_failed"}
            if not isinstance(result, dict) or (
                not result.get("error") and not isinstance(result.get("items"), list)
            ):
                result = {"error": "context_not_available"}
            has_information = bool(
                isinstance(result.get("items"), list)
                and result["items"]
                and not result.get("error")
            )
            response = {
                "kind": kind,
                "data": result,
            }
            if sales_deal_id is not None:
                response["sales_deal_id"] = str(sales_deal_id)
            if result.get("error") == "context_not_available":
                response["no_new_information"] = True
                cached[key] = response
                return response
            if not result.get("error"):
                response["no_new_information"] = not has_information
                if on_lookup is not None:
                    try:
                        on_lookup(
                            {
                                "kind": kind,
                                **(
                                    {"sales_deal_id": str(sales_deal_id)}
                                    if sales_deal_id is not None
                                    else {}
                                ),
                                "data": copy.deepcopy(result),
                            }
                        )
                    except Exception as error:
                        log_agent_error(
                            error,
                            stage="meeting_content.crm_lookup",
                            error_code="crm_lookup_failed",
                            lookup_kind=kind,
                        )
                        return {"error": "crm_lookup_failed"}
                received_context |= has_information
                cached[key] = response
            return response

    async def read_company_trade_history() -> dict[str, Any]:
        """모호한 구간이 과거 거래를 가리킬 때만 고객사 거래 이력을 읽는다.

        특정 딜의 현재 발언이나 신규 고객 여부를 판단할 때는 사용하지 않는다. 결과의
        ``items=[]``는 조회 범위에 기록이 없다는 뜻이고, ``context_not_available``은 이
        실행의 고정 스냅샷에 해당 자료가 없다는 뜻이다. 둘 다 같은 조회를 반복하지 않는다.
        """
        return await read("trade_history", None, company_trade_history)

    async def read_previous_deal_reports(sales_deal_id: UUID) -> dict[str, Any]:
        """선택 딜의 과거 확정 보고서를 읽어 '지난번 제안' 같은 표현을 확인한다.

        Args:
            sales_deal_id: 이번 미팅에서 선택된 딜 ID. 다른 딜 ID는 거부된다.

        현재 미팅의 새 사실을 채우거나 다른 딜의 내용을 옮길 때는 사용하지 않는다.
        ``items=[]``는 과거 확정본이 없다는 뜻이며, ``context_not_available``은 고정
        스냅샷에 자료가 없다는 뜻이다. 어느 경우에도 추측하지 말고 unresolved를 유지한다.
        """
        return await read(
            "previous_reports",
            sales_deal_id,
            lambda: deal_context("previous_reports", sales_deal_id),
        )

    async def read_deal_product_details(sales_deal_id: UUID) -> dict[str, Any]:
        """선택 딜의 제품명·사양이 원문 약칭의 대상을 가를 때만 제품 상세를 읽는다.

        Args:
            sales_deal_id: 이번 미팅에서 선택된 딜 ID. 다른 딜 ID는 거부된다.

        제품이 비슷하다는 이유만으로 귀속할 때는 사용하지 않는다. ``items=[]`` 또는
        ``context_not_available``이면 새 근거가 없으므로 unresolved를 유지하고 반복 조회하지
        않는다. 도구 오류가 ``crm_lookup_failed``일 때만 한도 안에서 재시도할 수 있다.
        """
        return await read(
            "product_details",
            sales_deal_id,
            lambda: deal_context("product_details", sales_deal_id),
        )

    payload = {
        "selected_deals": [deal.model_dump(mode="json") for deal in agent_input.deals],
        "crm_context": basic_crm(agent_input),
        "unresolved_segments": [
            item.segment.model_dump(mode="json")
            for item in ledger.items
            if item.segment.segment_id in unresolved
        ],
        "resolved_context": [
            item.model_dump(mode="json")
            for item in ledger.items
            if item.segment.segment_id not in unresolved
        ],
    }
    agent = create_agent(
        model,
        system_prompt=system_prompt,
        tools=[
            read_company_trade_history,
            read_previous_deal_reports,
            read_deal_product_details,
        ],
        response_format=ToolStrategy(MeetingContentAnalysisOutput),
    )
    state = await agent.ainvoke(
        {"messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]},
        config={"callbacks": [budget], "recursion_limit": model_call_limit * 3},
    )
    refined: MeetingContentAnalysisOutput = state["structured_response"]
    updates = {item.segment_id: item.applicability for item in refined.assignments}
    if set(updates) != unresolved:
        raise LLMError("meeting_content_refinement_segments_mismatch")
    if any(not set(item.deal_ids) <= set(ledger.selected_deal_ids) for item in updates.values()):
        raise LLMError("meeting_content_refinement_deal_not_selected")
    if not received_context:
        return ledger
    analysis = MeetingContentAnalysisOutput(
        assignments=[
            {
                "segment_id": item.segment.segment_id,
                "applicability": updates.get(item.segment.segment_id, item.applicability),
            }
            for item in ledger.items
        ]
    )
    return build_evidence_ledger(agent_input.source, analysis)
