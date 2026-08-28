"""계정 요청 테스트.

실제 Discord 를 부르지 않는다. services.discord 의 전송 함수를 갈아끼워
"요청이 사라지는 경우"가 있는지를 본다. DB 를 쓰지 않으므로 항상 돈다.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.signup import _MAX_REQUESTS, _request_limiter
from app.core.config import settings
from app.main import app
from app.services import discord

ORIGIN = settings.cors_origin_list[0]


class _Spy:
    """보낸 이메일을 기억하거나, 정해 둔 실패를 던진다."""

    def __init__(self, *, raises: Exception | None = None):
        self.raises = raises
        self.emails: list[str] = []

    async def send_account_request(self, *, email: str) -> None:
        self.emails.append(email)
        if self.raises is not None:
            raise self.raises


@pytest.fixture(autouse=True)
def signup_environment(monkeypatch):
    monkeypatch.setattr(settings, "discord_webhook_url", SecretStr("https://discord.test/hook"))
    _request_limiter.clear()
    yield
    _request_limiter.clear()


def _client(spy: _Spy, monkeypatch) -> TestClient:
    monkeypatch.setattr(discord, "send_account_request", spy.send_account_request)
    return TestClient(app)


def _post(client: TestClient, email: str, *, origin: str | None = ORIGIN):
    headers = {"Origin": origin} if origin is not None else {}
    return client.post("/api/signup/request", headers=headers, json={"email": email})


def test_account_request_reaches_discord_normalized(monkeypatch):
    spy = _Spy()
    response = _post(_client(spy, monkeypatch), "  Someone@Example.COM  ")

    assert response.status_code == 204
    assert spy.emails == ["someone@example.com"]


def test_malformed_email_is_rejected_before_discord(monkeypatch):
    spy = _Spy()
    response = _post(_client(spy, monkeypatch), "not-an-email")

    assert response.status_code == 422
    assert spy.emails == []


def test_missing_webhook_is_reported_as_configuration(monkeypatch):
    spy = _Spy(raises=discord.DiscordNotConfigured("signup_not_configured"))
    response = _post(_client(spy, monkeypatch), "someone@example.com")

    assert response.status_code == 503
    assert response.json() == {"detail": "signup_not_configured"}


def test_delivery_failure_is_reported_to_the_requester(monkeypatch):
    """요청을 DB 에 쌓지 않으므로 전송 실패는 반드시 사용자에게 알려야 한다."""
    spy = _Spy(raises=discord.DiscordError("signup_delivery_failed:ConnectError"))
    response = _post(_client(spy, monkeypatch), "someone@example.com")

    assert response.status_code == 503
    assert response.json() == {"detail": "signup_unavailable"}


def test_delivery_failure_does_not_consume_an_attempt(monkeypatch):
    """서버 잘못으로 시도 슬롯을 채우면 다시 시도할 기회까지 잃는다."""
    failing = _Spy(raises=discord.DiscordError("signup_delivery_failed:ConnectError"))
    client = _client(failing, monkeypatch)
    for _ in range(_MAX_REQUESTS + 1):
        assert _post(client, "someone@example.com").status_code == 503

    succeeding = _Spy()
    assert _post(_client(succeeding, monkeypatch), "someone@example.com").status_code == 204


def test_repeated_requests_from_one_ip_are_limited(monkeypatch):
    spy = _Spy()
    client = _client(spy, monkeypatch)
    for _ in range(_MAX_REQUESTS):
        assert _post(client, "someone@example.com").status_code == 204

    limited = _post(client, "someone@example.com")

    assert limited.status_code == 429
    assert limited.json() == {"detail": "signup_rate_limited"}
    assert int(limited.headers["retry-after"]) > 0


def test_request_without_allowed_origin_is_refused(monkeypatch):
    spy = _Spy()
    response = _post(_client(spy, monkeypatch), "someone@example.com", origin=None)

    assert response.status_code == 403
    assert spy.emails == []
