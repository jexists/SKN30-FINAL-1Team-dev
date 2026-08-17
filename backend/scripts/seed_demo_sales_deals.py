"""filled 데모팀의 기본 파이프라인에 합성 딜 61건을 반복 가능하게 넣는다."""

import asyncio
from datetime import timedelta
from typing import NamedTuple
from uuid import UUID, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_sessionmaker
from app.models.configuration import SalesDealType
from app.models.crm import CustomerCompany
from app.models.sales import Product, SalesDeal, SalesPipeline, SalesPipelineStage
from app.models.workspace import Member, Team
from scripts.seed_demo_activities import PRODUCT_NAMES, REFERENCE_DATE, product_id
from scripts.seed_demo_auth import FILLED_TEAM_ID
from scripts.seed_demo_customers import FILLED_TEAM_NAME, OWNER_IDS, company_id


class SalesDealSeed(NamedTuple):
    deal_no: str
    company_name: str
    product_name: str
    deal_amount: int
    deal_type_code: str
    day_offset: int
    owner_name: str
    sales_pipeline_stage_key: str
    stage_position: int


STAGE_CODE_BY_KEY = {
    "needs": "needs_validation",
    "demo": "product_demo",
    "quote": "quote_sent",
    "sent": "contract_sent",
    "reviewing": "contract_review",
    "won": "contract_completed",
    "order_in_progress": "order_in_progress",
    "delivered": "order_delivered",
    "lost": "closed_cancelled",
}

# 프론트 딜 111건 중 현재 product seed 3종에 정확히 연결되는 61건만 옮긴다.
# stage_position은 제외된 50건을 포함한 기존 영업 보드의 순서를 그대로 보존한다.
SALES_DEAL_SEEDS = (
    SalesDealSeed(
        "FM-CT-2026-0039",
        "정우병원",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        0,
        "박도윤",
        "needs",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0059",
        "한빛대학교병원",
        "CardioView X7",
        48_000_000,
        "expansion",
        -1,
        "김지훈",
        "needs",
        1,
    ),
    SalesDealSeed(
        "FM-CT-2026-0058",
        "미래아동병원",
        "SonoFlex Pro",
        92_000_000,
        "new_installation",
        -2,
        "최가은",
        "needs",
        2,
    ),
    SalesDealSeed(
        "FM-CT-2026-0037",
        "한빛대학교병원",
        "SonoFlex Pro",
        98_000_000,
        "expansion",
        -3,
        "김지훈",
        "won",
        1,
    ),
    SalesDealSeed(
        "FM-CT-2026-0055",
        "서림메디컬센터",
        "OrthoScan Mini",
        34_400_000,
        "expansion",
        -8,
        "김지훈",
        "demo",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0054",
        "새봄정형외과",
        "OrthoScan Mini",
        25_800_000,
        "new_installation",
        -11,
        "이수민",
        "demo",
        1,
    ),
    SalesDealSeed(
        "FM-CT-2026-0051",
        "도담재활병원",
        "CardioView X7",
        24_000_000,
        "new_installation",
        -18,
        "박도윤",
        "quote",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0050",
        "정우병원",
        "SonoFlex Pro",
        98_000_000,
        "expansion",
        -21,
        "박도윤",
        "quote",
        1,
    ),
    SalesDealSeed(
        "FM-CT-2026-0032",
        "한빛대학교병원",
        "OrthoScan Mini",
        98_000_000,
        "new_installation",
        -21,
        "김지훈",
        "won",
        6,
    ),
    SalesDealSeed(
        "FM-CT-2026-0047",
        "한빛대학교병원",
        "OrthoScan Mini",
        43_000_000,
        "expansion",
        -30,
        "김지훈",
        "sent",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0030",
        "새봄정형외과",
        "CardioView X7",
        50_600_000,
        "expansion",
        -32,
        "이수민",
        "won",
        7,
    ),
    SalesDealSeed(
        "FM-CT-2026-0046",
        "미래아동병원",
        "CardioView X7",
        24_000_000,
        "new_installation",
        -33,
        "최가은",
        "sent",
        1,
    ),
    SalesDealSeed(
        "FM-CT-2026-0029",
        "미래아동병원",
        "CardioView X7",
        60_500_000,
        "new_installation",
        -38,
        "이수민",
        "won",
        8,
    ),
    SalesDealSeed(
        "FM-CT-2026-0044",
        "정우병원",
        "OrthoScan Mini",
        17_200_000,
        "consumables_supply",
        -39,
        "이수민",
        "sent",
        3,
    ),
    SalesDealSeed(
        "FM-CT-2026-0043",
        "서림메디컬센터",
        "SonoFlex Pro",
        88_000_000,
        "new_installation",
        -42,
        "김지훈",
        "reviewing",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0028",
        "도담재활병원",
        "CardioView X7",
        41_800_000,
        "new_installation",
        -46,
        "최가은",
        "won",
        9,
    ),
    SalesDealSeed(
        "FM-CT-2026-0027",
        "서림메디컬센터",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -51,
        "김지훈",
        "won",
        10,
    ),
    SalesDealSeed(
        "FM-CT-2026-0040",
        "도담재활병원",
        "OrthoScan Mini",
        21_500_000,
        "expansion",
        -52,
        "박도윤",
        "reviewing",
        3,
    ),
    SalesDealSeed(
        "FM-CT-2026-0026",
        "미래아동병원",
        "SonoFlex Pro",
        21_100_000,
        "expansion",
        -56,
        "이수민",
        "won",
        11,
    ),
    SalesDealSeed(
        "FM-CT-2026-0024",
        "새봄정형외과",
        "OrthoScan Mini",
        34_500_000,
        "new_installation",
        -68,
        "이수민",
        "won",
        13,
    ),
    SalesDealSeed(
        "FM-CT-2026-0022",
        "도담재활병원",
        "SonoFlex Pro",
        14_500_000,
        "expansion",
        -80,
        "최가은",
        "won",
        15,
    ),
    SalesDealSeed(
        "FM-CT-2026-0021",
        "한빛대학교병원",
        "SonoFlex Pro",
        52_700_000,
        "expansion",
        -86,
        "김지훈",
        "lost",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0020",
        "한빛대학교병원",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -93,
        "김지훈",
        "order_in_progress",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0019",
        "서림메디컬센터",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -98,
        "김지훈",
        "won",
        17,
    ),
    SalesDealSeed(
        "FM-CT-2026-0015",
        "한빛대학교병원",
        "OrthoScan Mini",
        98_000_000,
        "new_installation",
        -124,
        "김지훈",
        "won",
        20,
    ),
    SalesDealSeed(
        "FM-CT-2026-0013",
        "서림메디컬센터",
        "OrthoScan Mini",
        60_900_000,
        "new_installation",
        -135,
        "김지훈",
        "delivered",
        0,
    ),
    SalesDealSeed(
        "FM-CT-2026-0011",
        "미래아동병원",
        "CardioView X7",
        29_200_000,
        "expansion",
        -149,
        "이수민",
        "won",
        23,
    ),
    SalesDealSeed(
        "FM-CT-2026-0010",
        "서림메디컬센터",
        "CardioView X7",
        79_900_000,
        "expansion",
        -155,
        "김지훈",
        "won",
        24,
    ),
    SalesDealSeed(
        "FM-CT-2026-0009",
        "한빛대학교병원",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -160,
        "김지훈",
        "won",
        25,
    ),
    SalesDealSeed(
        "FM-CT-2026-0006",
        "한빛대학교병원",
        "OrthoScan Mini",
        98_000_000,
        "new_installation",
        -181,
        "김지훈",
        "won",
        28,
    ),
    SalesDealSeed(
        "FM-CT-2026-0005",
        "서림메디컬센터",
        "CardioView X7",
        86_400_000,
        "expansion",
        -187,
        "김지훈",
        "won",
        29,
    ),
    SalesDealSeed(
        "FM-CT-2026-0004",
        "서림메디컬센터",
        "CardioView X7",
        97_000_000,
        "expansion",
        -195,
        "김지훈",
        "won",
        30,
    ),
    SalesDealSeed(
        "FM-CT-2026-0002",
        "정우병원",
        "SonoFlex Pro",
        71_700_000,
        "new_installation",
        -212,
        "박도윤",
        "won",
        32,
    ),
    SalesDealSeed(
        "FM-CT-2026-0001",
        "새봄정형외과",
        "CardioView X7",
        78_700_000,
        "new_installation",
        -219,
        "이수민",
        "won",
        33,
    ),
    SalesDealSeed(
        "FM-CT-2025-0039",
        "서림메디컬센터",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -233,
        "김지훈",
        "won",
        35,
    ),
    SalesDealSeed(
        "FM-CT-2025-0038",
        "한빛대학교병원",
        "SonoFlex Pro",
        98_000_000,
        "expansion",
        -241,
        "김지훈",
        "won",
        36,
    ),
    SalesDealSeed(
        "FM-CT-2025-0035",
        "서림메디컬센터",
        "SonoFlex Pro",
        66_400_000,
        "expansion",
        -264,
        "김지훈",
        "won",
        39,
    ),
    SalesDealSeed(
        "FM-CT-2025-0034",
        "한빛대학교병원",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -272,
        "김지훈",
        "won",
        40,
    ),
    SalesDealSeed(
        "FM-CT-2025-0032",
        "한빛대학교병원",
        "OrthoScan Mini",
        98_000_000,
        "new_installation",
        -288,
        "김지훈",
        "won",
        42,
    ),
    SalesDealSeed(
        "FM-CT-2025-0029",
        "미래아동병원",
        "CardioView X7",
        31_600_000,
        "expansion",
        -310,
        "이수민",
        "won",
        45,
    ),
    SalesDealSeed(
        "FM-CT-2025-0026",
        "한빛대학교병원",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -333,
        "김지훈",
        "won",
        48,
    ),
    SalesDealSeed(
        "FM-CT-2025-0024",
        "새봄정형외과",
        "CardioView X7",
        98_000_000,
        "expansion",
        -349,
        "이수민",
        "won",
        50,
    ),
    SalesDealSeed(
        "FM-CT-2025-0021",
        "새봄정형외과",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -380,
        "이수민",
        "won",
        53,
    ),
    SalesDealSeed(
        "FM-CT-2025-0020",
        "서림메디컬센터",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -391,
        "김지훈",
        "lost",
        2,
    ),
    SalesDealSeed(
        "FM-CT-2025-0017",
        "한빛대학교병원",
        "OrthoScan Mini",
        98_000_000,
        "new_installation",
        -420,
        "김지훈",
        "won",
        56,
    ),
    SalesDealSeed(
        "FM-CT-2025-0016",
        "서림메디컬센터",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -430,
        "김지훈",
        "won",
        57,
    ),
    SalesDealSeed(
        "FM-CT-2025-0015",
        "한빛대학교병원",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -442,
        "김지훈",
        "won",
        58,
    ),
    SalesDealSeed(
        "FM-CT-2025-0014",
        "한빛대학교병원",
        "SonoFlex Pro",
        69_400_000,
        "expansion",
        -452,
        "김지훈",
        "won",
        59,
    ),
    SalesDealSeed(
        "FM-CT-2025-0013",
        "새봄정형외과",
        "CardioView X7",
        69_900_000,
        "new_installation",
        -461,
        "이수민",
        "won",
        60,
    ),
    SalesDealSeed(
        "FM-CT-2025-0008",
        "한빛대학교병원",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -513,
        "김지훈",
        "won",
        65,
    ),
    SalesDealSeed(
        "FM-CT-2025-0004",
        "한빛대학교병원",
        "CardioView X7",
        98_000_000,
        "expansion",
        -550,
        "김지훈",
        "won",
        69,
    ),
    SalesDealSeed(
        "FM-CT-2024-0011",
        "한빛대학교병원",
        "OrthoScan Mini",
        98_000_000,
        "new_installation",
        -604,
        "김지훈",
        "won",
        74,
    ),
    SalesDealSeed(
        "FM-CT-2024-0010",
        "서림메디컬센터",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -614,
        "김지훈",
        "won",
        75,
    ),
    SalesDealSeed(
        "FM-CT-2024-0009",
        "정우병원",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -623,
        "박도윤",
        "won",
        76,
    ),
    SalesDealSeed(
        "FM-CT-2024-0008",
        "새봄정형외과",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -632,
        "이수민",
        "won",
        77,
    ),
    SalesDealSeed(
        "FM-CT-2024-0007",
        "미래아동병원",
        "CardioView X7",
        38_600_000,
        "expansion",
        -644,
        "이수민",
        "won",
        78,
    ),
    SalesDealSeed(
        "FM-CT-2024-0005",
        "정우병원",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -665,
        "박도윤",
        "won",
        80,
    ),
    SalesDealSeed(
        "FM-CT-2024-0004",
        "서림메디컬센터",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -675,
        "김지훈",
        "won",
        81,
    ),
    SalesDealSeed(
        "FM-CT-2024-0003",
        "한빛대학교병원",
        "CardioView X7",
        98_000_000,
        "new_installation",
        -685,
        "김지훈",
        "won",
        82,
    ),
    SalesDealSeed(
        "FM-CT-2024-0002",
        "서림메디컬센터",
        "SonoFlex Pro",
        98_000_000,
        "new_installation",
        -695,
        "김지훈",
        "won",
        83,
    ),
    SalesDealSeed(
        "FM-CT-2024-0001",
        "새봄정형외과",
        "OrthoScan Mini",
        36_300_000,
        "new_installation",
        -704,
        "이수민",
        "won",
        84,
    ),
)


def sales_deal_id(deal_no: str) -> UUID:
    # 기존 seed UUID를 보존해야 이미 저장된 딜과 같은 행을 갱신한다.
    return uuid5(FILLED_TEAM_ID, f"contract:{deal_no}")


def sales_deal_row(
    seed: SalesDealSeed,
    sales_pipeline_id: UUID,
    stage_ids_by_key: dict[str, UUID],
    deal_type_ids_by_code: dict[str, UUID],
) -> dict:
    opened_on = REFERENCE_DATE + timedelta(days=seed.day_offset)
    return {
        "id": sales_deal_id(seed.deal_no),
        "team_id": FILLED_TEAM_ID,
        "deal_no": seed.deal_no,
        "customer_company_id": company_id(seed.company_name),
        "customer_contact_id": None,
        "owner_member_id": OWNER_IDS[seed.owner_name],
        "product_id": product_id(seed.product_name),
        "sales_pipeline_id": sales_pipeline_id,
        "sales_pipeline_stage_id": stage_ids_by_key[seed.sales_pipeline_stage_key],
        "title": f"{seed.company_name} {seed.product_name}",
        "description": None,
        "sales_deal_type_id": deal_type_ids_by_code[seed.deal_type_code],
        "deal_amount": seed.deal_amount,
        "opened_on": opened_on,
        "closed_on": opened_on if seed.sales_pipeline_stage_key == "lost" else None,
        "quote_no": None,
        "quote_issued_on": None,
        "quote_valid_until": None,
        "contract_no": None,
        "contract_signed_on": (
            opened_on
            if seed.sales_pipeline_stage_key in {"won", "order_in_progress", "delivered"}
            else None
        ),
        "contract_ends_on": None,
        "warranty_terms": None,
        "expected_delivery_at": None,
        "memo": None,
        "stage_position": seed.stage_position,
        "deleted_at": None,
    }


def sales_deal_upsert(row: dict):
    sales_deal_insert = insert(SalesDeal).values(**row)
    update_fields = {
        key: getattr(sales_deal_insert.excluded, key)
        for key in row
        if key not in {"id", "team_id", "deal_no"}
    }
    return sales_deal_insert.on_conflict_do_update(
        index_elements=[SalesDeal.id],
        set_=update_fields,
        where=and_(
            SalesDeal.team_id == FILLED_TEAM_ID,
            SalesDeal.deal_no == row["deal_no"],
        ),
    ).returning(SalesDeal.id)


async def seed_demo_sales_deals() -> None:
    expected_members = {
        OWNER_IDS[name]: name for name in {seed.owner_name for seed in SALES_DEAL_SEEDS}
    }
    expected_companies = {
        company_id(name): name for name in {seed.company_name for seed in SALES_DEAL_SEEDS}
    }
    expected_products = {product_id(name): name for name in PRODUCT_NAMES}
    expected_deal_type_codes = {seed.deal_type_code for seed in SALES_DEAL_SEEDS}

    async with get_sessionmaker()() as session, session.begin():
        filled_team_name = (
            await session.execute(
                select(Team.name).where(Team.id == FILLED_TEAM_ID).with_for_update()
            )
        ).scalar_one_or_none()
        if filled_team_name != FILLED_TEAM_NAME:
            raise SystemExit("filled 인증 seed를 먼저 실행하세요.")

        pipeline = (
            await session.execute(
                select(SalesPipeline)
                .where(
                    SalesPipeline.team_id == FILLED_TEAM_ID,
                    SalesPipeline.status_code == "published",
                    SalesPipeline.is_default.is_(True),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if pipeline is None:
            raise SystemExit("filled 인증 seed를 먼저 실행해 기본 파이프라인을 준비하세요.")

        stage_rows = (
            await session.execute(
                select(
                    SalesPipelineStage.id,
                    SalesPipelineStage.stage_code,
                    SalesPipelineStage.phase_code,
                    SalesPipelineStage.outcome_code,
                )
                .where(SalesPipelineStage.sales_pipeline_id == pipeline.id)
                .with_for_update()
            )
        ).all()
        stages_by_code = {row.stage_code: row for row in stage_rows}
        if set(stages_by_code) != set(STAGE_CODE_BY_KEY.values()):
            raise SystemExit("기본 파이프라인의 9개 영업 단계를 확인하세요.")
        stage_ids_by_key = {
            key: stages_by_code[stage_code].id for key, stage_code in STAGE_CODE_BY_KEY.items()
        }

        deal_type_rows = (
            await session.execute(
                select(SalesDealType.id, SalesDealType.code)
                .where(
                    SalesDealType.team_id == FILLED_TEAM_ID,
                    SalesDealType.code.in_(expected_deal_type_codes),
                    SalesDealType.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).all()
        deal_type_ids_by_code = {row.code: row.id for row in deal_type_rows}
        if set(deal_type_ids_by_code) != expected_deal_type_codes:
            raise SystemExit("filled 인증 seed를 먼저 실행해 딜 유형을 준비하세요.")

        sales_deals = tuple(
            sales_deal_row(
                seed,
                pipeline.id,
                stage_ids_by_key,
                deal_type_ids_by_code,
            )
            for seed in SALES_DEAL_SEEDS
        )
        expected_sales_deals = {row["id"]: row for row in sales_deals}
        expected_sales_deal_ids_by_no = {row["deal_no"]: row["id"] for row in sales_deals}

        existing_members = (
            await session.execute(
                select(
                    Member.id,
                    Member.team_id,
                    Member.display_name,
                    Member.role_code,
                    Member.active,
                )
                .where(Member.id.in_(expected_members))
                .with_for_update()
            )
        ).all()
        if {row.id for row in existing_members} != set(expected_members):
            raise SystemExit("고객 seed를 먼저 실행해 딜 담당자를 준비하세요.")
        for row in existing_members:
            if (
                row.team_id != FILLED_TEAM_ID
                or row.display_name != expected_members[row.id]
                or row.role_code != "member"
                or not row.active
            ):
                raise SystemExit("합성 딜 담당자 ID, 팀, 이름 또는 역할이 충돌합니다.")

        existing_companies = (
            await session.execute(
                select(CustomerCompany.id, CustomerCompany.team_id, CustomerCompany.name)
                .where(
                    or_(
                        CustomerCompany.id.in_(expected_companies),
                        and_(
                            CustomerCompany.team_id == FILLED_TEAM_ID,
                            CustomerCompany.name.in_(expected_companies.values()),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        expected_company_ids_by_name = {name: id_ for id_, name in expected_companies.items()}
        for row in existing_companies:
            if (
                row.team_id != FILLED_TEAM_ID
                or expected_companies.get(row.id) != row.name
                or expected_company_ids_by_name.get(row.name) != row.id
            ):
                raise SystemExit("합성 계약 고객사 ID, 이름 또는 팀이 충돌합니다.")
        if {row.id for row in existing_companies} != set(expected_companies):
            raise SystemExit("고객 seed를 먼저 실행해 딜 고객사를 준비하세요.")

        existing_products = (
            await session.execute(
                select(Product.id, Product.team_id, Product.name, Product.active)
                .where(
                    or_(
                        Product.id.in_(expected_products),
                        and_(
                            Product.team_id == FILLED_TEAM_ID,
                            Product.name.in_(PRODUCT_NAMES),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        expected_product_ids_by_name = {name: id_ for id_, name in expected_products.items()}
        for row in existing_products:
            if (
                row.team_id != FILLED_TEAM_ID
                or expected_products.get(row.id) != row.name
                or expected_product_ids_by_name.get(row.name) != row.id
                or not row.active
            ):
                raise SystemExit("합성 계약 상품 ID, 이름, 팀 또는 상태가 충돌합니다.")
        if {row.id for row in existing_products} != set(expected_products):
            raise SystemExit("일정 seed를 먼저 실행해 계약 상품을 준비하세요.")

        existing_sales_deals = (
            await session.execute(
                select(SalesDeal.id, SalesDeal.team_id, SalesDeal.deal_no)
                .where(
                    or_(
                        SalesDeal.id.in_(expected_sales_deals),
                        and_(
                            SalesDeal.team_id == FILLED_TEAM_ID,
                            SalesDeal.deal_no.in_(expected_sales_deal_ids_by_no),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        for row in existing_sales_deals:
            expected = expected_sales_deals.get(row.id)
            if (
                expected is None
                or row.team_id != FILLED_TEAM_ID
                or expected["deal_no"] != row.deal_no
                or expected_sales_deal_ids_by_no.get(row.deal_no) != row.id
            ):
                raise SystemExit("합성 딜 ID, 딜 번호 또는 팀이 충돌합니다.")

        for row in sales_deals:
            upserted_id = (await session.execute(sales_deal_upsert(row))).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 딜 ID, 딜 번호 또는 팀이 충돌합니다.")

    print("개발 DB의 filled 합성 팀 기본 파이프라인에 딜 61건을 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_sales_deals())
