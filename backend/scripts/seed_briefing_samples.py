"""teamo@naver.com의 브리핑 화면 테스트용 3×3 샘플 데이터.

고객·상품·딜은 같은 순번끼리 연결된다. UUID가 팀 ID와 고정 키에서 나오므로
재실행해도 이 스크립트가 만든 9개 데이터만 갱신한다.

    uv run python -m scripts.seed_briefing_samples [--dry-run]
"""

import argparse
import asyncio
from datetime import date
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_sessionmaker
from app.models.configuration import CustomerContactStatus, SalesDealType
from app.models.crm import CustomerCompany, CustomerContact, CustomerContactAssignee
from app.models.sales import Product, SalesDeal, SalesDealItem, SalesPipeline, SalesPipelineStage
from app.models.workspace import Member
from scripts.seed_demo_auth import seed_team_configuration

OWNER_EMAIL = "teamo@naver.com"
SEED_TAG = "briefing-test-202609"
SAMPLES = (
    ("01", "브리핑테스트 서울의원", "김브리", "SLV 브리핑 베이직", "초기 제품 검토"),
    ("02", "브리핑테스트 강남병원", "이테스트", "SLV 브리핑 프로", "데모 일정 협의"),
    ("03", "브리핑테스트 미래클리닉", "박샘플", "SLV 브리핑 케어", "도입 조건 검토"),
)


def seed_id(team_id: UUID, kind: str, key: str) -> UUID:
    return uuid5(team_id, f"{SEED_TAG}:{kind}:{key}")


async def upsert(session, model, values):
    statement = insert(model).values(**values)
    updates = {key: getattr(statement.excluded, key) for key in values if key != "id"}
    await session.execute(statement.on_conflict_do_update(index_elements=[model.id], set_=updates))


async def seed(*, dry_run: bool = False) -> None:
    async with get_sessionmaker()() as session:
        owner = (
            await session.execute(select(Member).where(Member.email == OWNER_EMAIL))
        ).scalar_one_or_none()
        if owner is None:
            raise SystemExit(f"{OWNER_EMAIL} 계정을 찾지 못했습니다.")
        team_id = owner.team_id
        # 신규 팀은 조회 코드가 쓰는 기본 파이프라인·상태값부터 필요하다.
        await seed_team_configuration(session, owner.team_id)

        pipeline = (
            await session.execute(
                select(SalesPipeline).where(
                    SalesPipeline.team_id == owner.team_id,
                    SalesPipeline.is_default.is_(True),
                    SalesPipeline.status_code == "published",
                )
            )
        ).scalar_one_or_none()
        if pipeline is None:
            raise SystemExit("기본 영업 파이프라인을 찾지 못했습니다.")
        stage = (
            await session.execute(
                select(SalesPipelineStage).where(
                    SalesPipelineStage.sales_pipeline_id == pipeline.id,
                    SalesPipelineStage.stage_code == "product_demo",
                )
            )
        ).scalar_one_or_none()
        deal_type_id = (
            await session.execute(
                select(SalesDealType.id).where(
                    SalesDealType.team_id == owner.team_id,
                    SalesDealType.code == "new_installation",
                    SalesDealType.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        contact_status_id = (
            await session.execute(
                select(CustomerContactStatus.id).where(
                    CustomerContactStatus.team_id == owner.team_id,
                    CustomerContactStatus.code == "proposal",
                    CustomerContactStatus.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if stage is None or deal_type_id is None or contact_status_id is None:
            raise SystemExit("브리핑 샘플에 필요한 팀 기본 설정을 찾지 못했습니다.")

        if dry_run:
            await session.rollback()
            print(f"{OWNER_EMAIL} / 팀 {team_id}: 고객 3, 상품 3, 영업 3을 연결합니다.")
            return

        for position, (key, company_name, contact_name, product_name, memo) in enumerate(
            SAMPLES, start=1
        ):
            company_id = seed_id(owner.team_id, "company", key)
            contact_id = seed_id(owner.team_id, "contact", key)
            product_id = seed_id(owner.team_id, "product", key)
            deal_id = seed_id(owner.team_id, "deal", key)
            unit_price = 1_000_000 * position

            await upsert(
                session,
                CustomerCompany,
                {"id": company_id, "team_id": owner.team_id, "name": company_name,
                 "region_code": "seoul", "business_no": f"99000000{position:02d}"},
            )
            await upsert(
                session,
                CustomerContact,
                {"id": contact_id, "company_id": company_id, "owner_member_id": owner.id,
                 "created_by_member_id": owner.id, "name": contact_name, "department": "영업기획",
                 "job_title": "담당자", "email": f"briefing{key}@demo.test", "phone": None,
                 "customer_contact_status_id": contact_status_id, "source_code": "referral",
                 "memo": "AI 브리핑 테스트용 샘플 고객", "visited": False, "deleted_at": None},
            )
            await session.execute(
                insert(CustomerContactAssignee)
                .values(customer_contact_id=contact_id, member_id=owner.id)
                .on_conflict_do_nothing()
            )
            await upsert(
                session,
                Product,
                {"id": product_id, "team_id": owner.team_id, "name": product_name, "active": True,
                 "category_code": "system", "unit_price": unit_price, "shelf_life_months": None,
                 "spec": "브리핑 테스트 전용", "memo": "샘플 제품", "image_storage_key": None},
            )
            await upsert(
                session,
                SalesDeal,
                {"id": deal_id, "team_id": owner.team_id, "deal_no": f"BRIEF-TEST-{key}",
                 "customer_company_id": company_id, "customer_contact_id": contact_id,
                 "owner_member_id": owner.id, "product_id": product_id,
                 "sales_pipeline_id": pipeline.id, "sales_pipeline_stage_id": stage.id,
                 "title": f"{company_name} {product_name} 도입",
                 "description": "AI 브리핑 화면 테스트용 영업 건",
                 "sales_deal_type_id": deal_type_id,
                 "deal_amount": unit_price, "opened_on": date.today(), "closed_on": None,
                 "quote_no": None, "quote_issued_on": None, "quote_valid_until": None,
                 "contract_no": None, "contract_signed_on": None, "quote_status_id": None,
                 "contract_status_id": None, "quote_amount": None, "contract_amount": None,
                 "quote_delivery_terms": None, "contract_ends_on": None,
                 "contract_payment_terms": None, "contract_late_interest_terms": None,
                 "warranty_terms": None, "expected_delivery_at": None, "memo": memo,
                 "quote_memo": None, "contract_memo": None, "order_memo": None,
                 "source_code": "briefing_test", "stage_position": position - 1,
                 "deleted_at": None},
            )
            await upsert(
                session,
                SalesDealItem,
                {"id": seed_id(owner.team_id, "deal-item", key), "sales_deal_id": deal_id,
                 "product_id": product_id, "quantity": 1, "unit_price": unit_price, "position": 0},
            )

        await session.commit()
        count = (
            await session.execute(
                select(SalesDeal.id).where(
                    SalesDeal.team_id == owner.team_id,
                    SalesDeal.deal_no.like("BRIEF-TEST-%"),
                    SalesDeal.deleted_at.is_(None),
                )
            )
        ).all()
        if len(count) != 3:
            raise RuntimeError(f"샘플 영업 건 검증 실패: {len(count)}건")
        print(f"{OWNER_EMAIL}에 고객 3명, 상품 3개, 연결된 영업 3건을 만들었습니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(seed(dry_run=args.dry_run))
