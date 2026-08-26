from app.core.config import Settings
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
