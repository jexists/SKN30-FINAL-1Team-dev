"""공유 개발 DB에 합성 팀 하나, 기본 설정과 구성원 두 명을 반복 가능하게 넣는다.

member.id 는 곧 auth.users.id 이므로 구성원 UUID 를 코드에 상수로 둘 수 없다.
Supabase Dashboard 에서 만든 사용자의 UID 를 인자로 받는다. 이 스크립트는
이메일·비밀번호를 다루지 않으며 자격증명은 Dashboard 에서만 관리한다.

    uv run python -m scripts.seed_demo_auth --manager <UUID> --member <UUID>
"""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models.workspace import Member, Team

# 기본 설정 정의는 어드민 계정 발급과 공유한다. 여기서는 팀·구성원만 다룬다.
from app.services.team_configuration import (  # noqa: F401  (테스트와 다른 seed 가 재수출을 쓴다)
    DEFAULT_PIPELINE_STAGES,
    LOOKUP_DEFAULTS,
    ConfigurationConflict,
    configuration_id,
    insert_missing,
    rows,
    seed_team_configuration,
)

TEAM_ID = UUID("6d0f1b76-6b1a-4b72-9ba3-1df477a62d78")
TEAM_NAME = "SalesLuv 데모팀"

# 각 항목이 Supabase 사용자 한 명과 1:1로 대응한다.
MEMBER_ACCOUNTS = (
    {
        "key": "manager",
        "flag": "--manager",
        "display_name": "김서현",
        "role_code": "manager",
        "job_title": "영업팀장",
    },
    {
        "key": "member",
        "flag": "--member",
        "display_name": "김지훈",
        "role_code": "member",
        "job_title": "영업 담당자",
    },
)


class _DryRun(Exception):
    """dry-run 에서 트랜잭션을 되돌리기 위한 내부 신호."""


async def seed_demo_auth(member_ids: dict[str, UUID], *, dry_run: bool = False) -> None:
    try:
        async with get_sessionmaker()() as session, session.begin():
            await _seed(session, member_ids)
            if dry_run:
                raise _DryRun
    except _DryRun:
        print("--dry-run 이므로 아무것도 저장하지 않았습니다.")
        return
    except IntegrityError as error:
        flags = [f"  {account['flag']} {member_ids[account['key']]}" for account in MEMBER_ACCOUNTS]
        raise SystemExit(
            "구성원을 넣지 못했습니다. auth.users 에 없는 UUID 이거나 참조가 어긋납니다. "
            "Supabase Dashboard 에서 사용자를 먼저 확인하세요." + "\n" + "\n".join(flags)
        ) from error

    print(f"개발 DB에 합성 팀 '{TEAM_NAME}', 기본 설정과 구성원 2명을 준비했습니다.")


async def _seed(session: AsyncSession, member_ids: dict[str, UUID]) -> None:
    existing_teams = (
        await session.execute(
            select(Team.id, Team.name).where(Team.id == TEAM_ID).with_for_update()
        )
    ).all()
    if any(name != TEAM_NAME for _team_id, name in existing_teams):
        raise SystemExit("기존 팀과 데모 팀 ID 또는 이름이 충돌합니다.")

    team_insert = insert(Team).values(id=TEAM_ID, name=TEAM_NAME)
    upserted_team_id = (
        await session.execute(
            team_insert.on_conflict_do_update(
                index_elements=[Team.id],
                set_={"name": team_insert.excluded.name},
                where=Team.name == TEAM_NAME,
            ).returning(Team.id)
        )
    ).scalar_one_or_none()
    if upserted_team_id is None:
        raise SystemExit("기존 팀과 데모 팀 ID 또는 이름이 충돌합니다.")

    await seed_team_configuration(session, TEAM_ID)

    # 다른 팀의 구성원을 이 팀으로 끌어오지 않는다.
    existing_members = (
        await session.execute(
            select(Member.id, Member.team_id)
            .where(Member.id.in_(member_ids.values()))
            .with_for_update()
        )
    ).all()
    if any(team_id != TEAM_ID for _member_id, team_id in existing_members):
        raise SystemExit("기존 구성원과 데모 계정의 ID 또는 팀이 충돌합니다.")

    for account in MEMBER_ACCOUNTS:
        member_insert = insert(Member).values(
            id=member_ids[account["key"]],
            team_id=TEAM_ID,
            display_name=account["display_name"],
            role_code=account["role_code"],
            job_title=account["job_title"],
            active=True,
        )
        await session.execute(
            member_insert.on_conflict_do_update(
                index_elements=[Member.id],
                set_={
                    "team_id": member_insert.excluded.team_id,
                    "display_name": member_insert.excluded.display_name,
                    "role_code": member_insert.excluded.role_code,
                    "job_title": member_insert.excluded.job_title,
                    "active": member_insert.excluded.active,
                },
            )
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Supabase Dashboard 에서 만든 사용자 UID 를 받아 데모 팀과 구성원을 넣습니다. "
            "UID 는 자격증명이 아니지만 저장소나 .env 에 두지 않습니다."
        )
    )
    for account in MEMBER_ACCOUNTS:
        parser.add_argument(
            account["flag"],
            required=True,
            metavar="UUID",
            help=f"{account['display_name']} ({account['role_code']}) 의 Supabase 사용자 UID",
        )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="넣을 내용을 출력만 하고 저장하지 않습니다.",
    )
    return parser.parse_args(argv)


def member_ids_from_args(args: argparse.Namespace) -> dict[str, UUID]:
    """DB 를 건드리기 전에 형식과 중복을 모두 거른다."""
    member_ids: dict[str, UUID] = {}
    for account in MEMBER_ACCOUNTS:
        raw = getattr(args, account["key"])
        try:
            member_ids[account["key"]] = UUID(raw)
        except (ValueError, AttributeError, TypeError) as error:
            raise SystemExit(f"{account['flag']} 값이 UUID 형식이 아닙니다: {raw}") from error

    if len(set(member_ids.values())) != len(member_ids):
        raise SystemExit(
            "서로 다른 역할에 같은 UUID 를 줄 수 없습니다. "
            "Dashboard 에서 계정별 UID 를 다시 확인하세요."
        )
    return member_ids


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    member_ids = member_ids_from_args(args)

    print(f"팀 {TEAM_NAME} ({TEAM_ID})")
    for account in MEMBER_ACCOUNTS:
        print(
            f"  {account['display_name']} / {account['role_code']} / "
            f"{account['job_title']} <- {member_ids[account['key']]}"
        )

    asyncio.run(seed_demo_auth(member_ids, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
