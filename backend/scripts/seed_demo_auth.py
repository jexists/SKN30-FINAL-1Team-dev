"""공유 개발 DB에 합성 로그인 계정 두 개를 반복 가능하게 넣는다."""

import asyncio
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.models.workspace import Member, Team

TEAM_ID = UUID("6d0f1b76-6b1a-4b72-9ba3-1df477a62d78")
MANAGER_ID = UUID("a6a7a7f6-7141-4b94-9355-bde585f44d1a")
MEMBER_ID = UUID("86d40aa1-0a5b-4a23-912f-e039c392c60a")


async def seed_demo_auth() -> None:
    manager_login_id = settings.demo_manager_login_id.strip().lower()
    member_login_id = settings.demo_member_login_id.strip().lower()
    password = settings.demo_password.get_secret_value()

    if not manager_login_id or not member_login_id or not password:
        raise SystemExit("backend/.env의 DEMO_* 인증 값을 먼저 채워주세요.")
    if manager_login_id == member_login_id:
        raise SystemExit("두 데모 계정의 로그인 ID는 달라야 합니다.")
    if len(password) > 256:
        raise SystemExit("DEMO_PASSWORD는 256자 이하여야 합니다.")

    manager_hash = await asyncio.to_thread(hash_password, password)
    member_hash = await asyncio.to_thread(hash_password, password)

    async with get_sessionmaker()() as session, session.begin():
        team_insert = insert(Team).values(id=TEAM_ID, name="SalesLuv 데모팀")
        await session.execute(
            team_insert.on_conflict_do_update(
                index_elements=[Team.id],
                set_={"name": team_insert.excluded.name},
            )
        )

        accounts = (
            {
                "id": MANAGER_ID,
                "login_id": manager_login_id,
                "password_hash": manager_hash,
                "display_name": "김서현",
                "role_code": "manager",
                "job_title": "영업팀장",
            },
            {
                "id": MEMBER_ID,
                "login_id": member_login_id,
                "password_hash": member_hash,
                "display_name": "김지훈",
                "role_code": "member",
                "job_title": "영업 담당자",
            },
        )
        expected_by_id = {account["id"]: account["login_id"] for account in accounts}
        expected_by_login = {login_id: member_id for member_id, login_id in expected_by_id.items()}
        existing = await session.execute(
            select(Member.id, Member.login_id).where(
                or_(
                    Member.id.in_(expected_by_id),
                    Member.login_id.in_(expected_by_login),
                )
            )
        )
        for member_id, login_id in existing:
            if (
                expected_by_id.get(member_id) != login_id
                or expected_by_login.get(login_id) != member_id
            ):
                raise SystemExit("기존 회원과 데모 계정 ID 또는 로그인 ID가 충돌합니다.")

        for account in accounts:
            member_insert = insert(Member).values(team_id=TEAM_ID, active=True, **account)
            await session.execute(
                member_insert.on_conflict_do_update(
                    index_elements=[Member.id],
                    set_={
                        "team_id": member_insert.excluded.team_id,
                        "password_hash": member_insert.excluded.password_hash,
                        "display_name": member_insert.excluded.display_name,
                        "role_code": member_insert.excluded.role_code,
                        "job_title": member_insert.excluded.job_title,
                        "active": member_insert.excluded.active,
                    },
                )
            )

    print("개발 DB의 합성 로그인 계정 2개를 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_auth())
