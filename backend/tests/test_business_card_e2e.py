import pytest

from scripts.business_card_e2e import _required_env


def test_business_card_e2e_required_env_rejects_missing_value(monkeypatch):
    monkeypatch.delenv("SALESLUV_E2E_EMAIL", raising=False)

    with pytest.raises(SystemExit, match="SALESLUV_E2E_EMAIL"):
        _required_env("SALESLUV_E2E_EMAIL")


def test_business_card_e2e_required_env_strips_value(monkeypatch):
    monkeypatch.setenv("SALESLUV_E2E_CARD_PATH", "  /tmp/card.jpeg  ")

    assert _required_env("SALESLUV_E2E_CARD_PATH") == "/tmp/card.jpeg"
