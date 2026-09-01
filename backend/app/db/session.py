"""비동기 DB 엔진과 세션.

Supabase pooler 뒤에 있는 장기 실행 FastAPI 서버를 전제로 합니다.
SQLAlchemy의 연결 풀을 사용하고 끊어진 연결은 재사용 전에 확인합니다.

접속 포트가 어느 pooler 인지를 정하고, 그에 따라 풀 설정이 갈립니다.
6543 은 transaction pooler, 그 밖(5432)은 session pooler 로 봅니다.

엔진은 import 시점이 아니라 처음 쓸 때 만듭니다.
그래야 DATABASE_URL 이 없는 환경(CI 등)에서도 앱을 import 할 수 있고,
DB 를 쓰지 않는 테스트가 DB 설정에 끌려가지 않습니다.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Supabase transaction pooler 포트. session pooler 는 5432 를 씁니다.
TRANSACTION_POOLER_PORT = 6543


def _transaction_pooler_args() -> dict[str, Any]:
    """transaction pooler 로 갈 때 asyncpg 에 붙이는 인자.

    transaction pooler 는 트랜잭션이 끝날 때마다 클라이언트를 다른 Postgres 연결에
    다시 붙인다. 그래서 앞선 연결에 만들어 둔 prepared statement 가 다음 트랜잭션에
    없거나, 같은 이름이 남의 연결에 이미 있는 일이 생긴다. 캐시를 끄고 이름을 매번
    새로 지어 이 두 가지를 모두 피한다.
    """
    return {
        # asyncpg 자체 캐시
        "statement_cache_size": 0,
        # SQLAlchemy asyncpg 방언이 따로 들고 있는 캐시
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL 이 설정되지 않았습니다. backend/.env 를 확인하세요.")

    url = settings.async_database_url
    transaction_mode = urlsplit(url).port == TRANSACTION_POOLER_PORT

    # session pooler 는 클라이언트 하나가 Postgres 연결 하나를 통째로 붙잡고 있고,
    # 한도 15 는 머신이 아니라 Supabase 프로젝트 단위다. 배포 서버, 팀원들의 로컬
    # 서버, pytest 가 모두 같은 15 를 나눠 쓴다. 화면 하나가 요청을 여러 개 동시에
    # 쏘는 순간 슬롯이 모자라 EMAXCONNSESSION 이 나고, 브라우저에는 500 으로 보인다.
    #
    # 그래서 앱은 transaction pooler(6543)로 붙는다. 이쪽은 트랜잭션 단위로 연결을
    # 돌려 쓰므로 클라이언트 수 한도가 훨씬 넉넉하다.
    #
    # 어느 쪽이든 한 프로세스가 상한 밖으로 커넥션을 더 여는 길(max_overflow)은
    # 두지 않는다. 풀이 찼을 때 오는 요청은 새로 열지 않고 pool_timeout 만큼 풀
    # 안에서 줄을 선다. async 라 커넥션을 붙잡는 시간이 짧아 줄은 금방 빠진다.
    #
    # ponytail: uvicorn worker 를 늘리거나 session pooler 로 되돌릴 때는
    # pool_size × 프로세스 수가 한도를 넘지 않는지 다시 계산한다.
    return create_async_engine(
        url,
        # echo=settings.debug,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,  # 이 프로세스가 쥘 수 있는 커넥션 수
        max_overflow=0,  # 상한 밖으로 더 열지 않는다. 넘치는 요청은 풀에서 기다린다
        pool_timeout=30,  # 커넥션을 기다리는 최대 시간(초)
        pool_recycle=1800,  # 오래된 커넥션을 재접속하는 주기(초)
        connect_args=_transaction_pooler_args() if transaction_mode else {},
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
