"""팀 하나가 쓸 기본 룩업과 기본 영업 파이프라인을 넣는다.

어드민 계정 발급과 seed 스크립트가 같은 함수를 쓴다. 팀 행만 만들고 여기를
건너뛰면 그 팀은 고객·활동·견적·계약 어느 화면도 코드 값을 찾지 못한다.

id 는 `md5("<네임스페이스>:<테이블>:<자연키>")` 로 정해 두어 어느 경로로 몇 번을
넣어도 같은 행을 가리킨다. 모든 INSERT 는 on_conflict_do_nothing 이라 반복 실행이
안전하고, 팀이 직접 바꾼 값은 덮어쓰지 않는다.
"""

from datetime import UTC, datetime
from hashlib import md5
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import (
    ActivityActionTag,
    ActivityCategory,
    ContractStatus,
    CustomerContactStatus,
    PurchaseOrderStatus,
    QuoteStatus,
    SalesDealType,
)
from app.models.sales import SalesPipeline, SalesPipelineStage


class ConfigurationConflict(RuntimeError):
    """기본값과 어긋나는 기존 행을 만났다. 덮어쓰지 않고 멈춘다."""


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
            ("code", "name", "tone", "position"),
            (
                ("visit", "방문", "blue", 0),
                ("demo", "데모", "purple", 1),
                ("education", "교육", "green", 2),
                ("call", "전화", "gray", 3),
                ("delivery", "납품", "orange", 4),
                ("conference", "컨퍼런스", "purple", 5),
            ),
        ),
    ),
    (
        ActivityActionTag,
        "activity_action_tag",
        rows(
            ("code", "name", "tone", "position"),
            (
                ("first_call", "첫 전화", "gray", 0),
                ("meeting", "미팅", "blue", 1),
                ("demo_requested", "데모 요청", "blue", 2),
                ("demo_in_progress", "데모 진행", "purple", 3),
                ("demo_completed", "데모 완료", "green", 4),
                ("quote_completed", "견적완료", "purple", 5),
                ("contract_completed", "계약완료", "green", 6),
                ("product_training", "제품교육", "blue", 7),
                ("delivery_completed", "납품완료", "green", 8),
                ("internal_meeting", "내부회의", "gray", 9),
                ("conference", "컨퍼런스", "purple", 10),
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
                ("cancelled", "발주취소", "red", 5, "cancelled"),
            ),
        ),
    ),
    (
        QuoteStatus,
        "quote_status",
        rows(
            ("code", "name", "tone", "position", "outcome_code"),
            (
                ("drafting", "견적작성", "gray", 0, "in_progress"),
                ("reviewing", "견적검토", "blue", 1, "in_progress"),
                ("sent", "고객발송", "purple", 2, "in_progress"),
                ("negotiating", "조건협의", "orange", 3, "in_progress"),
                ("completed", "견적완료", "green", 4, "completed"),
            ),
        ),
    ),
    (
        ContractStatus,
        "contract_status",
        rows(
            ("code", "name", "tone", "position", "outcome_code"),
            (
                ("drafting", "초안작성", "gray", 0, "in_progress"),
                ("reviewing", "계약검토", "blue", 1, "in_progress"),
                ("negotiating", "고객협의", "orange", 2, "in_progress"),
                ("signed", "고객서명", "purple", 3, "in_progress"),
                ("completed", "계약완료", "green", 4, "completed"),
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
                raise ConfigurationConflict(f"{table_name} 기본값의 ID, 팀 또는 code가 충돌합니다.")
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
            raise ConfigurationConflict("기본 영업 파이프라인의 ID, 이름 또는 기본값이 충돌합니다.")
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
            raise ConfigurationConflict(
                "기존 기본 영업 파이프라인은 seed 값과 다르므로 덮어쓰지 않습니다."
            )
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
            raise ConfigurationConflict(
                "기본 영업 단계의 ID, pipeline 또는 고정 정의가 충돌합니다."
            )
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
