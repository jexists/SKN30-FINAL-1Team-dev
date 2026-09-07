"""공유 개발 DB의 SalesLuv 데모팀에 계약/일정관리 에이전트 API 테스트용
customer_company, customer_contact, sales_deal, activity 를 각 10건씩 넣는다.

seed_demo_auth.py 가 이미 만들어 둔 데모팀(team_id, 파이프라인, 단계, 딜 유형,
활동 분류)에 의존한다. deal_no 로 결정론적 id 를 만들어 반복 실행해도
중복 삽입되지 않는다. 지우는 로직은 없다 — 계속 남겨 두고 재사용한다.

회사마다 대표 담당자(가상 인물)를 하나씩 만들어 딜과 일정에 붙인다. 담당자가 없으면 계약관리
에이전트가 다음 미팅을 추천할 때 일정에 넣을 사람을 못 정해 AI 브리핑이 만들어지지 않는다.
이미 있는 딜·일정은 담당자와 고객사가 비어 있을 때만 채우고 나머지 값은 건드리지 않는다.

    uv run python -m scripts.seed_demo_contract_schedule
"""

import asyncio
from datetime import UTC, date, datetime
from hashlib import md5
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models.configuration import CustomerContactStatus
from app.models.crm import Activity, CustomerCompany, CustomerContact, CustomerContactAssignee
from app.models.sales import SalesDeal

TEAM_ID = UUID("6d0f1b76-6b1a-4b72-9ba3-1df477a62d78")
MANAGER_ID = UUID("21ab9c67-328f-40b3-a410-9158a86ce4f1")
MEMBER_ID = UUID("d13137f5-02b4-470a-b0ce-304d62688c0e")

PIPELINE_ID = UUID("6feb55b1-21eb-1ff4-3d2f-d4b09d5d66cd")

STAGE = {
    "needs_validation": UUID("446da7c6-52ce-1929-1244-1f94e946e827"),
    "product_demo": UUID("d257dbeb-2a3c-0bc7-c56d-e69f68e802b4"),
    "quote_sent": UUID("fbb0d7db-869d-a14b-caed-7c02d9eda8e1"),
    "contract_sent": UUID("d00f616b-0ee3-2e78-96ea-7e5e1ace2407"),
    "contract_review": UUID("e80660ad-f9a6-b925-e917-fe59bf2e2fe7"),
    "contract_completed": UUID("42cd72ff-5c9f-4283-e1a7-f472a3b2eecc"),
    "order_in_progress": UUID("3004cad0-05d9-fa54-b1ab-38e381327f4b"),
    "order_delivered": UUID("77689ce6-d335-4422-3ff4-002fd73bb252"),
    "closed_cancelled": UUID("8761c798-d4e5-f41e-2e8f-daf8ddefc6d5"),
}

DEAL_TYPE = {
    "new_installation": UUID("2616e91b-238d-204a-2639-e99a27780aeb"),
    "expansion": UUID("0d64305d-35d3-1410-7648-0623d3961e91"),
    "renewal": UUID("96b478a8-7f21-234e-bc2b-261368f37511"),
    "maintenance": UUID("60368b68-8c5e-85c9-dacb-f20dfbce104e"),
    "consumables_supply": UUID("f4875e4e-b259-26c6-f3a3-9ffa586047a1"),
}

ACTIVITY_CATEGORY = {
    "visit": UUID("771cb4cc-6ad6-c3d4-5566-4ae0f35c28e5"),
    "demo": UUID("1761d32f-c6f1-c3f5-0a2a-dec35eae5c5a"),
    "call": UUID("2d73e785-b7e1-d3f4-dd3b-2bc823ff73e5"),
    "delivery": UUID("d221c0bb-0b01-95ee-24c7-0a9db70796b9"),
}


def _id(natural_key: str) -> UUID:
    raw = f"{TEAM_ID}:seed_demo_contract_schedule:{natural_key}".encode()
    return UUID(md5(raw, usedforsecurity=False).hexdigest())


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


# 각 행이 계약관리/일정관리 에이전트가 볼 위험 신호나 브리핑 시나리오를 하나씩 대표한다.
DEALS = (
    {
        "key": "hanbit",
        "company": "한빛병원",
        "region_code": "seoul",
        "owner": MANAGER_ID,
        "stage": "contract_review",
        "deal_type": "renewal",
        "title": "한빛병원 정기 계약 갱신",
        "deal_amount": 45_000_000,
        "opened_on": "2026-06-01",
        "quote_issued_on": "2026-06-10",
        "quote_valid_until": "2026-07-01",
        "contract_no": "CT-2026-0001",
        "contract_signed_on": "2026-08-01",
        "contract_ends_on": "2026-09-05",
        "activity": ("visit", "2026-08-10T10:00:00+09:00", "2026-08-10T11:00:00+09:00"),
    },
    {
        "key": "seoul-jungang",
        "company": "서울중앙의료원",
        "region_code": "seoul",
        "owner": MEMBER_ID,
        "stage": "quote_sent",
        "deal_type": "new_installation",
        "title": "서울중앙의료원 신규 장비 도입 견적",
        "deal_amount": 30_000_000,
        "opened_on": "2026-07-01",
        "quote_issued_on": "2026-08-15",
        "quote_valid_until": "2026-09-01",
        "activity": ("demo", "2026-08-15T14:00:00+09:00", "2026-08-15T15:00:00+09:00"),
    },
    {
        "key": "mirae-surgery",
        "company": "미래외과의원",
        "region_code": "gyeonggi",
        "owner": MANAGER_ID,
        "stage": "needs_validation",
        "deal_type": "new_installation",
        "title": "미래외과의원 니즈 검증",
        "deal_amount": 12_000_000,
        "opened_on": "2026-05-01",
        "activity": ("call", "2026-07-01T09:30:00+09:00", "2026-07-01T09:50:00+09:00"),
    },
    {
        "key": "gangnam-union",
        "company": "강남연합병원",
        "region_code": "seoul",
        "owner": MEMBER_ID,
        "stage": "product_demo",
        "deal_type": "expansion",
        "title": "강남연합병원 증설 제품 시연",
        "deal_amount": 20_000_000,
        "opened_on": "2026-08-01",
        "activity": ("demo", "2026-08-20T13:00:00+09:00", "2026-08-20T14:00:00+09:00"),
    },
    {
        "key": "pureun-internal",
        "company": "푸른내과의원",
        "region_code": "incheon",
        "owner": MANAGER_ID,
        "stage": "contract_sent",
        "deal_type": "maintenance",
        "title": "푸른내과의원 유지보수 계약서 발송",
        "deal_amount": 15_000_000,
        "opened_on": "2026-07-15",
        "contract_no": "CT-2026-0002",
        "activity": ("visit", "2026-08-18T11:00:00+09:00", "2026-08-18T11:40:00+09:00"),
    },
    {
        "key": "donghae-first",
        "company": "동해제일병원",
        "region_code": "gangwon",
        "owner": MEMBER_ID,
        "stage": "contract_completed",
        "deal_type": "new_installation",
        "title": "동해제일병원 신규 도입 계약 완료",
        "deal_amount": 60_000_000,
        "opened_on": "2026-06-15",
        "contract_no": "CT-2026-0003",
        "contract_signed_on": "2026-08-10",
        "closed_on": "2026-08-10",
        "activity": ("visit", "2026-08-10T10:00:00+09:00", "2026-08-10T11:00:00+09:00"),
    },
    {
        "key": "saebom-ortho",
        "company": "새봄정형외과",
        "region_code": "busan",
        "owner": MANAGER_ID,
        "stage": "order_in_progress",
        "deal_type": "consumables_supply",
        "title": "새봄정형외과 소모품 발주 진행",
        "deal_amount": 25_000_000,
        "opened_on": "2026-08-05",
        "activity": ("delivery", "2026-08-28T09:00:00+09:00", "2026-08-28T10:00:00+09:00"),
    },
    {
        "key": "hangang-sungmo",
        "company": "한강성모의료원",
        "region_code": "seoul",
        "owner": MEMBER_ID,
        "stage": "order_delivered",
        "deal_type": "new_installation",
        "title": "한강성모의료원 장비 납품 완료",
        "deal_amount": 40_000_000,
        "opened_on": "2026-07-01",
        "closed_on": "2026-08-20",
        "activity": ("delivery", "2026-08-20T10:00:00+09:00", "2026-08-20T11:00:00+09:00"),
    },
    {
        "key": "yein-ent",
        "company": "예인이비인후과",
        "region_code": "daegu",
        "owner": MANAGER_ID,
        "stage": "closed_cancelled",
        "deal_type": "new_installation",
        "title": "예인이비인후과 도입 취소",
        "deal_amount": 8_000_000,
        "opened_on": "2026-07-01",
        "closed_on": "2026-08-05",
        "activity": ("call", "2026-07-20T15:00:00+09:00", "2026-07-20T15:20:00+09:00"),
    },
    {
        "key": "daehan-rehab",
        "company": "대한재활병원",
        "region_code": "seoul",
        "owner": MEMBER_ID,
        "stage": "needs_validation",
        "deal_type": "expansion",
        "title": "대한재활병원 증설 상담",
        "deal_amount": 18_000_000,
        "opened_on": "2026-08-24",
        "activity": ("visit", "2026-09-03T10:00:00+09:00", "2026-09-03T10:30:00+09:00"),
    },
)


# 회사마다 대표 담당자 한 명. 목업이라 이름·직함·번호가 모두 가상이다. 미팅 참석자를 여럿
# 두는 자리는 sales_deal_participant 이고, 여기 있는 사람은 "연락은 이 분께"에 해당한다.
CONTACTS = {
    "hanbit": ("정하윤", "구매팀장", "010-0000-0001"),
    "seoul-jungang": ("문서준", "의공팀장", "010-0000-0002"),
    "mirae-surgery": ("배소율", "원장", "010-0000-0003"),
    "gangnam-union": ("한지후", "총무과장", "010-0000-0004"),
    "pureun-internal": ("오다은", "실장", "010-0000-0005"),
    "donghae-first": ("신재윤", "구매담당", "010-0000-0006"),
    "saebom-ortho": ("윤채원", "행정실장", "010-0000-0007"),
    "hangang-sungmo": ("임도현", "의공기사", "010-0000-0008"),
    "yein-ent": ("강수아", "대표원장", "010-0000-0009"),
    "daehan-rehab": ("서민호", "재활치료실장", "010-0000-0010"),
}


async def seed(*, dry_run: bool = False) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session, session.begin():
        await _seed(session)
        if dry_run:
            await session.rollback()
            print("--dry-run 이므로 아무것도 저장하지 않았습니다.")
            return
    print(
        f"데모팀({TEAM_ID})에 customer_company/customer_contact/sales_deal/activity 를 "
        "각 10건 준비했습니다."
    )


async def _seed(session: AsyncSession) -> None:
    # 고객 상태 룩업은 팀마다 id 가 다르다. 데모팀 것을 한 번만 읽는다.
    new_status_id = await session.scalar(
        select(CustomerContactStatus.id).where(
            CustomerContactStatus.team_id == TEAM_ID,
            CustomerContactStatus.code == "new",
            CustomerContactStatus.deleted_at.is_(None),
        )
    )

    for position, row in enumerate(DEALS):
        company_id = _id(f"customer_company:{row['key']}")
        contact_id = _id(f"customer_contact:{row['key']}")
        deal_id = _id(f"sales_deal:{row['key']}")
        activity_id = _id(f"activity:{row['key']}")
        contact_name, contact_job_title, contact_phone = CONTACTS[row["key"]]

        await session.execute(
            insert(CustomerCompany)
            .values(
                id=company_id,
                team_id=TEAM_ID,
                name=row["company"],
                region_code=row["region_code"],
                business_no=None,
            )
            .on_conflict_do_nothing(index_elements=[CustomerCompany.id])
        )

        await session.execute(
            insert(CustomerContact)
            .values(
                id=contact_id,
                company_id=company_id,
                owner_member_id=row["owner"],
                created_by_member_id=row["owner"],
                name=contact_name,
                department=None,
                job_title=contact_job_title,
                email=None,
                phone=contact_phone,
                customer_contact_status_id=new_status_id,
                source_code=None,
                memo=None,
            )
            .on_conflict_do_nothing(index_elements=[CustomerContact.id])
        )

        # 대표 담당자도 담당자 목록에 함께 들어간다. 고객 조회 스코프가 이 표를 본다.
        await session.execute(
            insert(CustomerContactAssignee)
            .values(customer_contact_id=contact_id, member_id=row["owner"])
            .on_conflict_do_nothing(
                index_elements=[
                    CustomerContactAssignee.customer_contact_id,
                    CustomerContactAssignee.member_id,
                ]
            )
        )

        await session.execute(
            insert(SalesDeal)
            .values(
                id=deal_id,
                team_id=TEAM_ID,
                deal_no=f"DEMO-SEED-{position + 1:03d}",
                customer_company_id=company_id,
                customer_contact_id=contact_id,
                owner_member_id=row["owner"],
                product_id=None,
                sales_pipeline_id=PIPELINE_ID,
                sales_pipeline_stage_id=STAGE[row["stage"]],
                title=row["title"],
                description=None,
                sales_deal_type_id=DEAL_TYPE[row["deal_type"]],
                deal_amount=row["deal_amount"],
                opened_on=date.fromisoformat(row["opened_on"]),
                closed_on=date.fromisoformat(row["closed_on"]) if row.get("closed_on") else None,
                quote_no=None,
                quote_issued_on=(
                    date.fromisoformat(row["quote_issued_on"])
                    if row.get("quote_issued_on")
                    else None
                ),
                quote_valid_until=(
                    date.fromisoformat(row["quote_valid_until"])
                    if row.get("quote_valid_until")
                    else None
                ),
                contract_no=row.get("contract_no"),
                contract_signed_on=(
                    date.fromisoformat(row["contract_signed_on"])
                    if row.get("contract_signed_on")
                    else None
                ),
                contract_ends_on=(
                    date.fromisoformat(row["contract_ends_on"])
                    if row.get("contract_ends_on")
                    else None
                ),
                warranty_terms=None,
                expected_delivery_at=None,
                memo=None,
                stage_position=0,
                deleted_at=None,
            )
            # 이미 있는 행은 담당자가 비어 있을 때만 채우고 나머지는 그대로 둔다.
            .on_conflict_do_update(
                index_elements=[SalesDeal.id],
                set_={"customer_contact_id": contact_id},
                where=SalesDeal.customer_contact_id.is_(None),
            )
        )

        category, starts_at, ends_at = row["activity"]
        await session.execute(
            insert(Activity)
            .values(
                id=activity_id,
                team_id=TEAM_ID,
                owner_member_id=row["owner"],
                customer_contact_id=contact_id,
                customer_company_id=company_id,
                end_user_contact_id=None,
                activity_category_id=ACTIVITY_CATEGORY[category],
                title=f"{row['company']} {category}",
                starts_at=_dt(starts_at),
                ends_at=_dt(ends_at),
                all_day=False,
                due_at=None,
                location=row["company"],
                activity_action_tag_id=None,
                completed_at=(
                    _dt(ends_at) if _dt(starts_at) < datetime.now(UTC).astimezone() else None
                ),
                note=None,
                deleted_at=None,
                product_id=None,
                sales_deal_id=deal_id,
                purchase_order_id=None,
            )
            # 이미 있는 행은 비어 있는 칸만 채우고 나머지는 그대로 둔다. 담당자와 딜은
            # 각각 비어 있을 수 있어 coalesce 로 칸마다 따로 본다.
            .on_conflict_do_update(
                index_elements=[Activity.id],
                set_={
                    "customer_contact_id": func.coalesce(Activity.customer_contact_id, contact_id),
                    "sales_deal_id": func.coalesce(Activity.sales_deal_id, deal_id),
                },
            )
        )


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
