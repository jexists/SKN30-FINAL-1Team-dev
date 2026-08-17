"""filled 데모팀에만 관계가 정확한 합성 C/S 요청 3건을 반복 가능하게 넣는다."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_sessionmaker
from app.models.crm import CustomerCompany, CustomerContact, SupportRequest
from app.models.workspace import Member, Team
from scripts.seed_demo_auth import FILLED_TEAM_ID
from scripts.seed_demo_customers import FILLED_TEAM_NAME, OWNER_IDS, company_id, contact_id

REFERENCE_AT = datetime(2026, 8, 17, tzinfo=UTC)

STATUS_CODES = {
    "처리중": "in_progress",
    "처리완료": "completed",
}


class SupportRequestSeed(NamedTuple):
    mock_id: str
    contact_mock_id: str
    company_name: str
    contact_name: str
    department: str
    assignee_name: str
    title: str
    body: str
    is_urgent: bool
    status: str
    registered_day_offset: int


# 프론트 C/S 4건 중 현재 고객사·접수자·담당자가 모두 정확한 3건만 옮긴다.
SUPPORT_REQUEST_SEEDS = (
    SupportRequestSeed(
        "cs-1",
        "FM-CU-2026-0001",
        "한빛대학교병원",
        "박서준",
        "순환기내과",
        "김지훈",
        "부팅 시 화면 깜빡임",
        "진료 중 재현되어 사용을 중단한 상태입니다. 기술지원팀 배정이 필요합니다.",
        True,
        "처리중",
        0,
    ),
    SupportRequestSeed(
        "cs-2",
        "FM-CU-2026-0002",
        "서림메디컬센터",
        "윤가영",
        "영상의학과",
        "김지훈",
        "프로브 케이블 접촉 불량",
        "프로브 3종 중 1종에서만 발생합니다. 교체용 케이블 재고를 확인하세요.",
        False,
        "처리중",
        -1,
    ),
    SupportRequestSeed(
        "cs-3",
        "FM-CU-2026-0003",
        "새봄정형외과",
        "오정민",
        "원무팀",
        "이수민",
        "젤 워머 온도 편차",
        "기술지원팀이 원격 점검 중입니다. 결과 회신 예정입니다.",
        False,
        "처리중",
        -2,
    ),
)

# 프론트 mock은 note 전체를 요청 내용으로 사용하고 별도 대응 이력을 갖고 있지 않다.
SUPPORT_RESPONSE_SEEDS: tuple[()] = ()


def support_request_id(mock_id: str) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"support-request:{mock_id}")


def support_request_row(seed: SupportRequestSeed) -> dict:
    return {
        "id": support_request_id(seed.mock_id),
        "team_id": FILLED_TEAM_ID,
        "customer_contact_id": contact_id(seed.contact_mock_id),
        "assignee_member_id": OWNER_IDS[seed.assignee_name],
        "title": seed.title,
        "body": seed.body,
        "is_urgent": seed.is_urgent,
        "status_code": STATUS_CODES[seed.status],
        "registered_at": REFERENCE_AT + timedelta(days=seed.registered_day_offset),
    }


def support_request_upsert(row: dict):
    request_insert = insert(SupportRequest).values(**row)
    update_fields = {
        key: getattr(request_insert.excluded, key)
        for key in row
        if key not in {"id", "team_id", "customer_contact_id", "title", "registered_at"}
    }
    return request_insert.on_conflict_do_update(
        index_elements=[SupportRequest.id],
        set_=update_fields,
        where=and_(
            SupportRequest.team_id == FILLED_TEAM_ID,
            SupportRequest.customer_contact_id == row["customer_contact_id"],
            SupportRequest.title == row["title"],
            SupportRequest.registered_at == row["registered_at"],
        ),
    ).returning(SupportRequest.id)


async def seed_demo_support() -> None:
    request_rows = tuple(support_request_row(seed) for seed in SUPPORT_REQUEST_SEEDS)
    expected_requests_by_id = {row["id"]: row for row in request_rows}
    expected_request_id_by_natural = {
        (row["customer_contact_id"], row["title"], row["registered_at"]): row["id"]
        for row in request_rows
    }
    expected_contacts_by_id = {
        contact_id(seed.contact_mock_id): seed for seed in SUPPORT_REQUEST_SEEDS
    }
    expected_contact_id_by_natural = {
        (company_id(seed.company_name), seed.contact_name): contact_id(seed.contact_mock_id)
        for seed in SUPPORT_REQUEST_SEEDS
    }
    expected_assignees = {
        OWNER_IDS[seed.assignee_name]: seed.assignee_name for seed in SUPPORT_REQUEST_SEEDS
    }
    expected_assignee_id_by_name = {
        name: member_id for member_id, name in expected_assignees.items()
    }

    async with get_sessionmaker()() as session, session.begin():
        filled_team_name = (
            await session.execute(
                select(Team.name).where(Team.id == FILLED_TEAM_ID).with_for_update()
            )
        ).scalar_one_or_none()
        if filled_team_name != FILLED_TEAM_NAME:
            raise SystemExit("filled 인증 seed를 먼저 실행하세요.")

        existing_contacts = (
            await session.execute(
                select(
                    CustomerContact.id,
                    CustomerContact.company_id,
                    CustomerContact.owner_member_id,
                    CustomerContact.name,
                    CustomerContact.department,
                    CustomerCompany.team_id,
                    CustomerCompany.name.label("company_name"),
                )
                .join(CustomerCompany, CustomerCompany.id == CustomerContact.company_id)
                .where(
                    or_(
                        CustomerContact.id.in_(expected_contacts_by_id),
                        *(
                            and_(
                                CustomerContact.company_id == company_id(seed.company_name),
                                CustomerContact.name == seed.contact_name,
                            )
                            for seed in SUPPORT_REQUEST_SEEDS
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        for row in existing_contacts:
            expected = expected_contacts_by_id.get(row.id)
            natural = (row.company_id, row.name)
            if (
                expected is None
                or row.team_id != FILLED_TEAM_ID
                or row.company_name != expected.company_name
                or row.department != expected.department
                or row.owner_member_id != OWNER_IDS[expected.assignee_name]
                or expected_contact_id_by_natural.get(natural) != row.id
            ):
                raise SystemExit("합성 C/S 접수자 ID, 이름, 고객사 또는 팀이 충돌합니다.")
        if {row.id for row in existing_contacts} != set(expected_contacts_by_id):
            raise SystemExit("고객 seed를 먼저 실행해 C/S 접수자를 준비하세요.")

        existing_assignees = (
            await session.execute(
                select(
                    Member.id, Member.team_id, Member.display_name, Member.role_code, Member.active
                )
                .where(
                    or_(
                        Member.id.in_(expected_assignees),
                        and_(
                            Member.team_id == FILLED_TEAM_ID,
                            Member.display_name.in_(expected_assignee_id_by_name),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        for row in existing_assignees:
            if (
                row.team_id != FILLED_TEAM_ID
                or expected_assignees.get(row.id) != row.display_name
                or expected_assignee_id_by_name.get(row.display_name) != row.id
                or row.role_code != "member"
                or not row.active
            ):
                raise SystemExit("합성 C/S 담당자 ID, 이름, 팀, 역할 또는 상태가 충돌합니다.")
        if {row.id for row in existing_assignees} != set(expected_assignees):
            raise SystemExit("인증 seed를 먼저 실행해 C/S 담당자를 준비하세요.")

        existing_requests = (
            await session.execute(
                select(
                    SupportRequest.id,
                    SupportRequest.team_id,
                    SupportRequest.customer_contact_id,
                    SupportRequest.title,
                    SupportRequest.registered_at,
                )
                .where(
                    or_(
                        SupportRequest.id.in_(expected_requests_by_id),
                        *(
                            and_(
                                SupportRequest.team_id == FILLED_TEAM_ID,
                                SupportRequest.customer_contact_id == row["customer_contact_id"],
                                SupportRequest.title == row["title"],
                                SupportRequest.registered_at == row["registered_at"],
                            )
                            for row in request_rows
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        for row in existing_requests:
            expected = expected_requests_by_id.get(row.id)
            natural = (row.customer_contact_id, row.title, row.registered_at)
            if (
                expected is None
                or row.team_id != FILLED_TEAM_ID
                or expected_request_id_by_natural.get(natural) != row.id
            ):
                raise SystemExit("합성 C/S 요청 ID 또는 자연키 관계가 충돌합니다.")

        for row in request_rows:
            upserted_id = (await session.execute(support_request_upsert(row))).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 C/S 요청 ID 또는 자연키 관계가 충돌합니다.")

    print("filled 데모팀의 합성 C/S 요청 3건을 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_support())
