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

    # session pooler 는 클라이언트 하나가 Postgres 연결 하나를 통째로 붙잡고 있고,
    # 한도 15 는 머신이 아니라 Supabase 프로젝트 단위다. 배포 서버, 팀원들의 로컬
    # 서버, pytest 가 모두 같은 15 를 나눠 쓴다.
    #
    # SQLAlchemy 기본값(pool_size 5 + max_overflow 10)이면 프로세스 하나가 그 15 를
    # 혼자 다 가져갈 수 있어, 다른 누군가가 붙는 순간 EMAXCONNSESSION 이 난다.
    #
    # 그래서 한 프로세스가 쥘 수 있는 최대(pool_size + max_overflow)를 10 으로 묶는다.
    # blue/green 교체 중에는 컨테이너 둘이 잠깐 겹치지만, async 라 커넥션을 실제로
    # 붙잡는 시간은 짧아 둘이 동시에 상한까지 차는 일은 드물다. 그래도 넘치면 밖에서
    # 거절당하는 대신 pool_timeout 만큼 안에서 줄 선다.
    #
    # ponytail: uvicorn worker 를 늘리거나 슬롯이 늘면
    # (pool_size + max_overflow) × 프로세스 수가 15 를 넘지 않는지 다시 계산한다.
    return create_async_engine(
        settings.async_database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,  # 기본으로 유지할 커넥션 수
        max_overflow=5,  # 풀이 꽉 찼을 때 추가로 허용할 임시 커넥션 수 (합쳐 10)
        pool_timeout=30,  # 커넥션을 기다리는 최대 시간(초)
        pool_recycle=1800,  # 오래된 커넥션을 재접속하는 주기(초)
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
