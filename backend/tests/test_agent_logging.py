"""실제 요청 없이 에이전트 로그의 실행 문맥 분리와 민감정보 경계를 검사한다."""

import asyncio
import json
import logging
import re

import httpx
import openai
from pydantic import ValidationError

from app.services.agent_logging import agent_log_context, log_agent_error


def _events(caplog):
    events = []
    for record in caplog.records:
        if record.name != "app.services.agent_logging":
            continue
        message = record.getMessage()
        assert record.levelno == logging.ERROR
        assert message.startswith("agent_error ") and "\n" not in message
        assert record.exc_info is None and record.stack_info is None
        event = json.loads(message.removeprefix("agent_error "))
        assert event["event"] == "agent_error"
        events.append(event)
    return events


def test_context_isolated_across_async_tasks_threads_and_restored_after_error(caplog):
    caplog.set_level(logging.ERROR, logger="app.services.agent_logging")

    async def worker(run_id):
        with agent_log_context(run_id=run_id, agent_code="meeting_processing"):
            await asyncio.sleep(0)
            log_agent_error(RuntimeError("private"), stage=f"{run_id}.async")
            await asyncio.to_thread(
                log_agent_error, RuntimeError("private"), stage=f"{run_id}.thread"
            )
            try:
                with agent_log_context(run_id=f"nested-{run_id}"):
                    log_agent_error(RuntimeError("private"), stage=f"{run_id}.nested")
                    raise LookupError("private")
            except LookupError:
                pass
            log_agent_error(RuntimeError("private"), stage=f"{run_id}.restored")

    async def execute():
        with agent_log_context(run_id="parent", model="mock-model"):
            await asyncio.gather(worker("run-a"), worker("run-b"))
            log_agent_error(RuntimeError("private"), stage="parent")
        log_agent_error(RuntimeError("private"), stage="outside")

    asyncio.run(execute())
    events = {event["stage"]: event for event in _events(caplog)}
    assert len(events) == 10
    for run_id in ("run-a", "run-b"):
        for stage in ("async", "thread", "restored"):
            event = events[f"{run_id}.{stage}"]
            assert event["run_id"] == run_id and event["agent_code"] == "meeting_processing"
            assert event["model"] == "mock-model"
        assert events[f"{run_id}.nested"]["run_id"] == f"nested-{run_id}"
    assert events["parent"]["run_id"] == "parent"
    assert "agent_code" not in events["parent"]
    assert not {"run_id", "agent_code", "model"} & events["outside"].keys()


def test_http_429_keeps_request_id_without_keys_request_or_response_body(caplog):
    caplog.set_level(logging.ERROR, logger="app.services.agent_logging")
    request = httpx.Request(
        "POST",
        "https://example.test/PRIVATE_URL?api_key=PRIVATE_QUERY_KEY",
        headers={"Authorization": "Bearer PRIVATE_AUTH_KEY"},
        content=b"PRIVATE_REQUEST_BODY",
    )
    response = httpx.Response(
        429,
        request=request,
        headers={"x-request-id": "req_test_429", "set-cookie": "PRIVATE_COOKIE"},
        json={"error": {"message": "PRIVATE_RESPONSE_BODY"}},
    )
    try:
        raise openai.RateLimitError(
            "PRIVATE_EXCEPTION_MESSAGE", response=response, body=response.json()
        )
    except openai.RateLimitError as error:
        log_agent_error(error, stage="report_write", error_code="report_agent_failed")

    events = _events(caplog)
    assert len(events) == 1 and events[0]["error_code"] == "report_agent_failed"
    details = events[0]["exceptions"]
    assert any(item["type"].endswith("RateLimitError") for item in details)
    assert any(item.get("status_code") == 429 for item in details)
    assert any(item.get("request_id") == "req_test_429" for item in details)
    frames = [frame for item in details for frame in item["frames"]]
    assert frames and all(re.fullmatch(r"[^/\\]+:\d+:[^\r\n]+", frame) for frame in frames)
    assert "PRIVATE_" not in caplog.text


def test_source_and_cause_chain_keeps_validation_types_not_values_locations_or_messages(caplog):
    caplog.set_level(logging.ERROR, logger="app.services.agent_logging")
    validation = ValidationError.from_exception_data(
        "PRIVATE_SCHEMA",
        [
            {
                "type": "value_error",
                "loc": ("PRIVATE_LOCATION\nforged_log",),
                "input": {"prompt": "PRIVATE_RAW_INPUT", "token": "PRIVATE_TOKEN"},
                "ctx": {"error": ValueError("PRIVATE_VALIDATOR_MESSAGE")},
            }
        ],
    )
    wrapper = RuntimeError("PRIVATE_WRAPPER_MESSAGE")
    try:
        raise validation
    except ValidationError as error:
        wrapper.source = error
    try:
        raise wrapper from OSError("PRIVATE_CAUSE_MESSAGE")
    except RuntimeError as error:
        log_agent_error(error, stage="feature_extract", error_code="deal_feature_failed")

    events = _events(caplog)
    assert len(events) == 1 and events[0]["stage"] == "feature_extract"
    details = events[0]["exceptions"]
    kinds = {item["type"].rsplit(".", 1)[-1] for item in details}
    assert {"RuntimeError", "OSError", "ValidationError"} <= kinds
    validation_details = [item for item in details if item["type"].endswith("ValidationError")]
    assert len(validation_details) == 1
    assert validation_details[0]["validation_error_types"] == ["value_error"]
    assert validation_details[0]["frames"]
    assert "PRIVATE_" not in caplog.text and "forged_log" not in caplog.text


def test_progress_records_actual_counts_timing_tokens_not_source(caplog):
    from app.services.agent_logging import log_agent_event

    caplog.set_level(logging.INFO, logger="app.services.agent_logging")
    with agent_log_context(run_id="test-run"):
        log_agent_event(
            "report_writing.model_call",
            outcome="completed",
            call_count=4,
            call_limit=100,
            review_attempt=2,
            review_limit=10,
            elapsed_ms=45_200,
            timeout_seconds=180,
            input_tokens=120,
            output_tokens=75,
            total_tokens=195,
            transcript="PRIVATE_TRANSCRIPT",
            issues=["PRIVATE_REVIEW"],
        )
    event = json.loads(caplog.records[-1].getMessage().removeprefix("agent_progress "))
    assert event["run_id"] == "test-run" and event["call_count"] == 4
    assert event["elapsed_ms"] == 45_200 and event["total_tokens"] == 195
    assert event["review_attempt"] == 2 and event["review_limit"] == 10
    assert "PRIVATE_" not in caplog.text
