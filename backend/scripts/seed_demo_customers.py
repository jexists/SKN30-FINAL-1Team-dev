"""filled 데모팀에만 고정 합성 고객사와 담당자를 반복 가능하게 넣는다.

실제 고객 데이터가 아니며 이메일과 전화번호도 통신 불가능한 데모 값이다.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.security import dummy_password_hash
from app.db.session import get_sessionmaker
from app.models.crm import CustomerCompany, CustomerContact
from app.models.workspace import Member, Team
from scripts.seed_demo_auth import FILLED_MEMBER2_ID, FILLED_MEMBER_ID, FILLED_TEAM_ID

FILLED_TEAM_NAME = "SalesLuv 데모팀"
REFERENCE_AT = datetime(2026, 8, 17, tzinfo=UTC)

COMPANY_REGIONS = {
    "한빛대학교병원": "seoul",
    "서림메디컬센터": "seoul",
    "새봄정형외과": "gyeonggi",
    "도담재활병원": "gyeonggi",
    "정우병원": "incheon",
    "미래아동병원": "chungnam",
}

STATUS_CODES = {
    "신규": "new",
    "제안": "proposal",
    "협의": "negotiation",
    "계약": "contracted",
    "보류": "on_hold",
}

SOURCE_CODES = {
    "소개": "referral",
    "박람회": "exhibition",
    "홈페이지": "website",
    "콜드콜": "cold_call",
    "기존 거래": "existing_customer",
}


class ContactSeed(NamedTuple):
    mock_id: str
    name: str
    company_name: str
    department: str
    job_title: str
    email: str
    phone: str
    owner_name: str
    source: str
    status: str
    memo: str
    created_offset: int


ROSTER_MEMBERS = (
    {
        "id": uuid5(FILLED_TEAM_ID, "member:박도윤"),
        "login_id": "demo-roster-rep-4@example.invalid",
        "display_name": "박도윤",
    },
    {
        "id": uuid5(FILLED_TEAM_ID, "member:최가은"),
        "login_id": "demo-roster-rep-5@example.invalid",
        "display_name": "최가은",
    },
)

OWNER_IDS = {
    "김지훈": FILLED_MEMBER_ID,
    "이수민": FILLED_MEMBER2_ID,
    **{member["display_name"]: member["id"] for member in ROSTER_MEMBERS},
}

CONTACT_SEEDS = (
    ContactSeed(
        "FM-CU-2026-0001",
        "박서준",
        "한빛대학교병원",
        "순환기내과",
        "과장",
        "seojun.park@demo.test",
        "02-000-1840",
        "김지훈",
        "소개",
        "협의",
        "CardioView X7 도입 예산 확인 필요",
        -164,
    ),
    ContactSeed(
        "FM-CU-2026-0002",
        "윤가영",
        "서림메디컬센터",
        "영상의학과",
        "팀장",
        "gayoung.yoon@demo.test",
        "02-000-2731",
        "김지훈",
        "박람회",
        "계약",
        "사용 교육 일정 협의 중",
        -212,
    ),
    ContactSeed(
        "FM-CU-2026-0003",
        "오정민",
        "새봄정형외과",
        "원무팀",
        "대표원장",
        "jeongmin.oh@demo.test",
        "02-000-3677",
        "이수민",
        "홈페이지",
        "제안",
        "견적 전달 후 회신 없음",
        -88,
    ),
    ContactSeed(
        "FM-CU-2026-0004",
        "이민호",
        "한빛대학교병원",
        "구매팀",
        "과장",
        "minho.lee@demo.test",
        "02-000-1098",
        "김지훈",
        "기존 거래",
        "협의",
        "연간 소모품 단가 재협의",
        -301,
    ),
    ContactSeed(
        "FM-CU-2026-0005",
        "최수아",
        "정우병원",
        "정보전략팀",
        "책임",
        "sua.choi@demo.test",
        "02-000-4432",
        "박도윤",
        "소개",
        "제안",
        "PACS 연동 범위 확인",
        -57,
    ),
    ContactSeed(
        "FM-CU-2026-0006",
        "정하늘",
        "도담재활병원",
        "재활의학과",
        "실장",
        "haneul.jeong@demo.test",
        "02-000-5120",
        "최가은",
        "박람회",
        "신규",
        "전시 부스에서 명함 교환",
        -12,
    ),
    ContactSeed(
        "FM-CU-2026-0007",
        "강도현",
        "미래아동병원",
        "소아청소년과",
        "진료부장",
        "dohyun.kang@demo.test",
        "02-000-6248",
        "이수민",
        "소개",
        "협의",
        "SonoFlex Pro 데모 요청",
        -140,
    ),
    ContactSeed(
        "FM-CU-2026-0008",
        "한지우",
        "서림메디컬센터",
        "구매팀",
        "차장",
        "jiwoo.han@demo.test",
        "02-000-2865",
        "김지훈",
        "기존 거래",
        "계약",
        "3분기 발주 예정",
        -395,
    ),
    ContactSeed(
        "FM-CU-2026-0009",
        "문채원",
        "정우병원",
        "간호부",
        "수간호사",
        "chaewon.moon@demo.test",
        "02-000-4519",
        "박도윤",
        "콜드콜",
        "신규",
        "전극 패드 샘플 발송 대기",
        -20,
    ),
    ContactSeed(
        "FM-CU-2026-0010",
        "배준영",
        "한빛대학교병원",
        "심장혈관센터",
        "교수",
        "junyoung.bae@demo.test",
        "02-000-1276",
        "김지훈",
        "소개",
        "계약",
        "학술 심포지엄 공동 진행 논의",
        -430,
    ),
    ContactSeed(
        "FM-CU-2026-0011",
        "서은비",
        "새봄정형외과",
        "진료협력팀",
        "주임",
        "eunbi.seo@demo.test",
        "02-000-3391",
        "이수민",
        "홈페이지",
        "보류",
        "내년 예산 편성 후 재논의",
        -95,
    ),
    ContactSeed(
        "FM-CU-2026-0012",
        "노시현",
        "도담재활병원",
        "구매팀",
        "과장",
        "sihyun.noh@demo.test",
        "02-000-5074",
        "최가은",
        "박람회",
        "제안",
        "OrthoScan Mini 견적 검토 중",
        -63,
    ),
    ContactSeed(
        "FM-CU-2026-0013",
        "임세아",
        "미래아동병원",
        "원무팀",
        "팀장",
        "sea.lim@demo.test",
        "02-000-6712",
        "이수민",
        "기존 거래",
        "협의",
        "유지보수 계약 갱신 일정 확정 필요",
        -251,
    ),
    ContactSeed(
        "FM-CU-2026-0014",
        "조현우",
        "서림메디컬센터",
        "영상의학과",
        "전문의",
        "hyunwoo.jo@demo.test",
        "02-000-2088",
        "김지훈",
        "소개",
        "제안",
        "비교 견적 요청받음",
        -74,
    ),
    ContactSeed(
        "FM-CU-2026-0015",
        "황유진",
        "정우병원",
        "구매팀",
        "대리",
        "yujin.hwang@demo.test",
        "02-000-4903",
        "박도윤",
        "콜드콜",
        "신규",
        "첫 통화 완료, 자료 발송",
        -9,
    ),
    ContactSeed(
        "FM-CU-2026-0016",
        "신태호",
        "한빛대학교병원",
        "의공학팀",
        "팀장",
        "taeho.shin@demo.test",
        "02-000-1533",
        "김지훈",
        "기존 거래",
        "계약",
        "설치 환경 사전 점검 완료",
        -520,
    ),
    ContactSeed(
        "FM-CU-2026-0017",
        "권나연",
        "새봄정형외과",
        "간호부",
        "수간호사",
        "nayeon.kwon@demo.test",
        "02-000-3204",
        "이수민",
        "소개",
        "신규",
        "사용 교육 희망 인원 확인 필요",
        -30,
    ),
    ContactSeed(
        "FM-CU-2026-0018",
        "류정원",
        "도담재활병원",
        "재활의학과",
        "전문의",
        "jeongwon.ryu@demo.test",
        "02-000-5661",
        "최가은",
        "홈페이지",
        "협의",
        "데모 장비 2주 대여 요청",
        -102,
    ),
    ContactSeed(
        "FM-CU-2026-0019",
        "고민석",
        "미래아동병원",
        "의공학팀",
        "주임",
        "minseok.ko@demo.test",
        "02-000-6019",
        "이수민",
        "박람회",
        "보류",
        "담당자 변경 예정, 후임 확인 필요",
        -118,
    ),
    ContactSeed(
        "FM-CU-2026-0020",
        "심보라",
        "서림메디컬센터",
        "원무팀",
        "과장",
        "bora.shim@demo.test",
        "02-000-2447",
        "김지훈",
        "기존 거래",
        "협의",
        "결제 조건 조정 요청",
        -188,
    ),
    ContactSeed(
        "FM-CU-2026-0021",
        "양우진",
        "정우병원",
        "심장혈관센터",
        "교수",
        "woojin.yang@demo.test",
        "02-000-4155",
        "박도윤",
        "소개",
        "제안",
        "임상 사례 자료 요청받음",
        -77,
    ),
    ContactSeed(
        "FM-CU-2026-0022",
        "표지호",
        "한빛대학교병원",
        "원무팀",
        "대리",
        "jiho.pyo@demo.test",
        "02-000-1719",
        "김지훈",
        "콜드콜",
        "신규",
        "구매 절차 안내 예정",
        -15,
    ),
    ContactSeed(
        "FM-CU-2026-0023",
        "진소율",
        "새봄정형외과",
        "구매팀",
        "팀장",
        "soyul.jin@demo.test",
        "02-000-3548",
        "이수민",
        "박람회",
        "계약",
        "납품 일정 확정",
        -276,
    ),
    ContactSeed(
        "FM-CU-2026-0024",
        "설민아",
        "도담재활병원",
        "원무팀",
        "주임",
        "mina.seol@demo.test",
        "02-000-5892",
        "최가은",
        "홈페이지",
        "제안",
        "견적서 재발송 필요",
        -49,
    ),
    ContactSeed(
        "FM-CU-2026-0025",
        "남기훈",
        "미래아동병원",
        "소아청소년과",
        "전문의",
        "gihoon.nam@demo.test",
        "02-000-6503",
        "이수민",
        "소개",
        "신규",
        "초음파 장비 관심",
        -25,
    ),
    ContactSeed(
        "FM-CU-2026-0026",
        "차예린",
        "서림메디컬센터",
        "간호부",
        "수간호사",
        "yerin.cha@demo.test",
        "02-000-2610",
        "김지훈",
        "기존 거래",
        "계약",
        "소모품 정기 배송 전환 완료",
        -342,
    ),
    ContactSeed(
        "FM-CU-2026-0027",
        "방시우",
        "정우병원",
        "의공학팀",
        "차장",
        "siwoo.bang@demo.test",
        "02-000-4771",
        "박도윤",
        "박람회",
        "협의",
        "설치 공간 실측 일정 재조율",
        -131,
    ),
    ContactSeed(
        "FM-CU-2026-0028",
        "엄지수",
        "한빛대학교병원",
        "간호부",
        "주임",
        "jisu.eom@demo.test",
        "02-000-1385",
        "김지훈",
        "콜드콜",
        "보류",
        "부서 통합 이슈로 검토 중단",
        -66,
    ),
    ContactSeed(
        "FM-CU-2026-0029",
        "천유빈",
        "새봄정형외과",
        "재활의학과",
        "실장",
        "yubin.cheon@demo.test",
        "02-000-3970",
        "이수민",
        "홈페이지",
        "제안",
        "월 렌탈 방식 문의",
        -41,
    ),
    ContactSeed(
        "FM-CU-2026-0030",
        "구본희",
        "도담재활병원",
        "의공학팀",
        "과장",
        "bonhee.gu@demo.test",
        "02-000-5316",
        "최가은",
        "소개",
        "협의",
        "유지보수 범위 문서 전달",
        -83,
    ),
    ContactSeed(
        "FM-CU-2026-0031",
        "주하람",
        "미래아동병원",
        "구매팀",
        "대리",
        "haram.joo@demo.test",
        "02-000-6884",
        "이수민",
        "기존 거래",
        "신규",
        "전임자 인수인계 중",
        -35,
    ),
    ContactSeed(
        "FM-CU-2026-0032",
        "위성찬",
        "정우병원",
        "원무팀",
        "팀장",
        "seongchan.wi@demo.test",
        "02-000-4288",
        "박도윤",
        "박람회",
        "계약",
        "연간 계약 체결, 첫 납품 준비",
        -207,
    ),
)


def company_id(name: str) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"company:{name}")


def contact_id(mock_id: str) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"contact:{mock_id}")


async def seed_demo_customers() -> None:
    roster_password_hash = await asyncio.to_thread(dummy_password_hash)
    company_ids = {name: company_id(name) for name in COMPANY_REGIONS}
    expected_company_by_id = {value: name for name, value in company_ids.items()}
    extra_member_by_id = {member["id"]: member for member in ROSTER_MEMBERS}
    extra_member_by_login = {member["login_id"]: member for member in ROSTER_MEMBERS}

    contacts = tuple(
        {
            "id": contact_id(seed.mock_id),
            "company_id": company_ids[seed.company_name],
            "owner_member_id": OWNER_IDS[seed.owner_name],
            "name": seed.name,
            "department": seed.department,
            "job_title": seed.job_title,
            "email": seed.email,
            "phone": seed.phone,
            "status_code": STATUS_CODES[seed.status],
            "source_code": SOURCE_CODES[seed.source],
            "memo": seed.memo,
            "registered_at": REFERENCE_AT + timedelta(days=seed.created_offset),
        }
        for seed in CONTACT_SEEDS
    )
    expected_contact_by_id = {contact["id"]: contact for contact in contacts}

    async with get_sessionmaker()() as session, session.begin():
        filled_team_name = (
            await session.execute(
                select(Team.name).where(Team.id == FILLED_TEAM_ID).with_for_update()
            )
        ).scalar_one_or_none()
        if filled_team_name != FILLED_TEAM_NAME:
            raise SystemExit("filled 인증 seed의 고정 팀이 없거나 이름이 변경되었습니다.")

        login_members = {
            FILLED_MEMBER_ID: "김지훈",
            FILLED_MEMBER2_ID: "이수민",
        }
        member_ids = {*login_members, *extra_member_by_id}
        existing_members = (
            await session.execute(
                select(
                    Member.id,
                    Member.team_id,
                    Member.login_id,
                    Member.display_name,
                    Member.role_code,
                    Member.active,
                )
                .where(
                    or_(
                        Member.id.in_(member_ids),
                        Member.login_id.in_(extra_member_by_login),
                    )
                )
                .with_for_update()
            )
        ).all()
        found_member_ids = {row.id for row in existing_members}
        for row in existing_members:
            if row.id in login_members:
                if (
                    row.team_id != FILLED_TEAM_ID
                    or row.display_name != login_members[row.id]
                    or row.role_code != "member"
                    or not row.active
                    or row.login_id in extra_member_by_login
                ):
                    raise SystemExit("filled 팀원 데모 계정의 소속·역할이 다릅니다.")
                continue

            expected = extra_member_by_id.get(row.id)
            if (
                expected is None
                or row.team_id != FILLED_TEAM_ID
                or row.login_id != expected["login_id"]
                or extra_member_by_login.get(row.login_id) != expected
            ):
                raise SystemExit("합성 팀원 ID, 로그인 ID 또는 팀이 충돌합니다.")
        if not set(login_members).issubset(found_member_ids):
            raise SystemExit("인증 seed를 먼저 실행해 filled 팀원 데모 계정을 만드세요.")

        for member in ROSTER_MEMBERS:
            member_insert = insert(Member).values(
                id=member["id"],
                team_id=FILLED_TEAM_ID,
                login_id=member["login_id"],
                password_hash=roster_password_hash,
                display_name=member["display_name"],
                role_code="member",
                job_title="영업 담당자",
                active=True,
            )
            upserted_id = (
                await session.execute(
                    member_insert.on_conflict_do_update(
                        index_elements=[Member.id],
                        set_={
                            "password_hash": member_insert.excluded.password_hash,
                            "display_name": member_insert.excluded.display_name,
                            "role_code": member_insert.excluded.role_code,
                            "job_title": member_insert.excluded.job_title,
                            "active": member_insert.excluded.active,
                        },
                        where=and_(
                            Member.team_id == FILLED_TEAM_ID,
                            Member.login_id == member["login_id"],
                        ),
                    ).returning(Member.id)
                )
            ).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 팀원 ID, 로그인 ID 또는 팀이 충돌합니다.")

        existing_companies = (
            await session.execute(
                select(CustomerCompany.id, CustomerCompany.team_id, CustomerCompany.name)
                .where(
                    or_(
                        CustomerCompany.id.in_(expected_company_by_id),
                        and_(
                            CustomerCompany.team_id == FILLED_TEAM_ID,
                            CustomerCompany.name.in_(company_ids),
                        ),
                    )
                )
                .with_for_update()
            )
        ).all()
        for row in existing_companies:
            if (
                expected_company_by_id.get(row.id) != row.name
                or row.team_id != FILLED_TEAM_ID
                or company_ids.get(row.name) != row.id
            ):
                raise SystemExit("합성 고객사 ID, 이름 또는 팀이 충돌합니다.")

        for name, region_code in COMPANY_REGIONS.items():
            company_insert = insert(CustomerCompany).values(
                id=company_ids[name],
                team_id=FILLED_TEAM_ID,
                name=name,
                region_code=region_code,
            )
            upserted_id = (
                await session.execute(
                    company_insert.on_conflict_do_update(
                        index_elements=[CustomerCompany.id],
                        set_={"region_code": company_insert.excluded.region_code},
                        where=and_(
                            CustomerCompany.team_id == FILLED_TEAM_ID,
                            CustomerCompany.name == name,
                        ),
                    ).returning(CustomerCompany.id)
                )
            ).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 고객사 ID, 이름 또는 팀이 충돌합니다.")

        existing_contacts = (
            await session.execute(
                select(
                    CustomerContact.id,
                    CustomerContact.company_id,
                    CustomerContact.owner_member_id,
                )
                .where(CustomerContact.id.in_(expected_contact_by_id))
                .with_for_update()
            )
        ).all()
        for row in existing_contacts:
            expected = expected_contact_by_id[row.id]
            if (
                row.company_id != expected["company_id"]
                or row.owner_member_id != expected["owner_member_id"]
            ):
                raise SystemExit("합성 고객 담당자 ID, 고객사 또는 owner가 충돌합니다.")

        for contact in contacts:
            contact_insert = insert(CustomerContact).values(**contact)
            upserted_id = (
                await session.execute(
                    contact_insert.on_conflict_do_update(
                        index_elements=[CustomerContact.id],
                        set_={
                            "name": contact_insert.excluded.name,
                            "department": contact_insert.excluded.department,
                            "job_title": contact_insert.excluded.job_title,
                            "email": contact_insert.excluded.email,
                            "phone": contact_insert.excluded.phone,
                            "status_code": contact_insert.excluded.status_code,
                            "source_code": contact_insert.excluded.source_code,
                            "memo": contact_insert.excluded.memo,
                            "registered_at": contact_insert.excluded.registered_at,
                        },
                        where=and_(
                            CustomerContact.company_id == contact["company_id"],
                            CustomerContact.owner_member_id == contact["owner_member_id"],
                        ),
                    ).returning(CustomerContact.id)
                )
            ).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 고객 담당자 ID, 고객사 또는 owner가 충돌합니다.")

    print("개발 DB의 filled 합성 팀에 고객사 6개와 담당자 32명을 준비했습니다.")


if __name__ == "__main__":
    asyncio.run(seed_demo_customers())
