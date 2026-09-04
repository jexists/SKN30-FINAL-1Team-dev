import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from app.core.config import Settings
from app.services import llm
from app.services.agent_logging import agent_log_context


class _Result(BaseModel):
    value: int


@pytest.fixture
def configured_llm(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_api_url", "https://provider.invalid/v1/responses")
    monkeypatch.setattr(llm.settings, "llm_api_key", SecretStr("private-test-api-key"))
    monkeypatch.setattr(llm.settings, "llm_model", "test-model")
    monkeypatch.setattr(llm.settings, "llm_timeout_seconds", 180.0)


def _events(caplog):
    return [
        json.loads(record.message.removeprefix("agent_progress "))
        for record in caplog.records
        if record.message.startswith("agent_progress ")
    ]


def test_timeout_default_is_180_and_explicit_environment_is_respected(monkeypatch):
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    assert Settings(_env_file=None, app_env="test").llm_timeout_seconds == 180
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")
    assert Settings(_env_file=None, app_env="test").llm_timeout_seconds == 30


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (None, {}),
        ([], {}),
        ({}, {}),
        (
            {"input_tokens": 0, "output_tokens": 2, "total_tokens": 2},
            {"input_tokens": 0, "output_tokens": 2, "total_tokens": 2},
        ),
        ({"prompt_tokens": 7, "completion_tokens": 3}, {"input_tokens": 7, "output_tokens": 3}),
        (
            {"input_tokens": True, "output_tokens": -1, "total_tokens": "30", "private": "secret"},
            {},
        ),
        ({"input_tokens": 1.5, "output_tokens": 0}, {"output_tokens": 0}),
    ],
)
def test_usage_contains_only_reported_nonnegative_integer_counts(usage, expected):
    assert llm.safe_token_usage(usage) == expected


@pytest.mark.parametrize("error_type", [httpx.NetworkError, httpx.TimeoutException])
def test_httpx_base_transport_errors_remain_retryable(error_type):
    error = error_type("provider unavailable")
    code = llm.llm_boundary_error_code(error)

    assert code == f"llm_request_failed:{error_type.__name__}"
    assert llm.is_transient_llm_error(code) is True


@pytest.mark.anyio
@pytest.mark.parametrize("malformed", [False, True])
@pytest.mark.parametrize("response_kind", ["plain", "fenced"])
async def test_http_usage_is_recorded_even_when_output_schema_fails(
    configured_llm, monkeypatch, caplog, malformed, response_kind
):
    timeouts = []
    original_client = httpx.AsyncClient

    def response(request):
        timeouts.append(request.extensions["timeout"])
        text = json.dumps({"value": "private-provider-output" if malformed else 5})
        if response_kind != "plain":
            text = f" \n```json\n{text}\n```\n "
        payload = {
            "output_text": text,
            "usage": {
                "input_tokens": 13,
                "output_tokens": 7,
                "total_tokens": 20,
                "private_metadata": "private-token-data",
            },
        }
        return httpx.Response(
            200,
            headers={"x-request-id": "req_safe_test"},
            json=payload,
        )

    monkeypatch.setattr(
        llm.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(response), **kwargs),
    )
    with agent_log_context(call_count=2, call_limit=24):
        if malformed:
            with pytest.raises(llm.LLMError, match="^llm_output_schema_mismatch$"):
                await llm.generate_structured(
                    instructions="private-instructions",
                    input_text="private-transcript",
                    schema=_Result,
                    schema_name="safe_test",
                )
        else:
            result = await llm.generate_structured(
                instructions="private-instructions",
                input_text="private-transcript",
                schema=_Result,
                schema_name="safe_test",
            )
            assert result.value == 5

    assert timeouts == [{"connect": 10, "read": 180, "write": 180, "pool": 180}]
    completed = [event for event in _events(caplog) if event["stage"] == "llm.request_completed"]
    assert len(completed) == 1
    assert completed[0]["input_tokens"] == 13
    assert completed[0]["output_tokens"] == 7
    assert completed[0]["total_tokens"] == 20
    assert completed[0]["call_count"] == 2
    assert completed[0]["call_limit"] == 24
    assert completed[0]["request_id"] == "req_safe_test"
    assert completed[0]["elapsed_ms"] >= 0
    if malformed:
        errors = [
            json.loads(record.message.removeprefix("agent_error "))
            for record in caplog.records
            if record.message.startswith("agent_error ")
        ]
        assert any(event["stage"] == "llm.output_validation" for event in errors)
    assert "private-" not in caplog.text
    assert "provider.invalid" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [[], ["private-provider-output"], "private-provider-output", None, 42, False],
    ids=["empty-array", "array", "string", "null", "number", "boolean"],
)
async def test_non_object_response_uses_safe_llm_error(
    configured_llm, monkeypatch, caplog, payload
):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=json.dumps(payload),
            headers={"Content-Type": "application/json", "x-request-id": "req_safe_test"},
        )
    )
    monkeypatch.setattr(
        llm.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(llm.LLMError, match="^llm_response_not_object$"):
        await llm.generate_structured(
            instructions="private-instructions",
            input_text="private-transcript",
            schema=_Result,
            schema_name="safe_test",
        )

    errors = [
        json.loads(record.message.removeprefix("agent_error "))
        for record in caplog.records
        if record.message.startswith("agent_error ")
    ]
    assert len(errors) == 1
    assert errors[0]["stage"] == "llm.output_text"
    assert errors[0]["exceptions"][0]["type"] == "LLMError"
    assert errors[0]["request_id"] == "req_safe_test"
    assert "private-" not in caplog.text
    assert "provider.invalid" not in caplog.text


@pytest.mark.anyio
async def test_cancellation_keeps_safe_timing_without_fake_usage(
    configured_llm, monkeypatch, caplog
):
    original_client = httpx.AsyncClient

    async def cancel(request):
        raise asyncio.CancelledError("private-cancel-message")

    monkeypatch.setattr(
        llm.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(cancel), **kwargs),
    )
    with pytest.raises(asyncio.CancelledError):
        await llm.generate_structured(
            instructions="private-instructions",
            input_text="private-transcript",
            schema=_Result,
            schema_name="safe_test",
        )

    events = _events(caplog)
    assert [event["stage"] for event in events] == ["llm.request_started", "llm.request_cancelled"]
    assert events[-1]["elapsed_ms"] >= 0
    assert not any("total_tokens" in event for event in events)
    assert "private-" not in caplog.text
