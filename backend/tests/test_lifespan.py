"""앱이 어떤 길로 나가든 커넥션 풀을 반납하는지 검증한다."""

import pytest

from app import main
from app.main import lifespan


class _Engine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.anyio
async def test_lifespan_disposes_engine_on_normal_exit(monkeypatch):
    engine = _Engine()
    monkeypatch.setattr(main, "get_engine", lambda: engine)

    async with lifespan(None):
        pass

    assert engine.disposed


@pytest.mark.anyio
async def test_lifespan_disposes_engine_when_body_raises(monkeypatch):
    """예외로 나가도 반납해야 한다. 안 그러면 죽는 프로세스가 pooler 슬롯을 쥔 채 남는다."""
    engine = _Engine()
    monkeypatch.setattr(main, "get_engine", lambda: engine)

    with pytest.raises(RuntimeError, match="boom"):
        async with lifespan(None):
            raise RuntimeError("boom")

    assert engine.disposed


@pytest.mark.anyio
async def test_lifespan_ignores_missing_engine(monkeypatch):
    """DB 를 한 번도 안 쓴 프로세스에서는 get_engine() 이 실패한다. 종료를 막지 않는다."""

    def _fail():
        raise RuntimeError("DATABASE_URL 미설정")

    monkeypatch.setattr(main, "get_engine", _fail)

    async with lifespan(None):
        pass
