"""Contract-only tool loop. The injected runtime owns authorization and durability."""

import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langsmith import tracing_context

from app.agents.contract_management import (
    PROPOSE_NEXT_MEETING_SYSTEM_PROMPT,
    NextMeetingProposalOutput,
    _NextMeetingLLMInput,
    _now,
)
from app.core.config import settings
from app.schemas.schedule_delegation import ScheduleRequest
from app.services.agent_logging import log_agent_event
from app.services.contract_tracing import span
from app.services.llm import LLMError, configured_chat_model, llm_boundary_error_code

INSTRUCTIONS = """
이 실행에서는 JSON 본문 대신 도구를 사용한다.
미팅이 불필요하거나 정보가 부족하면 finish_proposal로 종료한다.
미팅이 필요하면 request_schedule_candidates로 일정관리 에이전트에 위임한다.
도구가 candidates_found를 반환하면 해당 실행 ID로 finish_proposal을 호출한다.
no_candidates일 때만, 확인된 조건 안에서 다른 기간으로 한 번 재검색할 수 있다.
재검색 reason에는 첫 결과와 기간 변경 근거를 짧게 명시한다.
확정된 일정 제약은 server_schedule_constraints에만 있다. 계약 만료일을 미팅 마감으로
단정하지 않는다. 기간 확대 허용 제약이 없으면 최초 기간 밖으로 확대하지 않는다.
미팅 길이를 줄이거나 같은 조건을 반복하지 않는다. failed는 후보 없음과 다르다.
서버 오류 이후 다른 조건으로 재검색하지 않는다. 입력 오류만 수정할 수 있다.
최대 일정 탐색 2회, 도구 요청 4회, 모델 호출 5회다. 마지막 호출은 종료에 사용한다.
최종 next_meeting_suggestion은 실제 적용 조건과 대상 딜을 그대로 사용한다.
후보 시각을 만들어내지 않는다. 일정은 사용자의 승인 전에는 등록되지 않는다.
"""


async def run(snapshot: dict, runtime) -> NextMeetingProposalOutput:
    data = _NextMeetingLLMInput(
        customer_company=snapshot.get("customer_company"),
        sales_deals=snapshot.get("sales_deals") or [],
        risk_signals=snapshot.get("risk_signals") or [],
        recent_approved_reports=snapshot.get("recent_approved_reports") or [],
        current_date=_now().isoformat(),
    ).model_dump()
    state = await runtime.restore()
    data["server_schedule_constraints"] = state.get("constraints", {})
    search = {
        "type": "function",
        "function": {
            "name": "request_schedule_candidates",
            "description": "검증된 기간에서 일정 후보 탐색",
            "parameters": ScheduleRequest.model_json_schema(),
        },
    }
    finish = {
        "type": "function",
        "function": {
            "name": "finish_proposal",
            "description": "검색 결과 또는 미팅 불필요 사유로 종료",
            "parameters": NextMeetingProposalOutput.model_json_schema(),
        },
    }
    model = configured_chat_model().bind_tools([search, finish], parallel_tool_calls=False)
    while True:
        state = await runtime.restore()
        if state.get("final") is not None:
            return NextMeetingProposalOutput.model_validate(state["final"])
        pending = state.get("pending")
        if pending:
            for index, call in enumerate(pending):
                call_key = f"{state['model_calls']}:{index}"
                if call["name"] == "finish_proposal":
                    try:
                        output = NextMeetingProposalOutput.model_validate(call["args"])
                        return await runtime.finish(output)
                    except (ValueError, TypeError):
                        result = {"status": "failed", "reason_code": "invalid_final_result"}
                elif call["name"] == "request_schedule_candidates":
                    result = await runtime.request(call_key, call["args"])
                else:
                    result = await runtime.reject(call_key, "unknown_tool")
                await runtime.record_result(call["id"], result)
            await runtime.clear_pending()
            continue

        count = await runtime.reserve_model()
        messages = [
            SystemMessage(content=PROPOSE_NEXT_MEETING_SYSTEM_PROMPT + INSTRUCTIONS),
            HumanMessage(content=json.dumps(data, ensure_ascii=False)),
        ]
        for item in state.get("history", []):
            if item["role"] == "assistant":
                messages.append(AIMessage(content="", tool_calls=item["tool_calls"]))
            else:
                messages.append(
                    ToolMessage(
                        content=json.dumps(item["result"], ensure_ascii=False),
                        tool_call_id=item["id"],
                    )
                )
        messages.append(
            HumanMessage(content=f"현재 모델 호출 {count}/5. 한 번에 도구 하나만 호출.")
        )
        # Global LANGSMITH_TRACING must not capture CRM prompts through automatic callbacks.
        async with span("contract.decision", model_call_count=count) as trace:
            with tracing_context(enabled=False):
                try:
                    async with asyncio.timeout(settings.llm_timeout_seconds):
                        response = await model.ainvoke(messages)
                except TimeoutError:
                    raise LLMError("llm_timeout") from None
                except Exception as error:
                    raise LLMError(
                        llm_boundary_error_code(error) or "contract_model_failed"
                    ) from None
            usage = response.usage_metadata or {}
            trace.update(
                {
                    k: usage[k]
                    for k in ("input_tokens", "output_tokens", "total_tokens")
                    if k in usage
                }
            )
            log_agent_event(
                "contract.decision",
                model_call_count=count,
                **{
                    k: usage[k]
                    for k in ("input_tokens", "output_tokens", "total_tokens")
                    if k in usage
                },
            )
            calls = response.tool_calls
            trace["action"] = (
                "search" if len(calls) == 1 and calls[0]["name"] == "request_schedule_candidates"
                else "finish" if len(calls) == 1 and calls[0]["name"] == "finish_proposal"
                else "invalid_tool_response"
            )
            if not calls or len(calls) != 1:
                # Consumes the durable model budget; no parallel side effects are dispatched.
                await runtime.record_invalid_turn()
                continue
            await runtime.record_calls(calls)
