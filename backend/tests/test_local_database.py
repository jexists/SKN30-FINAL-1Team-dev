"""로컬 전용 DB의 실제 HTTP/저장/롤백 smoke. 인증 제공자는 대체한다."""

import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import customers
from app.api.deps import get_current_member
from app.core.config import settings
from app.db.session import get_db
from app.models.crm import CustomerCompany
from app.models.workspace import Member, Team

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not settings.run_integration_tests or not settings.database_url,
        reason="로컬 DB 실통합 테스트는 명시적으로 켠다",
    ),
]


def test_local_database_customer_isolation_commit_and_rollback():
    url = make_url(settings.async_database_url)
    assert settings.app_env == "test"
    assert url.host == "127.0.0.1" and url.port == 55432
    assert url.database == "salesluv_test" and url.username == "salesluv_test"
    asyncio.run(_exercise_database())


async def _exercise_database():
    engine = create_async_engine(settings.async_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    team_a, team_b, company_b = uuid4(), uuid4(), uuid4()
    member = Member(id=uuid4(), team_id=team_a, display_name="합성 팀장", role_code="manager")
    app = FastAPI()
    app.include_router(customers.router, prefix="/api")

    async def database():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_member] = lambda: member
    try:
        async with sessions.begin() as session:
            session.add_all([Team(id=team_a, name="합성 A팀"), Team(id=team_b, name="합성 B팀")])
            await session.flush()
            session.add(CustomerCompany(id=company_b, team_id=team_b, name="합성 B팀 고객사"))

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            created = await client.post("/api/customer-companies", json={"name": "합성 A팀 고객사"})
            assert created.status_code == 201, created.text
            company_a = UUID(created.json()["id"])
            own = await client.get(f"/api/customer-companies/{company_a}")
            assert own.status_code == 200 and own.json()["name"] == "합성 A팀 고객사"
            hidden = await client.get(f"/api/customer-companies/{company_b}")
            assert hidden.status_code == 404
            denied = await client.patch(
                f"/api/customer-companies/{company_b}", json={"name": "변조 시도"}
            )
            assert denied.status_code == 404
            listing = await client.get("/api/customer-companies")
            assert listing.status_code == 200
            assert {item["id"] for item in listing.json()["items"]} == {str(company_a)}
            assert listing.json()["total"] == 1

        # API 요청 세션이 닫힌 뒤 새 세션에서 commit과 거절된 쓰기를 확인한다.
        async with sessions() as session:
            assert (await session.get(CustomerCompany, company_a)).name == "합성 A팀 고객사"
            assert (await session.get(CustomerCompany, company_b)).name == "합성 B팀 고객사"

        # 두 행을 실제 flush한 뒤 실패시키고, 새 세션에서 원상복구를 확인한다.
        with pytest.raises(RuntimeError, match="injected failure"):
            async with sessions.begin() as session:
                a = await session.get(CustomerCompany, company_a)
                b = await session.get(CustomerCompany, company_b)
                a.name = "롤백 대상 A"
                await session.flush()
                b.name = "롤백 대상 B"
                await session.flush()
                raise RuntimeError("injected failure")
        async with sessions() as session:
            assert (await session.get(CustomerCompany, company_a)).name == "합성 A팀 고객사"
            assert (await session.get(CustomerCompany, company_b)).name == "합성 B팀 고객사"
    finally:
        try:
            async with sessions.begin() as session:
                await session.execute(
                    delete(CustomerCompany).where(CustomerCompany.team_id.in_([team_a, team_b]))
                )
                await session.execute(delete(Team).where(Team.id.in_([team_a, team_b])))
            async with sessions() as session:
                assert not (
                    await session.execute(select(Team.id).where(Team.id.in_([team_a, team_b])))
                ).all()
        finally:
            await engine.dispose()
