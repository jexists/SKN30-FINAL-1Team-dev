"""미팅·기간 보고서가 공유하는 Deep Agents 실행 하네스."""

import json
from time import perf_counter
from typing import Any
from uuid import UUID

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.filesystem import FilesystemPermission
from langchain.agents.middleware import ModelCallLimitMiddleware, after_model
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import AsyncCallbackHandler
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.services.agent_logging import log_agent_error, log_agent_event
from app.services.llm import LLMError

RUN_TIMEOUT_SECONDS = 900
# Deep Agents가 자동 추가하는 작성자를 대체하여 불필요한 두 번째 하위 에이전트를 막는다.
DELEGATED_WRITER_NAME = "general-purpose"


class ReportReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[str] = Field(max_length=30)


class ReportRunBudget(AsyncCallbackHandler):
    """작성자·검토자·감독자의 모델 및 로컬 도구 호출을 실행별로 세는다."""

    # ponytail: ainvoke 전용. 동기 invoke를 추가할 때 콜백 예외 전파를 검증한다.
    raise_error = True

    def __init__(self, *, model_call_limit: int):
        self.model_calls = 0
        self.tool_calls = 0
        self.model_call_limit = model_call_limit
        self._timeout_seconds = max(180.0, settings.llm_timeout_seconds)
        self._started: dict[UUID, tuple[int, float]] = {}

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        if self.model_calls >= self.model_call_limit:
            log_agent_event(
                "report_writing.model",
                outcome="limit_reached",
                model_call_count=self.model_calls,
                call_count=self.model_calls,
                call_limit=self.model_call_limit,
                reason_code="report_agent_model_call_limit",
            )
            raise LLMError("report_agent_model_call_limit")
        self.model_calls += 1
        self._started[run_id] = (self.model_calls, perf_counter())
        log_agent_event(
            "report_writing.model",
            outcome="started",
            model_call_id=str(run_id),
            model_call_count=self.model_calls,
            call_count=self.model_calls,
            call_limit=self.model_call_limit,
            timeout_seconds=self._timeout_seconds,
        )

    def _finish(self, run_id, *, response=None, error=None):
        started = self._started.pop(run_id, None)
        if started is None:
            return
        tokens: dict[str, int] = {}
        if response is not None:
            for generations in response.generations:
                for generation in generations:
                    usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                    if isinstance(usage, dict):
                        for key in ("input_tokens", "output_tokens", "total_tokens"):
                            value = usage.get(key)
                            if type(value) is int and value >= 0:
                                tokens[key] = tokens.get(key, 0) + value
        fields = {
            "model_call_id": str(run_id),
            "model_call_count": started[0],
            "call_count": started[0],
            "call_limit": self.model_call_limit,
            "timeout_seconds": self._timeout_seconds,
            "elapsed_ms": round((perf_counter() - started[1]) * 1000),
            **tokens,
        }
        log_agent_event(
            "report_writing.model",
            outcome="failed" if error is not None else "completed",
            **fields,
        )
        if error is not None:
            log_agent_error(error, stage="report_writing.model", **fields)

    async def on_llm_end(self, response, *, run_id, **kwargs):
        self._finish(run_id, response=response)

    async def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, error=error)

    async def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        # 도구명·인수·결과는 로그에 남기지 않는다.
        self.tool_calls += 1


def successful_task_descriptions(messages: list[Any]) -> list[str]:
    """서버가 주입한 작성자 task 중 실제 완료된 description만 반환한다."""
    task_descriptions = {
        tool_call["id"]: tool_call["args"].get("description")
        for message in messages
        if getattr(message, "type", None) == "ai"
        for tool_call in getattr(message, "tool_calls", ())
        if tool_call.get("name") == "task"
        and isinstance(tool_call.get("args"), dict)
        and tool_call["args"].get("subagent_type") == DELEGATED_WRITER_NAME
        and isinstance(tool_call["args"].get("description"), str)
    }
    return [
        task_descriptions[message.tool_call_id]
        for message in messages
        if getattr(message, "type", None) == "tool"
        and getattr(message, "name", None) == "task"
        and getattr(message, "status", None) == "success"
        and getattr(message, "tool_call_id", None) in task_descriptions
    ]


def review_final_response(schema, review, accepted_response):
    """구조화 출력도 동일한 advisory 검토 흐름으로 보낸다."""

    @after_model
    async def review_final_report(state, runtime):
        value = state.get("structured_response")
        if value is None:
            return None
        draft = schema.model_validate(value)
        feedback = await review(draft, state["messages"])
        if not feedback["issues"]:
            accepted = accepted_response()
            if accepted is None:
                raise LLMError("report_agent_unreviewed_output")
            return {"structured_response": accepted}
        receipt = next(
            message
            for message in reversed(state["messages"])
            if message.type == "tool" and message.name == schema.__name__
        )
        return {
            "structured_response": None,
            "messages": [
                receipt.model_copy(
                    update={
                        "name": None,
                        "content": "검토 의견을 반영할 부분만 작성자에게 한 번 다시 "
                        "위임하고, 수정본은 렌더링 계약을 확인한 뒤 제출하라.\n"
                        + json.dumps(feedback, ensure_ascii=False),
                    }
                )
            ],
        }

    return review_final_report


def create_report_supervisor(
    *,
    model,
    system_prompt: str,
    review_tool,
    subagent: dict[str, Any],
    finish_middleware,
    review_callback,
    accepted_response,
    response_schema,
    supervisor_model_call_limit: int,
    tool_message_content: str,
    name: str,
):
    """공통 감독자 하네스에 서버가 확정한 작성 역할 하나만 장착한다."""
    return create_deep_agent(
        model,
        system_prompt=system_prompt,
        tools=[review_tool],
        backend=StateBackend(),
        permissions=[
            FilesystemPermission(operations=["write"], paths=["/scratch/**"], mode="allow"),
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
        ],
        subagents=[{**subagent, "name": DELEGATED_WRITER_NAME}],
        middleware=[
            finish_middleware,
            review_final_response(response_schema, review_callback, accepted_response),
            ModelCallLimitMiddleware(
                run_limit=supervisor_model_call_limit,
                exit_behavior="error",
            ),
        ],
        response_format=ToolStrategy(
            response_schema,
            tool_message_content=tool_message_content,
        ),
        name=name,
    )
