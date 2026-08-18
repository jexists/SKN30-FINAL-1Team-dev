r"""Supabase Auth 사용자를 기존 구성원에 연결한다.

Supabase Dashboard(Authentication > Users)에서 만든 사용자의 UID 를 인자로 받는다.
이메일과 비밀번호는 입력받지도 출력하지도 않는다. UID 를 .env 에 두지 않는다.

역할은 이 명령이 정하지 않는다. 팀·역할은 seed 가 만든 member 행에 이미 들어
있고, 어느 플래그에 UID 를 넣느냐가 그 사람이 어느 자리에 앉는지를 정한다.

필요한 역할만 골라 줄 수 있다. 계정을 한 번에 다 만들지 않아도 되고, 나중에
한 명씩 추가로 붙일 수도 있다. 주지 않은 역할의 구성원은 건드리지 않는다.

    uv run python -m scripts.link_demo_auth_users --dry-run \
        --filled-manager <UUID> --filled-member <UUID>

--dry-run 으로 바뀔 내용을 먼저 확인한 뒤 플래그를 빼고 실행한다.
같은 인자로 여러 번 실행해도 결과는 같다.
"""

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select, update

from app.db.session import get_sessionmaker
from app.models.workspace import Member
from scripts.seed_demo_auth import (
    EMPTY_MANAGER_ID,
    EMPTY_MEMBER_ID,
    FILLED_MANAGER_ID,
    FILLED_MEMBER_ID,
    TEST_MANAGER_ID,
    TEST_MEMBER_ID,
)

# 로그인하는 여섯 역할만 연결한다. member2 두 명은 auth_user_id 가 NULL 로 남는다.
ROLES = (
    ("filled_manager", "--filled-manager", FILLED_MANAGER_ID),
    ("filled_member", "--filled-member", FILLED_MEMBER_ID),
    ("empty_manager", "--empty-manager", EMPTY_MANAGER_ID),
    ("empty_member", "--empty-member", EMPTY_MEMBER_ID),
    ("test_manager", "--test-manager", TEST_MANAGER_ID),
    ("test_member", "--test-member", TEST_MEMBER_ID),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="link_demo_auth_users",
        description="Supabase Auth 사용자 UID 를 기존 member 행에 연결합니다.",
    )
    for _name, flag, _member_id in ROLES:
        parser.add_argument(
            flag,
            default=None,
            metavar="UUID",
            help="Supabase auth.users.id (연결할 역할만 주면 됩니다)",
        )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="변경 없이 현재 상태와 적용 결과만 출력합니다.",
    )
    return parser


def parse_assignments(args: argparse.Namespace) -> dict[UUID, UUID]:
    """준 역할만 member id 에 매핑한다. 문제가 있으면 DB 를 건드리기 전에 멈춘다."""
    assignments: dict[UUID, UUID] = {}
    seen: dict[UUID, str] = {}
    for name, flag, member_id in ROLES:
        raw = getattr(args, name)
        if raw is None:
            continue
        try:
            auth_user_id = UUID(str(raw).strip())
        except (AttributeError, TypeError, ValueError) as error:
            raise SystemExit(f"{flag} 값이 올바른 UUID 가 아닙니다.") from error
        if auth_user_id in seen:
            raise SystemExit(f"{flag} 와 {seen[auth_user_id]} 에 같은 UUID 가 들어왔습니다.")
        seen[auth_user_id] = flag
        assignments[member_id] = auth_user_id

    if not assignments:
        # 아무 일도 안 하고 조용히 끝나면 성공한 줄 안다.
        raise SystemExit(
            "연결할 역할을 최소 하나는 지정하세요: "
            + ", ".join(flag for _name, flag, _member_id in ROLES)
        )
    return assignments


async def link_demo_auth_users(assignments: dict[UUID, UUID], *, dry_run: bool) -> None:
    async with get_sessionmaker()() as session, session.begin():
        rows = (
            await session.execute(
                select(Member.id, Member.display_name, Member.role_code, Member.auth_user_id)
                .where(Member.id.in_(assignments))
                .with_for_update()
            )
        ).all()

        found = {row.id for row in rows}
        missing = set(assignments) - found
        if missing:
            raise SystemExit(
                "연결할 구성원이 없습니다. scripts.seed_demo_auth 를 먼저 실행하세요: "
                + ", ".join(str(member_id) for member_id in sorted(missing, key=str))
            )

        # 다른 구성원이 이미 쓰고 있는 UID 는 UNIQUE 제약에 걸리기 전에 막는다.
        taken = (
            await session.execute(
                select(Member.id, Member.auth_user_id).where(
                    Member.auth_user_id.in_(assignments.values())
                )
            )
        ).all()
        for member_id, auth_user_id in taken:
            if assignments.get(member_id) != auth_user_id:
                raise SystemExit(f"이미 다른 구성원({member_id})에 연결된 UUID 가 있습니다.")

        for row in sorted(rows, key=lambda item: str(item.id)):
            target = assignments[row.id]
            before = "없음" if row.auth_user_id is None else str(row.auth_user_id)
            mark = "유지" if row.auth_user_id == target else "변경"
            print(f"[{mark}] {row.display_name}({row.role_code}) {before} -> {target}")

        # 부분 실행이라는 사실이 화면에 남아야 한다. 빠진 역할은 로그인할 수 없다.
        skipped = [flag for _name, flag, member_id in ROLES if member_id not in assignments]
        if skipped:
            print(f"이번에 연결하지 않은 역할: {', '.join(skipped)}")

        if dry_run:
            print("--dry-run 이므로 아무것도 저장하지 않았습니다.")
            await session.rollback()
            return

        for member_id, auth_user_id in assignments.items():
            await session.execute(
                update(Member).where(Member.id == member_id).values(auth_user_id=auth_user_id)
            )
        print(f"구성원 {len(assignments)}명에 Supabase 사용자를 연결했습니다.")


def main() -> None:
    args = build_parser().parse_args()
    assignments = parse_assignments(args)
    asyncio.run(link_demo_auth_users(assignments, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
