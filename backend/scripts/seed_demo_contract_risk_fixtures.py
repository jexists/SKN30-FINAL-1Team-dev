"""filled 데모팀 계약 일부에 ends_on·expected_delivery_at을 채워 위험 탐지를 시연 가능하게 한다."""

import asyncio
from datetime import datetime, time, timedelta

from sqlalchemy import update

from app.db.session import get_sessionmaker
from app.models.sales import Contract
from scripts.seed_demo_activities import REFERENCE_DATE, SEOUL
from scripts.seed_demo_auth import FILLED_TEAM_ID
from scripts.seed_demo_contracts import contract_id

# 만료 임박 위험 시연용. day_offset은 REFERENCE_DATE(2026-08-17) 기준 며칠 뒤가
# 만료일인지를 뜻한다. 2건은 30일 이내, 2건은 60일 이내, 나머지 4건은 90일
# 이내에 걸리게 잡았다. 전부 outcome_code가 confirmed인 계약(won·delivered)이다.
ENDS_ON_FIXTURES = {
    "FM-CT-2026-0037": 15,
    "FM-CT-2026-0032": 25,
    "FM-CT-2026-0030": 40,
    "FM-CT-2026-0029": 55,
    "FM-CT-2026-0028": 65,
    "FM-CT-2026-0027": 75,
    "FM-CT-2026-0026": 85,
    "FM-CT-2026-0013": 88,
}

# 납품 지연·임박 위험 시연용. 음수는 이미 지난 납품 예정일, 양수는 앞으로 남은
# 날짜다. 전부 stage_key가 sent 또는 reviewing인 계약이다.
EXPECTED_DELIVERY_FIXTURES = {
    "FM-CT-2026-0047": -5,
    "FM-CT-2026-0043": -2,
    "FM-CT-2026-0046": 3,
    "FM-CT-2026-0040": 6,
}


async def seed_demo_contract_risk_fixtures() -> None:
    async with get_sessionmaker()() as session, session.begin():
        updated_ends_on = 0
        for contract_no, day_offset in ENDS_ON_FIXTURES.items():
            result = await session.execute(
                update(Contract)
                .where(
                    Contract.id == contract_id(contract_no),
                    Contract.team_id == FILLED_TEAM_ID,
                )
                .values(ends_on=REFERENCE_DATE + timedelta(days=day_offset))
            )
            updated_ends_on += result.rowcount

        updated_delivery = 0
        for contract_no, day_offset in EXPECTED_DELIVERY_FIXTURES.items():
            result = await session.execute(
                update(Contract)
                .where(
                    Contract.id == contract_id(contract_no),
                    Contract.team_id == FILLED_TEAM_ID,
                )
                .values(
                    expected_delivery_at=datetime.combine(
                        REFERENCE_DATE + timedelta(days=day_offset),
                        time(9, 0),
                        tzinfo=SEOUL,
                    )
                )
            )
            updated_delivery += result.rowcount

        if updated_ends_on != len(ENDS_ON_FIXTURES):
            raise SystemExit(
                f"ends_on 업데이트 {updated_ends_on}/{len(ENDS_ON_FIXTURES)}건만 "
                "반영됐습니다. 계약 seed를 먼저 실행하세요."
            )
        if updated_delivery != len(EXPECTED_DELIVERY_FIXTURES):
            raise SystemExit(
                f"expected_delivery_at 업데이트 {updated_delivery}/"
                f"{len(EXPECTED_DELIVERY_FIXTURES)}건만 반영됐습니다. "
                "계약 seed를 먼저 실행하세요."
            )

    print(
        f"계약 위험 시연용 픽스처를 채웠습니다: ends_on {updated_ends_on}건, "
        f"expected_delivery_at {updated_delivery}건."
    )


if __name__ == "__main__":
    asyncio.run(seed_demo_contract_risk_fixtures())
