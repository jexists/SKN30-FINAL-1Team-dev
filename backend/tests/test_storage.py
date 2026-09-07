import pytest

from app.services import storage


class _Response:
    def __init__(self, status_code: int, body=None):
        self.status_code = status_code
        self.body = body

    def json(self):
        if isinstance(self.body, ValueError):
            raise self.body
        return self.body


class _Client:
    def __init__(self, response: _Response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def delete(self, *_args, **_kwargs):
        return self.response


@pytest.mark.anyio
async def test_remove_reports_http_delete_failure(monkeypatch):
    monkeypatch.setattr(storage, "_require_config", lambda: None)
    monkeypatch.setattr(storage, "_headers", lambda: {})
    monkeypatch.setattr(storage.httpx, "AsyncClient", lambda **_kwargs: _Client(_Response(503)))

    assert await storage.remove(storage_key="team/draft.json") is False


@pytest.mark.anyio
async def test_remove_reports_success_only_after_http_delete_succeeds(monkeypatch):
    monkeypatch.setattr(storage, "_require_config", lambda: None)
    monkeypatch.setattr(storage, "_headers", lambda: {})
    monkeypatch.setattr(storage.httpx, "AsyncClient", lambda **_kwargs: _Client(_Response(204)))

    assert await storage.remove(storage_key="team/draft.json") is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,body,removed",
    [
        (404, {"code": "NoSuchKey"}, True),
        (404, {"code": "NoSuchBucket"}, False),
        (403, {"code": "AccessDenied"}, False),
        (404, None, False),
        (404, [], False),
        (404, ValueError("invalid JSON"), False),
    ],
)
async def test_remove_accepts_only_confirmed_missing_objects(monkeypatch, status, body, removed):
    monkeypatch.setattr(storage, "_require_config", lambda: None)
    monkeypatch.setattr(storage, "_headers", lambda: {})
    monkeypatch.setattr(
        storage.httpx, "AsyncClient", lambda **_kwargs: _Client(_Response(status, body))
    )
    assert await storage.remove(storage_key="team/draft.json") is removed
