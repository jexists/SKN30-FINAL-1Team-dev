"""공유 개발 DB에 합성 팀 하나, 기본 설정과 구성원 두 명을 반복 가능하게 넣는다.

member.id 는 곧 auth.users.id 이므로 구성원 UUID 를 코드에 상수로 둘 수 없다.
Supabase Dashboard 에서 만든 사용자의 UID 를 인자로 받는다. 이 스크립트는
이메일·비밀번호를 다루지 않으며 자격증명은 Dashboard 에서만 관리한다.

    uv run python -m scripts.seed_demo_auth --manager <UUID> --member <UUID>
"""

import argparse
import asyncio
from datetime import UTC, datetime
from hashlib import md5
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models.configuration import (
    ActivityActionTag,
    ActivityCategory,
    CustomerContactStatus,
    PurchaseOrderStatus,
    SalesDealType,
)
from app.models.sales import SalesPipeline, SalesPipelineStage
from app.models.workspace import Member, Team

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


def rows(columns, values):
    return tuple(dict(zip(columns, value, strict=True)) for value in values)


LOOKUP_DEFAULTS = (
    (
        CustomerContactStatus,
        "customer_contact_status",
        rows(
            ("code", "name", "tone", "position"),
            (
                ("new", "신규", "gray", 0),
                ("proposal", "제안", "blue", 1),
                ("negotiation", "협의", "orange", 2),
                ("contracted", "계약", "green", 3),
                ("on_hold", "보류", "red", 4),
            ),
        ),
    ),
    (
        ActivityCategory,
        "activity_category",
        rows(
            ("code", "name", "tone", "position", "activity_type"),
            (
                ("visit", "방문", "blue", 0, "meeting"),
                ("demo", "데모", "purple", 1, "meeting"),
                ("education", "교육", "green", 2, "meeting"),
                ("call", "전화", "gray", 3, "meeting"),
                ("delivery", "납품", "orange", 4, "meeting"),
                ("conference", "컨퍼런스", "purple", 5, "meeting"),
                ("internal", "내부업무", "gray", 6, "task"),
            ),
        ),
    ),
    (
        ActivityActionTag,
        "activity_action_tag",
        rows(
            ("code", "name", "tone", "position", "activity_type"),
            (
                ("first_call", "첫 전화", "gray", 0, "meeting"),
                ("meeting", "미팅", "blue", 1, "meeting"),
                ("demo_requested", "데모 요청", "blue", 2, "meeting"),
                ("demo_in_progress", "데모 진행", "purple", 3, "meeting"),
                ("demo_completed", "데모 완료", "green", 4, "meeting"),
                ("quote_completed", "견적완료", "purple", 5, "meeting"),
                ("contract_completed", "계약완료", "green", 6, "meeting"),
                ("product_training", "제품교육", "blue", 7, "meeting"),
                ("delivery_completed", "납품완료", "green", 8, "meeting"),
                ("internal_meeting", "내부회의", "gray", 9, "meeting"),
                ("weekly_review", "주간점검", "gray", 10, "task"),
                ("monthly_review", "월간점검", "gray", 11, "task"),
                ("quarterly_review", "분기점검", "gray", 12, "task"),
                ("conference", "컨퍼런스", "purple", 13, "meeting"),
                ("ojt", "OJT", "blue", 14, "task"),
            ),
        ),
    ),
    (
        SalesDealType,
        "sales_deal_type",
        rows(
            ("code", "name", "position"),
            (
                ("new_installation", "신규 도입", 0),
                ("expansion", "증설", 1),
                ("renewal", "갱신", 2),
                ("maintenance", "유지보수", 3),
                ("consumables_supply", "소모품 공급", 4),
            ),
        ),
    ),
    (
        PurchaseOrderStatus,
        "purchase_order_status",
        rows(
            ("code", "name", "tone", "position", "outcome_code"),
            (
                ("order_received", "발주 접수", "gray", 0, "in_progress"),
                (
                    "dispatch_request_completed",
                    "출고 의뢰서 완료",
                    "purple",
                    1,
                    "in_progress",
                ),
                ("in_production", "생산중", "orange", 2, "in_progress"),
                ("stock_received", "입고 완료", "blue", 3, "in_progress"),
                ("delivered", "납품 완료", "green", 4, "completed"),
                ("cancelled", "취소", "red", 5, "cancelled"),
            ),
        ),
    ),
)

DEFAULT_PIPELINE_STAGES = rows(
    ("stage_code", "name", "tone", "phase_code", "outcome_code", "position"),
    (
        ("needs_validation", "니즈 검증", "gray", "sales", "in_progress", 0),
        ("product_demo", "제품 시연 평가", "blue", "sales", "in_progress", 1),
        ("quote_sent", "견적서 발송", "purple", "quote", "in_progress", 2),
        ("contract_sent", "계약서 발송", "orange", "contract", "in_progress", 3),
        ("contract_review", "계약서 검토", "orange", "contract", "in_progress", 4),
        ("contract_completed", "계약 완료", "green", "contract", "confirmed", 5),
        ("order_in_progress", "발주 진행", "purple", "order", "confirmed", 6),
        ("order_delivered", "납품 완료", "green", "order", "confirmed", 7),
        ("closed_cancelled", "취소", "red", "closed", "cancelled", 8),
    ),
)


def configuration_id(namespace_id: UUID, table_name: str, natural_key: str) -> UUID:
    raw = f"{namespace_id}:{table_name}:{natural_key}".encode()
    return UUID(md5(raw, usedforsecurity=False).hexdigest())


def insert_missing(model, values: dict):
    return insert(model).values(values).on_conflict_do_nothing()


async def seed_team_configuration(session: AsyncSession, team_id: UUID) -> None:
    for model, table_name, defaults in LOOKUP_DEFAULTS:
        expected_ids = {
            row["code"]: configuration_id(team_id, table_name, row["code"]) for row in defaults
        }
        existing = (
            await session.execute(
                select(model.id, model.team_id, model.code)
                .where(
                    or_(
                        model.id.in_(expected_ids.values()),
                        and_(model.team_id == team_id, model.code.in_(expected_ids)),
                    )
                )
                .with_for_update()
            )
        ).all()
        existing_codes = set()
        deterministic_ids = set(expected_ids.values())
        for row in existing:
            if (
                row.team_id != team_id
                or row.code not in expected_ids
                or (row.id in deterministic_ids and expected_ids[row.code] != row.id)
            ):
                raise SystemExit(f"{table_name} 기본값의 ID, 팀 또는 code가 충돌합니다.")
            existing_codes.add(row.code)

        for row in defaults:
            if row["code"] not in existing_codes:
                await session.execute(
                    insert_missing(
                        model,
                        {
                            "id": expected_ids[row["code"]],
                            "team_id": team_id,
                            **row,
                        },
                    )
                )

    expected_pipeline_id = configuration_id(team_id, "sales_pipeline", "default")
    pipelines = (
        (
            await session.execute(
                select(SalesPipeline)
                .where(
                    or_(
                        SalesPipeline.id == expected_pipeline_id,
                        and_(SalesPipeline.team_id == team_id, SalesPipeline.name == "기본 영업"),
                        and_(
                            SalesPipeline.team_id == team_id,
                            SalesPipeline.status_code == "published",
                            SalesPipeline.is_default.is_(True),
                        ),
                    )
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if pipelines:
        if len(pipelines) != 1:
            raise SystemExit("기본 영업 파이프라인의 ID, 이름 또는 기본값이 충돌합니다.")
        pipeline = pipelines[0]
        if (
            pipeline.team_id != team_id
            or pipeline.name != "기본 영업"
            or pipeline.description is not None
            or pipeline.status_code != "published"
            or not pipeline.is_default
            or pipeline.published_at is None
            or pipeline.archived_at is not None
        ):
            raise SystemExit("기존 기본 영업 파이프라인은 seed 값과 다르므로 덮어쓰지 않습니다.")
        pipeline_id = pipeline.id
    else:
        pipeline_id = expected_pipeline_id
        await session.execute(
            insert_missing(
                SalesPipeline,
                {
                    "id": pipeline_id,
                    "team_id": team_id,
                    "name": "기본 영업",
                    "description": None,
                    "status_code": "published",
                    "is_default": True,
                    "published_at": datetime.now(UTC),
                    "archived_at": None,
                },
            )
        )

    expected_stages = {
        row["stage_code"]: (
            configuration_id(pipeline_id, "sales_pipeline_stage", row["stage_code"]),
            row,
        )
        for row in DEFAULT_PIPELINE_STAGES
    }
    stages = (
        (
            await session.execute(
                select(SalesPipelineStage)
                .where(
                    or_(
                        SalesPipelineStage.sales_pipeline_id == pipeline_id,
                        SalesPipelineStage.id.in_(
                            stage_id for stage_id, _row in expected_stages.values()
                        ),
                    )
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    existing_stage_codes = set()
    deterministic_stage_ids = {stage_id for stage_id, _row in expected_stages.values()}
    for stage in stages:
        expected = expected_stages.get(stage.stage_code)
        if (
            expected is None
            or stage.sales_pipeline_id != pipeline_id
            or (stage.id in deterministic_stage_ids and stage.id != expected[0])
            or any(getattr(stage, key) != value for key, value in expected[1].items())
        ):
            raise SystemExit("기본 영업 단계의 ID, pipeline 또는 고정 정의가 충돌합니다.")
        existing_stage_codes.add(stage.stage_code)

    for row in DEFAULT_PIPELINE_STAGES:
        if row["stage_code"] not in existing_stage_codes:
            await session.execute(
                insert_missing(
                    SalesPipelineStage,
                    {
                        "id": expected_stages[row["stage_code"]][0],
                        "sales_pipeline_id": pipeline_id,
                        **row,
                    },
                )
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
