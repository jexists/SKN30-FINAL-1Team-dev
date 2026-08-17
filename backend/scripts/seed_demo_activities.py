"""filled 데모팀에만 고정 합성 상품과 일정 12건을 반복 가능하게 넣는다."""

import asyncio
from datetime import date, datetime, time, timedelta
from typing import NamedTuple
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_sessionmaker
from app.models.crm import Activity, CustomerCompany, CustomerContact
from app.models.sales import Product
from app.models.workspace import Member, Team
from scripts.seed_demo_auth import FILLED_MANAGER_ID, FILLED_TEAM_ID
from scripts.seed_demo_customers import (
    FILLED_TEAM_NAME,
    OWNER_IDS,
    company_id,
    contact_id,
)

REFERENCE_DATE = date(2026, 8, 17)
SEOUL = ZoneInfo("Asia/Seoul")

CATEGORY_CODES = {
    "visit": "visit",
    "demo": "demo",
    "edu": "education",
    "call": "call",
    "delivery": "delivery",
    "booth": "conference",
    "internal": "internal",
}

ACTION_TAG_CODES = {
    "첫 전화": "first_call",
    "미팅": "meeting",
    "데모 요청": "demo_requested",
    "데모 진행": "demo_in_progress",
    "데모 완료": "demo_completed",
    "견적완료": "quote_completed",
    "계약완료": "contract_completed",
    "제품교육": "product_training",
    "납품완료": "delivery_completed",
    "내부회의": "internal_meeting",
    "주간점검": "weekly_review",
    "월간점검": "monthly_review",
    "분기점검": "quarterly_review",
    "컨퍼런스": "conference",
    "OJT": "ojt",
}

PRODUCT_NAMES = ("CardioView X7", "SonoFlex Pro", "OrthoScan Mini")
ACTIVITY_OWNER_IDS = {**OWNER_IDS, "김서현": FILLED_MANAGER_ID}


class ActivitySeed(NamedTuple):
    mock_id: str
    day_offset: int
    start_time: time
    duration_minutes: int | None
    kind: str
    owner_name: str
    customer_contact_id: UUID | None
    product_name: str | None
    stage: str | None
    location: str
    title: str
    note: str
    completed: bool
    all_day: bool = False


ACTIVITY_SEEDS = (
    ActivitySeed(
        "a1",
        0,
        time(9, 30),
        40,
        "visit",
        "김지훈",
        contact_id("FM-CU-2026-0001"),
        "CardioView X7",
        "견적완료",
        "본관 3층 회의실",
        "CardioView X7 도입 후속 미팅",
        (
            "지난 방문에서 제기된 3년 유지보수 비용 이슈에 대응합니다. "
            "TCO 비교표와 경쟁사 대비 납기 자료를 지참하고, 4분기 예산 집행 가능 여부와 "
            "최종 승인권자를 확인하는 것이 이번 미팅의 목표입니다."
        ),
        True,
    ),
    ActivitySeed(
        "a2",
        0,
        time(11),
        30,
        "call",
        "이수민",
        contact_id("FM-CU-2026-0003"),
        "SonoFlex Pro",
        "견적완료",
        "전화",
        "견적 회신 지연 건 후속 통화",
        (
            "견적 전달 후 14일째 회신이 없습니다. 예산 보류 사유를 확인하고 "
            "데모 재일정을 제안합니다. 리스 옵션 안내 자료를 미리 준비하세요."
        ),
        False,
    ),
    ActivitySeed(
        "a3",
        0,
        time(14),
        60,
        "demo",
        "김지훈",
        contact_id("FM-CU-2026-0002"),
        "OrthoScan Mini",
        "데모 진행",
        "교육실",
        "프로브 3종 비교 시연",
        (
            "실사용 간호 인력 5명이 참관합니다. 소독 프로토콜과 프로브 교체 주기 질문이 "
            "예상됩니다. 데모 장비 반출 확인이 오전 중에 끝나야 합니다."
        ),
        False,
    ),
    ActivitySeed(
        "a4",
        0,
        time(16, 30),
        30,
        "internal",
        "김서현",
        None,
        None,
        "주간점검",
        "본사 회의실 B",
        "주간 파이프라인 점검",
        "8월 확정 매출 진척과 리스크 딜 2건을 공유합니다. 일일보고서 미작성 3건을 마감합니다.",
        False,
    ),
    ActivitySeed(
        "a5",
        -2,
        time(10),
        None,
        "booth",
        "김지훈",
        None,
        "CardioView X7",
        "컨퍼런스",
        "코엑스 C홀",
        "학술대회 부스 운영 1일차",
        "CardioView X7 실물 전시와 상담을 진행합니다. 리드 카드는 당일 저녁에 CRM으로 옮깁니다.",
        True,
        True,
    ),
    ActivitySeed(
        "a6",
        -2,
        time(16),
        50,
        "visit",
        "박도윤",
        contact_id("FM-CU-2026-0005"),
        "OrthoScan Mini",
        "미팅",
        "학회장 미팅룸",
        "학회 현장 구매 담당자 면담",
        (
            "학회 참석 중인 구매 담당자와 짧게 면담합니다. "
            "기존 시스템 연동 범위와 도입 승인 절차를 확인합니다."
        ),
        True,
    ),
    ActivitySeed(
        "a7",
        1,
        time(9),
        90,
        "delivery",
        "이수민",
        contact_id("FM-CU-2026-0003"),
        "SonoFlex Pro",
        "계약완료",
        "1층 처치실",
        "SonoFlex Pro 납품 입회",
        (
            "발주 FM-PO-2026-0021 건의 예상 입고일입니다. 설치 공간은 사전 확인을 "
            "마쳤습니다. 입회 후 초기 셋업과 사용 교육 일정을 함께 잡으세요."
        ),
        False,
    ),
    ActivitySeed(
        "a8",
        2,
        time(13, 30),
        60,
        "edu",
        "김지훈",
        contact_id("FM-CU-2026-0002"),
        "OrthoScan Mini",
        "제품교육",
        "교육실",
        "OrthoScan Mini 사용 교육 1회차",
        (
            "데모에서 나온 소독 프로토콜 질문을 교육 자료에 반영해 진행합니다. "
            "참석자 명단은 전날까지 확정합니다."
        ),
        False,
    ),
    ActivitySeed(
        "a9",
        6,
        time(11),
        45,
        "visit",
        "김지훈",
        None,
        "CardioView X7",
        "계약완료",
        "본관 2층",
        "CardioView X7 계약 조건 협의",
        "발주 FM-PO-2026-0020의 분할 납품 2차 일정과 계약 조건을 함께 정리합니다.",
        False,
    ),
    ActivitySeed(
        "a10",
        -6,
        time(14),
        40,
        "visit",
        "김지훈",
        contact_id("FM-CU-2026-0001"),
        "CardioView X7",
        "데모 완료",
        "본관 3층",
        "CardioView X7 제품 테스트",
        (
            "실사용 테스트를 진행했습니다. 화면 가독성은 긍정적이었고 "
            "유지보수 비용 설명 요청을 받았습니다."
        ),
        True,
    ),
    ActivitySeed(
        "a11",
        8,
        time(10, 30),
        40,
        "visit",
        "박도윤",
        contact_id("FM-CU-2026-0005"),
        "OrthoScan Mini",
        "데모 요청",
        "회의실",
        "OrthoScan Mini 본원 데모",
        (
            "학회 면담 후속으로 본원에서 데모를 진행합니다. "
            "보안 요구사항과 데이터 접근 권한을 확인하세요."
        ),
        False,
    ),
    ActivitySeed(
        "a12",
        0,
        time(17),
        40,
        "internal",
        "김지훈",
        None,
        None,
        None,
        "본사 회의실 B",
        "담당 고객 진척 공유",
        (
            "한빛대학교병원 견적 회신 일정과 서림메디컬센터 데모 결과를 팀장에게 "
            "공유합니다. 다음 주 방문 계획을 확정합니다."
        ),
        False,
    ),
)


def product_id(name: str) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"product:{name}")


def activity_id(mock_id: str) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"activity:{mock_id}")


def activity_row(seed: ActivitySeed) -> dict:
    starts_at = datetime.combine(
        REFERENCE_DATE + timedelta(days=seed.day_offset),
        seed.start_time,
        tzinfo=SEOUL,
    )
    ends_at = (
        starts_at + timedelta(minutes=seed.duration_minutes)
        if seed.duration_minutes is not None
        else None
    )
    return {
        "id": activity_id(seed.mock_id),
        "team_id": FILLED_TEAM_ID,
        "owner_member_id": ACTIVITY_OWNER_IDS[seed.owner_name],
        "customer_contact_id": seed.customer_contact_id,
        "end_user_contact_id": None,
        "activity_type": "task" if seed.kind == "internal" else "meeting",
        "category_code": CATEGORY_CODES[seed.kind],
        "title": seed.title,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "all_day": seed.all_day,
        "due_at": None,
        "location": seed.location,
        "action_tag": ACTION_TAG_CODES[seed.stage] if seed.stage else None,
        "completed_at": (ends_at or starts_at) if seed.completed else None,
        "note": seed.note,
        "deleted_at": None,
        "product_id": product_id(seed.product_name) if seed.product_name else None,
        "contract_id": None,
        "order_id": None,
    }


async def seed_demo_activities() -> None:
    products = {product_id(name): name for name in PRODUCT_NAMES}
    activities = tuple(activity_row(seed) for seed in ACTIVITY_SEEDS)
    expected_activity_ids = {row["id"] for row in activities}
    expected_members = {
        ACTIVITY_OWNER_IDS[seed.owner_name]: (
            seed.owner_name,
            "manager" if seed.owner_name == "김서현" else "member",
        )
        for seed in ACTIVITY_SEEDS
    }
    expected_contacts = {
        contact_id("FM-CU-2026-0001"): (
            company_id("한빛대학교병원"),
            OWNER_IDS["김지훈"],
        ),
        contact_id("FM-CU-2026-0002"): (
            company_id("서림메디컬센터"),
            OWNER_IDS["김지훈"],
        ),
        contact_id("FM-CU-2026-0003"): (
            company_id("새봄정형외과"),
            OWNER_IDS["이수민"],
        ),
        contact_id("FM-CU-2026-0005"): (
            company_id("정우병원"),
            OWNER_IDS["박도윤"],
        ),
    }

    async with get_sessionmaker()() as session, session.begin():
        filled_team_name = (
            await session.execute(
                select(Team.name).where(Team.id == FILLED_TEAM_ID).with_for_update()
            )
        ).scalar_one_or_none()
        if filled_team_name != FILLED_TEAM_NAME:
            raise SystemExit("filled 인증 seed를 먼저 실행하세요.")

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
            raise SystemExit("인증과 고객 seed를 먼저 실행해 일정 담당자를 준비하세요.")
        for row in existing_members:
            display_name, role_code = expected_members[row.id]
            if (
                row.team_id != FILLED_TEAM_ID
                or row.display_name != display_name
                or row.role_code != role_code
                or not row.active
            ):
                raise SystemExit("합성 일정 담당자 ID, 팀, 이름 또는 역할이 충돌합니다.")

        existing_contacts = (
            await session.execute(
                select(
                    CustomerContact.id,
                    CustomerContact.company_id,
                    CustomerContact.owner_member_id,
                    CustomerCompany.team_id,
                )
                .join(CustomerCompany, CustomerContact.company_id == CustomerCompany.id)
                .where(CustomerContact.id.in_(expected_contacts))
                .with_for_update()
            )
        ).all()
        if {row.id for row in existing_contacts} != set(expected_contacts):
            raise SystemExit("고객 seed를 먼저 실행해 일정 고객 담당자를 준비하세요.")
        for row in existing_contacts:
            company_id_, owner_id = expected_contacts[row.id]
            if (
                row.team_id != FILLED_TEAM_ID
                or row.company_id != company_id_
                or row.owner_member_id != owner_id
            ):
                raise SystemExit("합성 일정 고객 담당자 ID, 고객사, owner 또는 팀이 충돌합니다.")

        existing_products = (
            await session.execute(
                select(Product.id, Product.team_id, Product.name)
                .where(
                    or_(
                        Product.id.in_(products),
                        and_(
                            Product.team_id == FILLED_TEAM_ID,
                            Product.name.in_(PRODUCT_NAMES),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        expected_product_ids = {name: id_ for id_, name in products.items()}
        for row in existing_products:
            if (
                products.get(row.id) != row.name
                or expected_product_ids.get(row.name) != row.id
                or row.team_id != FILLED_TEAM_ID
            ):
                raise SystemExit("합성 상품 ID, 이름 또는 팀이 충돌합니다.")

        existing_activities = (
            await session.execute(
                select(Activity.id, Activity.team_id)
                .where(Activity.id.in_(expected_activity_ids))
                .with_for_update()
            )
        ).all()
        if any(row.team_id != FILLED_TEAM_ID for row in existing_activities):
            raise SystemExit("합성 일정 ID 또는 팀이 충돌합니다.")

        for id_, name in products.items():
            product_insert = insert(Product).values(
                id=id_,
                team_id=FILLED_TEAM_ID,
                name=name,
                active=True,
            )
            upserted_id = (
                await session.execute(
                    product_insert.on_conflict_do_update(
                        index_elements=[Product.id],
                        set_={"active": product_insert.excluded.active},
                        where=and_(
                            Product.team_id == FILLED_TEAM_ID,
                            Product.name == name,
                        ),
                    ).returning(Product.id)
                )
            ).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 상품 ID, 이름 또는 팀이 충돌합니다.")

        for row in activities:
            activity_insert = insert(Activity).values(**row)
            update_fields = {
                key: getattr(activity_insert.excluded, key)
                for key in row
                if key not in {"id", "team_id"}
            }
            upserted_id = (
                await session.execute(
                    activity_insert.on_conflict_do_update(
                        index_elements=[Activity.id],
                        set_=update_fields,
                        where=Activity.team_id == FILLED_TEAM_ID,
                    ).returning(Activity.id)
                )
            ).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 일정 ID 또는 팀이 충돌합니다.")

    print("개발 DB의 filled 합성 팀에 상품 3개와 일정 12건을 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_activities())
