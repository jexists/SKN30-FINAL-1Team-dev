from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.deps import get_current_member
from app.core.config import settings
from app.main import app
from app.models.workspace import Member
from app.services import stt

ORIGIN = settings.cors_origin_list[0]
WAV = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVE"


class _Response:
    status_code = 200

    def json(self):
        return {"text": "고객과 다음 주 계약 일정을 논의했습니다."}


class _OpenAIStub:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


@pytest.fixture(autouse=True)
def transcription_environment(monkeypatch):
    member = Member(
        id=uuid4(),
        team_id=uuid4(),
        display_name="합성 영업 담당자",
        role_code="member",
        job_title="영업 담당자",
        active=True,
    )

    async def override_member():
        return member

    app.dependency_overrides[get_current_member] = override_member
    monkeypatch.setattr(settings, "stt_api_key", SecretStr("synthetic-stt-key"))
    yield
    app.dependency_overrides.clear()


def test_transcribes_valid_audio_through_openai(monkeypatch):
    provider = _OpenAIStub()
    monkeypatch.setattr(stt.httpx, "AsyncClient", lambda **_kwargs: provider)

    with TestClient(app) as client:
        response = client.post(
            "/api/transcriptions",
            headers={"Origin": ORIGIN},
            files={"audio": ("meeting.wav", WAV, "audio/wav")},
        )

    assert response.status_code == 200
    assert response.json() == {"transcript": "고객과 다음 주 계약 일정을 논의했습니다."}
    assert len(provider.calls) == 1
    url, request = provider.calls[0]
    assert url == "https://api.openai.com/v1/audio/transcriptions"
    assert request["data"]["model"] == settings.stt_model
    assert request["data"]["language"] == "ko"
    assert request["files"]["file"] == ("meeting.wav", WAV, "audio/wav")


@pytest.mark.parametrize(
    ("file_name", "media_type", "content", "detail", "code"),
    [
        ("meeting.exe", "audio/wav", WAV, "unsupported_file_extension", 415),
        ("meeting.wav", "image/png", WAV, "media_type_mismatch", 415),
        ("meeting.wav", "audio/wav", b"MZ\x90\x00", "file_signature_mismatch", 415),
        ("meeting.wav", "audio/wav", b"", "empty_file", 422),
    ],
)
def test_rejects_invalid_audio_before_provider(
    monkeypatch, file_name, media_type, content, detail, code
):
    called = False

    async def never_transcribe(**_kwargs):
        nonlocal called
        called = True
        return "호출되면 안 됩니다."

    monkeypatch.setattr(stt, "transcribe", never_transcribe)
    with TestClient(app) as client:
        response = client.post(
            "/api/transcriptions",
            headers={"Origin": ORIGIN},
            files={"audio": (file_name, content, media_type)},
        )

    assert response.status_code == code
    assert response.json() == {"detail": detail}
    assert called is False


def test_rejects_audio_over_configured_limit_before_provider(monkeypatch):
    monkeypatch.setattr(settings, "stt_max_bytes", len(WAV) - 1)

    async def never_transcribe(**_kwargs):
        raise AssertionError("크기 검증 전에 공급자를 호출했습니다.")

    monkeypatch.setattr(stt, "transcribe", never_transcribe)
    with TestClient(app) as client:
        response = client.post(
            "/api/transcriptions",
            headers={"Origin": ORIGIN},
            files={"audio": ("meeting.wav", WAV, "audio/wav")},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "file_too_large"}


def test_provider_failure_returns_only_safe_error(monkeypatch):
    async def failed_transcription(**_kwargs):
        raise stt.STTError("provider secret response")

    monkeypatch.setattr(stt, "transcribe", failed_transcription)
    with TestClient(app) as client:
        response = client.post(
            "/api/transcriptions",
            headers={"Origin": ORIGIN},
            files={"audio": ("meeting.wav", WAV, "audio/wav")},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "stt_unavailable"}
    assert "secret" not in response.text
