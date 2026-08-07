"""비동기 DB 엔진과 세션.

Supabase session pooler를 사용하는 장기 실행 FastAPI 서버를 전제로 합니다.
SQLAlchemy의 기본 연결 풀을 사용하고 끊어진 연결은 재사용 전에 확인합니다.

엔진은 import 시점이 아니라 처음 쓸 때 만듭니다.
그래야 DATABASE_URL 이 없는 환경(CI 등)에서도 앱을 import 할 수 있고,
DB 를 쓰지 않는 테스트가 DB 설정에 끌려가지 않습니다.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL 이 설정되지 않았습니다. backend/.env 를 확인하세요.")

    return create_async_engine(
        settings.async_database_url,
        echo=settings.debug,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession]:
    """요청 범위의 비동기 DB 세션을 제공한다."""
    async with get_sessionmaker()() as session:
        yield session
