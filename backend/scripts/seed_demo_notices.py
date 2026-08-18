"""filled 데모팀에만 합성 공지와 개인 지시를 반복 가능하게 넣는다.

수신자가 없는 행이 팀 공지, 수신자가 있는 행이 그 사람에게 온 지시다.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID, uuid5

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import get_sessionmaker
from app.models.workspace import Member, Notice, Team
from scripts.seed_demo_auth import FILLED_MANAGER_ID, FILLED_MEMBER_ID, FILLED_TEAM_ID
from scripts.seed_demo_customers import FILLED_TEAM_NAME

REFERENCE_AT = datetime(2026, 8, 17, tzinfo=UTC)


class NoticeSeed(NamedTuple):
    mock_id: str
    # 유스케이스에 공지 태그 어휘 정의가 없어 비워 둔다. 정의되면 그때 채운다.
    tag: str | None
    title: str
    body: str
    day_offset: int
    hour: int
    minute: int
    # None 이면 팀 공지, 값이 있으면 그 사람에게 온 지시다.
    recipient_id: UUID | None
    due_day_offset: int | None
    due_text: str | None


NOTICE_SEEDS = (
    NoticeSeed(
        "notice-1",
        None,
        "미팅에서 예산 집행 시기와 승인 담당자를 확인해 주세요",
        "상반기 실주 건을 되짚어 보니 제품 평가는 끝났는데 예산 집행 시기가 다음 분기로 밀려"
        " 흐지부지된 경우가 가장 많았습니다. 예산이 언제 열리는지, 최종 승인자가 실무 담당자인지"
        " 원장인지 두 가지를 확인하고 미팅보고서에 남겨 주세요.",
        0,
        8,
        40,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "notice-2",
        None,
        "8월 프로모션 단가표가 갱신되었습니다",
        "본체 가격은 그대로이고 3년 유지보수 패키지와 소모품 첫 해 공급분의 할인율이 바뀌었습니다."
        " 7월 단가표로 이미 나간 견적은 회수하지 말고 갱신본을 다시 보내면서 달라진 항목만"
        " 짚어 주세요.",
        -1,
        17,
        20,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "notice-3",
        None,
        "8월 출장비 정산은 25일까지 접수분만 당월 지급됩니다",
        "25일 이후 접수분은 다음 달 급여일에 함께 지급됩니다. 지방 출장 건은 방문한 고객사와"
        " 목적을 함께 적어 주시고, 영수증이 없는 대중교통 이용분은 경로만 남겨도 됩니다.",
        -2,
        14,
        30,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "notice-4",
        None,
        "신규 사용자 교육 슬롯이 다음 주 3일간으로 확정되었습니다",
        "다음 주 화·수·목 오후 2시부터 각 2시간씩 진행합니다. 회차당 정원은 8명이고 병원별로"
        " 최대 3명까지 신청할 수 있습니다. 도입 후 한 달이 지나지 않은 고객사를 먼저 안내해"
        " 주세요.",
        -3,
        11,
        5,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "notice-5",
        None,
        "펌웨어 2.4.1 배포. 방문 시 버전 확인을 부탁드립니다",
        "프로브 연결이 간헐적으로 끊기던 증상을 고친 버전입니다. 회수 대상은 아니지만 장비 설정"
        " 화면에서 버전이 2.4.0 이하이면 현장에서 업데이트를 권해 주세요. 저장된 검사 기록은"
        " 그대로 남습니다.",
        -5,
        9,
        15,
        None,
        None,
        None,
    ),
    NoticeSeed(
        "directive-1",
        None,
        "갱신 예정 계약 2건의 담당자 확인 결과를 공유해 주세요",
        "갱신 시점이 지나고 연락하면 이미 다른 업체 견적을 받아 본 뒤입니다. 갱신 의사가 있는지,"
        " 조건에서 바꾸고 싶은 것이 있는지 두 가지를 확인하고 결과를 공유해 주세요.",
        0,
        9,
        10,
        FILLED_MEMBER_ID,
        4,
        "금요일까지",
    ),
    NoticeSeed(
        "directive-2",
        None,
        "긴급 C/S 1건은 오늘 중 1차 응답을 남겨 주세요",
        "고객이 답답해하는 것은 고장 자체보다 언제 고쳐지는지 모르는 상태입니다. 원인 파악이"
        " 끝나지 않았더라도 접수 사실과 언제까지 답을 주겠다는 약속을 먼저 전해 주세요.",
        0,
        8,
        5,
        FILLED_MEMBER_ID,
        0,
        "오늘 중",
    ),
)


def notice_id(mock_id: str) -> UUID:
    return uuid5(FILLED_TEAM_ID, f"notice:{mock_id}")


def notice_row(seed: NoticeSeed) -> dict:
    published_at = REFERENCE_AT + timedelta(
        days=seed.day_offset, hours=seed.hour, minutes=seed.minute
    )
    due_at = (
        None
        if seed.due_day_offset is None
        else REFERENCE_AT + timedelta(days=seed.due_day_offset, hours=18)
    )
    return {
        "id": notice_id(seed.mock_id),
        "team_id": FILLED_TEAM_ID,
        "author_member_id": FILLED_MANAGER_ID,
        "recipient_member_id": seed.recipient_id,
        "tag": seed.tag,
        "title": seed.title,
        "body": seed.body,
        "image_storage_key": None,
        "image_alt": None,
        "published_at": published_at,
        "due_at": due_at,
        "due_text": seed.due_text,
    }


def notice_upsert(row: dict):
    notice_insert = insert(Notice).values(**row)
    update_fields = {
        key: getattr(notice_insert.excluded, key)
        for key in row
        if key not in {"id", "team_id", "author_member_id", "title", "published_at"}
    }
    return notice_insert.on_conflict_do_update(
        index_elements=[Notice.id],
        set_=update_fields,
        where=and_(
            Notice.team_id == FILLED_TEAM_ID,
            Notice.title == row["title"],
            Notice.published_at == row["published_at"],
        ),
    ).returning(Notice.id)


async def seed_demo_notices() -> None:
    rows = tuple(notice_row(seed) for seed in NOTICE_SEEDS)
    expected_by_id = {row["id"]: row for row in rows}
    expected_id_by_natural = {(row["title"], row["published_at"]): row["id"] for row in rows}
    expected_members = {FILLED_MANAGER_ID: "manager", FILLED_MEMBER_ID: "member"}

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
                select(Member.id, Member.team_id, Member.role_code, Member.active)
                .where(Member.id.in_(expected_members))
                .with_for_update()
            )
        ).all()
        for row in existing_members:
            if (
                row.team_id != FILLED_TEAM_ID
                or expected_members.get(row.id) != row.role_code
                or not row.active
            ):
                raise SystemExit("합성 공지 작성자 또는 수신자의 팀, 역할, 상태가 충돌합니다.")
        if {row.id for row in existing_members} != set(expected_members):
            raise SystemExit("인증 seed를 먼저 실행해 공지 작성자와 수신자를 준비하세요.")

        existing_notices = (
            await session.execute(
                select(Notice.id, Notice.team_id, Notice.title, Notice.published_at)
                .where(Notice.id.in_(expected_by_id))
                .with_for_update()
            )
        ).all()
        for row in existing_notices:
            expected = expected_by_id.get(row.id)
            natural = (row.title, row.published_at)
            if (
                expected is None
                or row.team_id != FILLED_TEAM_ID
                or expected_id_by_natural.get(natural) != row.id
            ):
                raise SystemExit("합성 공지 ID 또는 자연키 관계가 충돌합니다.")

        for row in rows:
            upserted_id = (await session.execute(notice_upsert(row))).scalar_one_or_none()
            if upserted_id is None:
                raise SystemExit("합성 공지 ID 또는 자연키 관계가 충돌합니다.")

    team_count = sum(1 for seed in NOTICE_SEEDS if seed.recipient_id is None)
    print(
        f"filled 데모팀의 합성 공지 {team_count}건과 "
        f"개인 지시 {len(NOTICE_SEEDS) - team_count}건을 준비했습니다."
    )


if __name__ == "__main__":
    asyncio.run(seed_demo_notices())
