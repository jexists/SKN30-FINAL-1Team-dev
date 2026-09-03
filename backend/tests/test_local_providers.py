import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.config import settings as runtime_settings
from app.schemas.business_cards import BusinessCardFields
from app.services import llm
from app.services.ocr import _paddle_lines


def test_local_provider_settings_are_configured_without_cloud_keys():
    settings = Settings(
        app_env="test",
        llm_provider="ollama",
        llm_api_url="http://localhost:11434/api/chat",
        llm_model="local-model",
        embedding_provider="local",
        embedding_local_model="local-embedding",
        ocr_provider="local",
    )

    assert settings.llm_configured is True
    assert settings.embedding_configured is True
    assert settings.ocr_configured is True


def test_openai_api_key_is_llm_fallback():
    settings = Settings(
        app_env="test",
        llm_provider="external",
        llm_api_url="https://api.openai.com/v1/responses",
        llm_api_key="",
        openai_api_key="openai-test-key",
        llm_model="gpt-test",
    )

    assert settings.llm_configured is True
    assert settings.effective_llm_api_key == "openai-test-key"


def test_configured_chat_model_uses_openai_api_key_fallback(monkeypatch):
    monkeypatch.setattr(runtime_settings, "llm_provider", "external")
    monkeypatch.setattr(runtime_settings, "llm_api_url", "https://provider.invalid/v1/responses")
    monkeypatch.setattr(runtime_settings, "llm_api_key", SecretStr(""))
    monkeypatch.setattr(runtime_settings, "openai_api_key", SecretStr("fallback-test-key"))
    monkeypatch.setattr(runtime_settings, "llm_model", "test-model")

    model = llm.configured_chat_model()

    assert model.openai_api_key.get_secret_value() == "fallback-test-key"


@pytest.mark.parametrize(
    ("llm_api_key", "openai_api_key"),
    [("", ""), ("must-not-be-forwarded", "also-must-not-be-forwarded")],
)
@pytest.mark.parametrize("scheme", ["http", "https"])
def test_configured_chat_model_uses_non_secret_key_for_loopback_ollama(
    monkeypatch, llm_api_key, openai_api_key, scheme
):
    monkeypatch.setattr(runtime_settings, "llm_provider", "ollama")
    monkeypatch.setattr(runtime_settings, "llm_api_url", f"{scheme}://localhost:11434/api/chat")
    monkeypatch.setattr(runtime_settings, "llm_api_key", SecretStr(llm_api_key))
    monkeypatch.setattr(runtime_settings, "openai_api_key", SecretStr(openai_api_key))
    monkeypatch.setattr(runtime_settings, "llm_model", "local-model")

    model = llm.configured_chat_model()

    assert model.openai_api_base == f"{scheme}://localhost:11434/v1"
    assert model.openai_api_key.get_secret_value() == "ollama"
    assert model.use_responses_api is False


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_configured_chat_model_rejects_non_loopback_ollama(monkeypatch, scheme):
    monkeypatch.setattr(runtime_settings, "llm_provider", "ollama")
    monkeypatch.setattr(
        runtime_settings, "llm_api_url", f"{scheme}://ollama.internal:11434/api/chat"
    )
    monkeypatch.setattr(runtime_settings, "llm_model", "local-model")

    with pytest.raises(llm.LLMError, match="^report_agent_unsupported_endpoint$"):
        llm.configured_chat_model()


def test_paddle_v3_result_is_normalized_to_ocr_lines():
    result = _paddle_lines(
        [
            {
                "rec_texts": ["홍길동", "sales@example.com"],
                "rec_scores": [0.98, 0.97],
            }
        ]
    )

    assert result == [
        {"content": "홍길동", "confidence": 0.98},
        {"content": "sales@example.com", "confidence": 0.97},
    ]


def test_paddle_v2_result_is_normalized_to_ocr_lines():
    result = _paddle_lines(
        [
            [
                [[[0, 0], [10, 0], [10, 10], [0, 10]], ["영업팀", 0.96]],
            ]
        ]
    )

    assert result == [{"content": "영업팀", "confidence": 0.96}]


@pytest.mark.anyio
async def test_ollama_generate_structured_reads_chat_message_content(monkeypatch):
    class _Response:
        status_code = 200

        def json(self):
            return {"message": {"role": "assistant", "content": '{"name":"홍길동"}'}}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **_kwargs: _Client())
    monkeypatch.setattr(runtime_settings, "llm_provider", "ollama")
    monkeypatch.setattr(runtime_settings, "llm_api_url", "http://localhost:11434/api/chat")
    monkeypatch.setattr(runtime_settings, "llm_model", "local-model")

    result = await llm.generate_structured(
        instructions="JSON만 출력",
        input_text="명함",
        schema=BusinessCardFields,
        schema_name="business_card_fields",
    )

    assert result.name == "홍길동"


@pytest.mark.anyio
async def test_external_generate_structured_rejects_http_endpoint(monkeypatch):
    monkeypatch.setattr(runtime_settings, "llm_provider", "external")
    monkeypatch.setattr(runtime_settings, "llm_api_url", "http://provider.invalid/v1/responses")
    monkeypatch.setattr(runtime_settings, "llm_api_key", SecretStr("private-test-key"))
    monkeypatch.setattr(runtime_settings, "llm_model", "test-model")

    with pytest.raises(llm.LLMError, match="^report_agent_unsupported_endpoint$"):
        await llm.generate_structured(
            instructions="JSON만 출력",
            input_text="명함",
            schema=BusinessCardFields,
            schema_name="business_card_fields",
        )
