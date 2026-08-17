"""공유 개발 DB에 두 합성 팀과 로그인 계정 네 개를 반복 가능하게 넣는다."""

import asyncio
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_sessionmaker
from app.models.workspace import Member, Team

FILLED_TEAM_ID = UUID("6d0f1b76-6b1a-4b72-9ba3-1df477a62d78")
EMPTY_TEAM_ID = UUID("dc153ea5-9ba6-4b96-a4df-845a44798003")
FILLED_MANAGER_ID = UUID("a6a7a7f6-7141-4b94-9355-bde585f44d1a")
FILLED_MEMBER_ID = UUID("86d40aa1-0a5b-4a23-912f-e039c392c60a")
EMPTY_MANAGER_ID = UUID("7a489d16-0e50-4061-9c23-8756fb79e3ed")
EMPTY_MEMBER_ID = UUID("cc1b70c1-71bb-421b-9ce4-66464ee17018")


async def seed_demo_auth() -> None:
    (
        filled_manager_login_id,
        filled_member_login_id,
        empty_manager_login_id,
        empty_member_login_id,
    ) = (
        settings.demo_filled_manager_login_id.strip().lower(),
        settings.demo_filled_member_login_id.strip().lower(),
        settings.demo_empty_manager_login_id.strip().lower(),
        settings.demo_empty_member_login_id.strip().lower(),
    )
    login_ids = (
        filled_manager_login_id,
        filled_member_login_id,
        empty_manager_login_id,
        empty_member_login_id,
    )
    password = settings.demo_password.get_secret_value()

    if not all(login_ids) or not password:
        raise SystemExit("backend/.env의 DEMO_* 인증 값을 먼저 채워주세요.")
    if len(set(login_ids)) != len(login_ids):
        raise SystemExit("네 데모 계정의 로그인 ID는 서로 달라야 합니다.")
    if any(len(login_id) > 254 for login_id in login_ids):
        raise SystemExit("데모 계정 로그인 ID는 254자 이하여야 합니다.")
    if not 1 <= len(password) <= 256:
        raise SystemExit("DEMO_PASSWORD는 1자 이상 256자 이하여야 합니다.")

    password_hashes = [await asyncio.to_thread(hash_password, password) for _ in login_ids]

    async with get_sessionmaker()() as session, session.begin():
        teams = (
            (FILLED_TEAM_ID, "SalesLuv 데모팀"),
            (EMPTY_TEAM_ID, "SalesLuv 첫 세팅팀"),
        )
        expected_team_names = dict(teams)
        existing_teams = await session.execute(
            select(Team.id, Team.name)
            .where(Team.id.in_(expected_team_names.keys()))
            .with_for_update()
        )
        if any(expected_team_names[team_id] != name for team_id, name in existing_teams):
            raise SystemExit("기존 팀과 데모 팀 ID 또는 이름이 충돌합니다.")

        for team_id, name in teams:
            team_insert = insert(Team).values(id=team_id, name=name)
            upserted_team_id = (
                await session.execute(
                    team_insert.on_conflict_do_update(
                        index_elements=[Team.id],
                        set_={"name": team_insert.excluded.name},
                        where=Team.name == name,
                    ).returning(Team.id)
                )
            ).scalar_one_or_none()
            if upserted_team_id is None:
                raise SystemExit("기존 팀과 데모 팀 ID 또는 이름이 충돌합니다.")

        accounts = (
            {
                "id": FILLED_MANAGER_ID,
                "team_id": FILLED_TEAM_ID,
                "login_id": filled_manager_login_id,
                "password_hash": password_hashes[0],
                "display_name": "김서현",
                "role_code": "manager",
                "job_title": "영업팀장",
            },
            {
                "id": FILLED_MEMBER_ID,
                "team_id": FILLED_TEAM_ID,
                "login_id": filled_member_login_id,
                "password_hash": password_hashes[1],
                "display_name": "김지훈",
                "role_code": "member",
                "job_title": "영업 담당자",
            },
            {
                "id": EMPTY_MANAGER_ID,
                "team_id": EMPTY_TEAM_ID,
                "login_id": empty_manager_login_id,
                "password_hash": password_hashes[2],
                "display_name": "김서현",
                "role_code": "manager",
                "job_title": "영업팀장",
            },
            {
                "id": EMPTY_MEMBER_ID,
                "team_id": EMPTY_TEAM_ID,
                "login_id": empty_member_login_id,
                "password_hash": password_hashes[3],
                "display_name": "김지훈",
                "role_code": "member",
                "job_title": "영업 담당자",
            },
        )
        expected_by_id = {
            account["id"]: (account["login_id"], account["team_id"]) for account in accounts
        }
        expected_by_login = {
            login_id: member_id for member_id, (login_id, _team_id) in expected_by_id.items()
        }
        existing = await session.execute(
            select(Member.id, Member.login_id, Member.team_id)
            .where(
                or_(
                    Member.id.in_(expected_by_id),
                    Member.login_id.in_(expected_by_login),
                )
            )
            .with_for_update()
        )
        for member_id, login_id, team_id in existing:
            expected_member = expected_by_id.get(member_id)
            expected_member_id = expected_by_login.get(login_id)
            if (
                expected_member is None
                or team_id != expected_member[1]
                or (expected_member_id is not None and expected_member_id != member_id)
            ):
                raise SystemExit("기존 회원과 데모 계정 ID, 로그인 ID 또는 팀이 충돌합니다.")

        for account in accounts:
            member_insert = insert(Member).values(active=True, **account)
            await session.execute(
                member_insert.on_conflict_do_update(
                    index_elements=[Member.id],
                    set_={
                        "team_id": member_insert.excluded.team_id,
                        "login_id": member_insert.excluded.login_id,
                        "password_hash": member_insert.excluded.password_hash,
                        "display_name": member_insert.excluded.display_name,
                        "role_code": member_insert.excluded.role_code,
                        "job_title": member_insert.excluded.job_title,
                        "active": member_insert.excluded.active,
                    },
                )
            )

    print("개발 DB의 합성 팀 2개와 로그인 계정 4개를 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_auth())
