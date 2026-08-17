"""공유 개발 DB에 두 합성 팀, 기본 설정과 로그인 계정 여섯 개를 반복 가능하게 넣는다."""

import asyncio
from datetime import UTC, datetime
from hashlib import md5
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
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

FILLED_TEAM_ID = UUID("6d0f1b76-6b1a-4b72-9ba3-1df477a62d78")
EMPTY_TEAM_ID = UUID("dc153ea5-9ba6-4b96-a4df-845a44798003")
FILLED_MANAGER_ID = UUID("a6a7a7f6-7141-4b94-9355-bde585f44d1a")
FILLED_MEMBER_ID = UUID("86d40aa1-0a5b-4a23-912f-e039c392c60a")
FILLED_MEMBER2_ID = UUID("318a44b7-6726-5054-9b67-469a43b3dd6f")
EMPTY_MANAGER_ID = UUID("7a489d16-0e50-4061-9c23-8756fb79e3ed")
EMPTY_MEMBER_ID = UUID("cc1b70c1-71bb-421b-9ce4-66464ee17018")
EMPTY_MEMBER2_ID = UUID("56ef16f5-19c0-5778-a429-2a71edf18de0")


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


async def seed_demo_auth() -> None:
    (
        filled_manager_login_id,
        filled_member_login_id,
        filled_member2_login_id,
        empty_manager_login_id,
        empty_member_login_id,
        empty_member2_login_id,
    ) = (
        settings.demo_filled_manager_login_id.strip().lower(),
        settings.demo_filled_member_login_id.strip().lower(),
        settings.demo_filled_member2_login_id.strip().lower(),
        settings.demo_empty_manager_login_id.strip().lower(),
        settings.demo_empty_member_login_id.strip().lower(),
        settings.demo_empty_member2_login_id.strip().lower(),
    )
    login_ids = (
        filled_manager_login_id,
        filled_member_login_id,
        filled_member2_login_id,
        empty_manager_login_id,
        empty_member_login_id,
        empty_member2_login_id,
    )
    password = settings.demo_password.get_secret_value()

    if not all(login_ids) or not password:
        raise SystemExit("backend/.env의 DEMO_* 인증 값을 먼저 채워주세요.")
    if len(set(login_ids)) != len(login_ids):
        raise SystemExit("여섯 데모 계정의 로그인 ID는 서로 달라야 합니다.")
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

        for team_id, _name in teams:
            await seed_team_configuration(session, team_id)

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
                "id": FILLED_MEMBER2_ID,
                "team_id": FILLED_TEAM_ID,
                "login_id": filled_member2_login_id,
                "password_hash": password_hashes[2],
                "display_name": "이수민",
                "role_code": "member",
                "job_title": "영업 담당자",
            },
            {
                "id": EMPTY_MANAGER_ID,
                "team_id": EMPTY_TEAM_ID,
                "login_id": empty_manager_login_id,
                "password_hash": password_hashes[3],
                "display_name": "김서현",
                "role_code": "manager",
                "job_title": "영업팀장",
            },
            {
                "id": EMPTY_MEMBER_ID,
                "team_id": EMPTY_TEAM_ID,
                "login_id": empty_member_login_id,
                "password_hash": password_hashes[4],
                "display_name": "김지훈",
                "role_code": "member",
                "job_title": "영업 담당자",
            },
            {
                "id": EMPTY_MEMBER2_ID,
                "team_id": EMPTY_TEAM_ID,
                "login_id": empty_member2_login_id,
                "password_hash": password_hashes[5],
                "display_name": "이수민",
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

    print("개발 DB의 합성 팀 2개, 기본 설정과 로그인 계정 6개를 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_auth())
