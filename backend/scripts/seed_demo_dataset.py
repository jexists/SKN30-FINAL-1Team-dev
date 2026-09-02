"""데모 팀 하나에 반복 실행 가능한 업무 데이터를 넣는다.

공공데이터 병원 목록(영업중 3,440곳)을 고객사로 넣고, 그중 일부에 담당자·딜·활동·
보고서·발주·고객불만을 실제 외래키로 이어 붙인다. 공지와 지시사항, 자료실도 함께 만든다.

모든 날짜는 기준일(--base-date, 기본값은 실행일)의 상대 오프셋이다. 절대 날짜를 두지
않으므로 며칠 뒤에 실행해도 과거·오늘·미래 업무의 구분이 그대로 유지된다.

새로 넣는 행의 id 는 uuid5(team_id, "demo2026:종류:자연키") 라 다시 실행해도 같은 행을
갱신할 뿐 늘어나지 않고, 이 시드가 만든 것만 골라 지울 수 있다.

실제 고객 데이터가 아니며 이메일·전화번호도 통신 불가능한 값이다.

    uv run python -m scripts.seed_demo_dataset [--reset] [--dry-run] [--base-date YYYY-MM-DD]
"""

import argparse
import asyncio
import os
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_sessionmaker
from app.models.configuration import (
    ActivityActionTag,
    ActivityCategory,
    ContractStatus,
    CustomerContactStatus,
    PurchaseOrderStatus,
    QuoteStatus,
    SalesDealType,
)
from app.models.content import Document, File, Report, ReportActivity
from app.models.crm import (
    Activity,
    CustomerCompany,
    CustomerContact,
    CustomerContactAssignee,
    SupportRequest,
    SupportResponse,
)
from app.models.sales import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesDeal,
    SalesDealItem,
    SalesPipeline,
    SalesPipelineStage,
    SalesTarget,
)
from app.models.workspace import Member, Notice, NoticeTarget, Team
from scripts.demo import data, hospitals
from scripts.demo._docx import MEDIA_TYPE, build_docx
from scripts.demo.data import SEED_TAG, TEAM_NAME
from scripts.seed_demo_auth import seed_team_configuration

SEOUL = ZoneInfo("Asia/Seoul")

# 팀 id 는 팀 이름에서 파생한다. 저장소에 UUID 를 상수로 두지 않으면서도 재실행 시
# 같은 팀을 찾아야 하기 때문이다. uuid5 라 이름이 같으면 항상 같은 값이 나온다.
TEAM_NAMESPACE = UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
TEAM_ID = uuid5(TEAM_NAMESPACE, f"{SEED_TAG}:team:{TEAM_NAME}")

PASSWORD_ENV = "DEMO_SEED_PASSWORD"

# 영업활동이 붙는 고객사 수. 나머지는 미개척 목록으로 남는다.
ACTIVE_COMPANIES = 520
DEALS = 220
ORDERS = 60
PAST_DAYS = 120
FUTURE_DAYS = 61
BATCH = 500

# 갱신 대상. 1년 전에 체결한 계약이라 종료일이 곧 돌아온다. 계약이 전부 최근 PAST_DAYS
# 안에 체결되면 종료일이 245~365일 뒤에 몰려 대시보드 갱신 카드(30일 이내)가 늘 0건이다.
RENEWALS = 14

SUPPLIERS = ("레이저메디텍", "프로레이저솔루션", "루미나레이저", "한빛옵틱스")


# ---------------------------------------------------------------- 공통 도우미


def _rand(seed: str, limit: int) -> int:
    """자연키에서 뽑는 결정적 난수. random 을 쓰면 재실행마다 결과가 달라진다."""
    return int(uuid5(TEAM_ID, seed).int % limit)


def _pick(seed: str, items: tuple[Any, ...] | list[Any]) -> Any:
    return items[_rand(seed, len(items))]


async def upsert(db: AsyncSession, model: Any, values: dict[str, Any]) -> None:
    """id 가 같으면 갱신한다. id 가 자연키에서 나오므로 다시 실행해도 늘지 않는다."""
    stmt = insert(model).values(**values)
    updates = {key: getattr(stmt.excluded, key) for key in values if key != "id"}
    await db.execute(stmt.on_conflict_do_update(index_elements=[model.id], set_=updates))


async def upsert_many(db: AsyncSession, model: Any, rows: list[dict[str, Any]]) -> None:
    """같은 모양의 행을 묶어서 넣는다. 3,440건을 한 건씩 왕복하면 느리다."""
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        if not chunk:
            continue
        stmt = insert(model).values(chunk)
        updates = {key: getattr(stmt.excluded, key) for key in chunk[0] if key != "id"}
        await db.execute(stmt.on_conflict_do_update(index_elements=[model.id], set_=updates))


async def link(db: AsyncSession, model: Any, rows: list[dict[str, Any]]) -> None:
    """복합 기본키를 쓰는 연결 표. 이미 있으면 그대로 둔다."""
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        if chunk:
            await db.execute(insert(model).values(chunk).on_conflict_do_nothing())


async def guard_team(db: AsyncSession, model: Any, ids: list[UUID], team_id: UUID) -> None:
    """같은 id 가 다른 팀 소유로 이미 있으면 덮어쓰지 않고 멈춘다."""
    rows = (await db.execute(select(model.id, model.team_id).where(model.id.in_(ids)))).all()
    if any(row.team_id != team_id for row in rows):
        raise SystemExit(f"{model.__tablename__} 에 다른 팀 소유의 같은 id 가 있습니다.")


class _DryRun(Exception):
    """dry-run 에서 트랜잭션을 되돌리기 위한 내부 신호."""


# ---------------------------------------------------------------- 팀과 계정


async def ensure_team_and_members(
    db: AsyncSession, *, dry_run: bool
) -> tuple[dict[str, UUID], list[str]]:
    """팀·기본 설정·구성원 5명을 확보하고 ({이름: member_id}, 없는 이메일) 을 돌려준다.

    member.id 는 auth.users.id 와 같은 값이라 Auth 사용자가 먼저 있어야 한다. 이미 있는
    계정은 조회로 재사용하므로 실행할 때마다 새 사용자가 생기지 않는다.

    dry-run 은 Auth 사용자를 만들지 않는다. 트랜잭션 밖이라 되돌릴 수 없기 때문이다.
    없는 계정은 만들지 않고 목록으로만 돌려준다.
    """
    from app.services import supabase_auth

    await upsert(
        db,
        Team,
        {"id": TEAM_ID, "name": TEAM_NAME, "company_name": "SalesLuv", "department": "영업팀"},
    )
    await seed_team_configuration(db, TEAM_ID)

    known = {
        row.email.lower(): row.id
        for row in (
            await db.execute(select(Member.id, Member.email).where(Member.email.is_not(None)))
        ).all()
    }

    password = os.environ.get(PASSWORD_ENV, "")
    members: dict[str, UUID] = {}
    missing: list[str] = []
    created = 0
    for seed in data.MEMBERS:
        member_id = known.get(seed.email.lower())
        if member_id is None:
            if dry_run:
                # 만들지 않는다. member 행은 auth.users 를 참조하므로 가짜 id 로는
                # 넣을 수도 없다. 무엇이 필요한지만 알린다.
                missing.append(seed.email)
                continue
            else:
                if not password:
                    raise SystemExit(
                        f"{PASSWORD_ENV} 환경변수가 필요합니다. "
                        f"계정 {seed.email} 을 만들 수 없습니다."
                    )
                try:
                    member_id = await supabase_auth.create_confirmed_user(
                        email=seed.email, password=password
                    )
                except supabase_auth.EmailAlreadyExists as error:
                    # auth 에는 있는데 member 행이 없는 상태다. UUID 를 알 길이 없으므로
                    # 사람이 정리해야 한다. 조용히 넘기면 팀이 반쪽으로 남는다.
                    raise SystemExit(
                        f"{seed.email} 이 Supabase Auth 에 있지만 member 행이 없습니다. "
                        "Dashboard 에서 확인해 주세요."
                    ) from error
                created += 1
        members[seed.key] = member_id
        await upsert(
            db,
            Member,
            {
                "id": member_id,
                "team_id": TEAM_ID,
                "display_name": seed.display_name,
                "role_code": seed.role_code,
                "job_title": seed.job_title,
                "email": seed.email,
                "active": True,
            },
        )

    if created:
        print(f"  Auth 계정 {created}개를 새로 만들었습니다.")
    return members, missing


# ---------------------------------------------------------------- 시딩


class Seeder:
    def __init__(
        self, db: AsyncSession, members: dict[str, UUID], base_date: date, *, with_documents: bool
    ) -> None:
        self.db = db
        self.team_id = TEAM_ID
        self.members = members
        self.base = base_date
        self.with_documents = with_documents
        self.counts: dict[str, int] = {}
        self.products: dict[str, tuple[UUID, int]] = {}
        self.companies: list[tuple[str, UUID]] = []
        self.contacts: list[dict[str, Any]] = []
        # seed_contact_rollup 이 딜·활동을 보고 되짚어 쓰도록 담당자 행을 들고 있는다.
        self.contact_rows: dict[UUID, dict[str, Any]] = {}
        self.visited_contacts: set[UUID] = set()
        self.deals: list[dict[str, Any]] = []
        self.uploaded: list[str] = []
        # (담당자, 날짜) -> 그날 완료된 활동. 일일·주간보고서를 실제 활동에서 만든다.
        self.by_day: dict[tuple[str, date], list[dict[str, Any]]] = {}

    # --- 도구

    def sid(self, kind: str, key: str) -> UUID:
        return uuid5(self.team_id, f"{SEED_TAG}:{kind}:{key}")

    def bump(self, key: str, amount: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + amount

    def day(self, offset: int) -> date:
        return self.base + timedelta(days=offset)

    def at(self, when: date, hour: int, minute: int = 0) -> datetime:
        return datetime(when.year, when.month, when.day, hour, minute, tzinfo=SEOUL)

    # --- 팀 설정 읽기

    async def load_configuration(self) -> None:
        async def codes(model: Any) -> dict[str, UUID]:
            rows = (
                await self.db.execute(
                    select(model.code, model.id).where(
                        model.team_id == self.team_id, model.deleted_at.is_(None)
                    )
                )
            ).all()
            return {row.code: row.id for row in rows}

        self.status = await codes(CustomerContactStatus)
        self.category = await codes(ActivityCategory)
        self.tag = await codes(ActivityActionTag)
        self.deal_type = await codes(SalesDealType)
        self.order_status = await codes(PurchaseOrderStatus)
        self.quote_status = await codes(QuoteStatus)
        self.contract_status = await codes(ContractStatus)

        self.pipeline_id = (
            await self.db.execute(
                select(SalesPipeline.id).where(
                    SalesPipeline.team_id == self.team_id,
                    SalesPipeline.is_default.is_(True),
                    SalesPipeline.status_code == "published",
                )
            )
        ).scalar_one()
        rows = (
            await self.db.execute(
                select(
                    SalesPipelineStage.stage_code,
                    SalesPipelineStage.id,
                    SalesPipelineStage.outcome_code,
                    SalesPipelineStage.position,
                ).where(SalesPipelineStage.sales_pipeline_id == self.pipeline_id)
            )
        ).all()
        self.stages = {r.stage_code: (r.id, r.outcome_code, r.position) for r in rows}

    # --- 01~05 기초 데이터

    async def seed_products(self) -> None:
        rows = []
        for seed in data.PRODUCTS:
            product_id = self.sid("product", seed.name)
            self.products[seed.name] = (product_id, seed.unit_price)
            rows.append(
                {
                    "id": product_id,
                    "team_id": self.team_id,
                    "name": seed.name,
                    "active": True,
                    "category_code": seed.category_code,
                    "unit_price": seed.unit_price,
                    "shelf_life_months": seed.shelf_life_months,
                    "memo": seed.memo,
                    "image_storage_key": None,
                }
            )
        await guard_team(self.db, Product, [r["id"] for r in rows], self.team_id)
        await upsert_many(self.db, Product, rows)
        self.bump("product", len(rows))

    async def seed_companies(self) -> None:
        loaded = hospitals.load()
        # 갱신 코호트의 딜은 1년 전에 열린다. 고객사가 그보다 늦게 생기면 안 된다.
        created = self.at(self.day(-PAST_DAYS - 300), 9)
        rows = []
        for item in loaded:
            company_id = self.sid("company", item.name)
            self.companies.append((item.name, company_id))
            rows.append(
                {
                    "id": company_id,
                    "team_id": self.team_id,
                    "name": item.name,
                    "region_code": item.region_code,
                    # 원본에 사업자번호가 없다. 지어내면 실존 사업자와 겹칠 수 있어 비워 둔다.
                    "business_no": None,
                    "postcode": item.postcode,
                    "address": item.address,
                    "address_detail": None,
                    "created_at": created,
                }
            )
        await guard_team(self.db, CustomerCompany, [r["id"] for r in rows[:BATCH]], self.team_id)
        await upsert_many(self.db, CustomerCompany, rows)
        self.bump("company", len(rows))

    async def seed_contacts(self) -> None:
        """앞쪽 고객사에만 담당자를 둔다. 나머지는 미개척 목록으로 남는다."""
        rows, links = [], []
        for index, (name, company_id) in enumerate(self.companies[:ACTIVE_COMPANIES]):
            owner = data.SALES[index % len(data.SALES)]
            # 큰 병원일수록 접점이 둘이다. 결정적으로 갈라 재실행 시 같은 수가 나오게 한다.
            count = 2 if _rand(f"contact-count:{name}", 5) < 2 else 1
            for slot in range(count):
                key = f"{name}#{slot}"
                contact_id = self.sid("contact", key)
                surname = _pick(f"sur:{key}", data.CONTACT_SURNAMES)
                given = _pick(f"giv:{key}", data.CONTACT_GIVEN)
                registered = self.at(self.day(-PAST_DAYS + _rand(f"reg:{key}", 20)), 10)
                row = {
                    "id": contact_id,
                    "company_id": company_id,
                    "owner_member_id": self.members[owner],
                    "created_by_member_id": self.members[owner],
                    "name": f"{surname}{given}",
                    "department": _pick(f"dept:{key}", data.CONTACT_DEPARTMENTS),
                    "job_title": _pick(f"title:{key}", data.CONTACT_TITLES),
                    # 통신 불가능한 번호대와 예약 도메인만 쓴다. 이름 조합이 320가지뿐이라
                    # 담당자 700여 명 사이에 동명이인이 나온다. 뒤 네 자리가 주소를 가른다.
                    "email": (
                        f"{data.CONTACT_SURNAME_ROMAN[surname]}."
                        f"{data.CONTACT_GIVEN_ROMAN[given]}"
                        f"{_rand(f'em:{key}', 10000):04d}@example.com"
                    ),
                    "phone": f"010-0000-{_rand(f'ph:{key}', 10000):04d}",
                    # 상태·방문·메모는 딜과 활동을 만든 뒤 seed_contact_rollup 이 되짚는다.
                    "customer_contact_status_id": self.status["new"],
                    "source_code": None,
                    "memo": None,
                    "visited": False,
                    "registered_at": registered,
                }
                rows.append(row)
                self.contact_rows[contact_id] = row
                links.append({"customer_contact_id": contact_id, "member_id": self.members[owner]})
                self.contacts.append(
                    {"id": contact_id, "company_id": company_id, "company": name, "owner": owner}
                )
        await upsert_many(self.db, CustomerContact, rows)
        await link(self.db, CustomerContactAssignee, links)
        self.bump("contact", len(rows))
        self.bump("contact_assignee", len(links))

    # --- 06~07 딜과 견적 품목

    # (단계 코드, 건수). 합이 DEALS 다. 9단계가 모두 채워져야 영업현황 화면이 비지 않는다.
    STAGE_MIX = (
        ("needs_validation", 32),
        ("product_demo", 30),
        ("quote_sent", 40),
        ("contract_sent", 16),
        ("contract_review", 12),
        ("contract_completed", 30),
        ("order_in_progress", 24),
        ("order_delivered", 22),
        ("closed_cancelled", 14),
    )
    QUOTE_FROM = 2  # quote_sent 부터 견적이 있다
    CONTRACT_FROM = 3  # contract_sent 부터 계약서가 있다
    SIGNED_FROM = 5  # contract_completed 부터 서명이 끝났다

    WARRANTY = "설치일로부터 12개월 무상 보증, 이후 연간 유지보수 계약 별도"
    PAYMENT = "계약금 30%, 납품 완료 후 잔금 70% 를 30일 이내 지급"
    LATE_INTEREST = "지급 지연 시 연 6% 의 지연이자를 적용한다"
    DELIVERY = "발주 후 4주 이내 납품, 설치와 사용 교육 포함"

    async def seed_deals(self) -> None:
        rows, items = [], []
        # 계약 이후 단계는 서사가 길어 오래된 고객사에 붙인다. 첫 통화 단계가 어제 열린
        # 고객사에 납품 완료 딜이 달리면 흐름이 말이 안 된다.
        plan = [code for code, count in self.STAGE_MIX for _ in range(count)]
        # 갱신 코호트. 확정 딜에서 고르게 뽑는다. 앞에서부터 자르면 계약 완료 단계에만
        # 몰려 갱신 목록이 한 단계로만 채워진다.
        confirmed = [i for i, code in enumerate(plan) if self.stages[code][1] == "confirmed"]
        renewals = set(confirmed[:: max(len(confirmed) // RENEWALS, 1)][:RENEWALS])
        for index, stage_code in enumerate(plan):
            contact = self.contacts[index % len(self.contacts)]
            stage_id, outcome, position = self.stages[stage_code]
            key = f"D{index:04d}"
            deal_id = self.sid("deal", key)
            owner = contact["owner"]

            product_name = _pick(f"prod:{key}", tuple(self.products))
            product_id, unit_price = self.products[product_name]
            quantity = 1 + _rand(f"qty:{key}", 6)
            amount = unit_price * quantity

            # 갱신 코호트는 종료일에서 거꾸로 짠다. 1년 계약이라 종료일이 곧 돌아오려면
            # 체결이 1년 전이어야 하고, 그러면 개설·견적도 그만큼 앞이어야 한다.
            if index in renewals:
                renewal_ends = self.day(3 + _rand(f"rn:{key}", 26))
                renewal_signed = renewal_ends - timedelta(days=365)
                renewal_quoted = renewal_signed - timedelta(days=8 + _rand(f"rq:{key}", 14))
                opened = renewal_quoted - timedelta(days=10 + _rand(f"ro:{key}", 12))
            else:
                renewal_ends = renewal_signed = renewal_quoted = None
                # 단계가 뒤일수록 더 오래전에 열렸다. 진행에 걸린 시간을 날짜로 표현한다.
                span = 12 + position * 11
                opened = self.day(-span - _rand(f"open:{key}", 20))

            row: dict[str, Any] = {
                "id": deal_id,
                "team_id": self.team_id,
                "deal_no": f"SL-DL-{key}",
                "customer_company_id": contact["company_id"],
                "customer_contact_id": contact["id"],
                "owner_member_id": self.members[owner],
                "product_id": product_id,
                "sales_pipeline_id": self.pipeline_id,
                "sales_pipeline_stage_id": stage_id,
                "title": f"{contact['company']} {product_name} {quantity}대",
                "description": None,
                "sales_deal_type_id": self.deal_type[_pick(f"type:{key}", tuple(self.deal_type))],
                "deal_amount": amount,
                "opened_on": opened,
                "closed_on": None,
                "quote_no": None,
                "quote_issued_on": None,
                "quote_valid_until": None,
                "quote_status_id": None,
                "quote_amount": None,
                "quote_delivery_terms": None,
                "contract_no": None,
                "contract_signed_on": None,
                "contract_ends_on": None,
                "contract_status_id": None,
                "contract_amount": None,
                "contract_payment_terms": None,
                "contract_late_interest_terms": None,
                "warranty_terms": None,
                "expected_delivery_at": None,
                "memo": None,
                "source_code": None,
                "stage_position": position,
                "deleted_at": None,
                "created_at": self.at(opened, 9),
                "updated_at": self.at(opened, 9),
            }

            quoted = contracted = None
            if position >= self.QUOTE_FROM:
                quoted = renewal_quoted or opened + timedelta(days=10 + _rand(f"q:{key}", 12))
                row |= {
                    "quote_no": f"SL-QT-{key}",
                    "quote_issued_on": quoted,
                    "quote_valid_until": quoted + timedelta(days=30),
                    "quote_status_id": self.quote_status[
                        "completed" if position > self.QUOTE_FROM else "sent"
                    ],
                    "quote_amount": amount,
                    "quote_delivery_terms": self.DELIVERY,
                }
            if position >= self.CONTRACT_FROM and stage_code != "closed_cancelled":
                row |= {
                    "contract_no": f"SL-CT-{key}",
                    "contract_status_id": self.contract_status[
                        "completed" if position >= self.SIGNED_FROM else "reviewing"
                    ],
                    "contract_payment_terms": self.PAYMENT,
                    "contract_late_interest_terms": self.LATE_INTEREST,
                    "warranty_terms": self.WARRANTY,
                }
            if position >= self.SIGNED_FROM and stage_code != "closed_cancelled":
                contracted = renewal_signed or quoted + timedelta(days=8 + _rand(f"c:{key}", 14))
                # 서명일이 기준일을 넘으면 미래에 체결된 계약이 된다. 오늘로 당긴다.
                contracted = min(contracted, self.base)
                row |= {
                    "contract_signed_on": contracted,
                    "contract_ends_on": renewal_ends or contracted + timedelta(days=365),
                    "contract_amount": amount,
                    "expected_delivery_at": self.at(contracted + timedelta(days=28), 14),
                }
            if stage_code == "closed_cancelled":
                row["closed_on"] = min(
                    (quoted or opened) + timedelta(days=20 + _rand(f"x:{key}", 25)), self.base
                )
            if stage_code == "order_delivered":
                row["closed_on"] = min(contracted + timedelta(days=30), self.base)

            rows.append(row)
            self.deals.append(
                {
                    "id": deal_id,
                    "key": key,
                    "stage": stage_code,
                    "position": position,
                    "outcome": outcome,
                    "owner": owner,
                    "contact": contact,
                    "product_name": product_name,
                    "product_id": product_id,
                    "quantity": quantity,
                    "amount": amount,
                    "opened": opened,
                    "quoted": quoted,
                    "contracted": contracted,
                }
            )

            # 견적 품목. 대표 제품에 소모품을 얹어 실제 견적처럼 만든다.
            items.append(
                {
                    "id": self.sid("deal_item", f"{key}#0"),
                    "sales_deal_id": deal_id,
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "position": 0,
                }
            )
            if position >= self.QUOTE_FROM:
                extra = _pick(
                    f"extra:{key}",
                    tuple(n for n, _ in self.products.items() if n.startswith("LC-")),
                )
                extra_id, extra_price = self.products[extra]
                items.append(
                    {
                        "id": self.sid("deal_item", f"{key}#1"),
                        "sales_deal_id": deal_id,
                        "product_id": extra_id,
                        "quantity": quantity * 2,
                        "unit_price": extra_price,
                        "position": 1,
                    }
                )

        await guard_team(self.db, SalesDeal, [r["id"] for r in rows], self.team_id)
        await upsert_many(self.db, SalesDeal, rows)
        await upsert_many(self.db, SalesDealItem, items)
        self.bump("deal", len(rows))
        self.bump("deal_item", len(items))

    # --- 08 발주

    def _ordered_deals(self) -> list[dict[str, Any]]:
        """계약 서명이 끝난 딜. 발주와 고객불만이 여기에서만 나온다."""
        return [d for d in self.deals if d["contracted"] is not None]

    async def seed_orders(self) -> None:
        rows, items = [], []
        pool = self._ordered_deals()
        if len(pool) < ORDERS:
            raise SystemExit(f"발주를 붙일 계약 완료 딜이 {len(pool)}건뿐입니다.")

        for index, deal in enumerate(pool[:ORDERS]):
            key = f"O{index:04d}"
            order_id = self.sid("order", key)
            ordered = deal["contracted"] + timedelta(days=2 + _rand(f"po:{key}", 12))
            ordered = min(ordered, self.base)
            # 납품 완료 딜은 이미 들어왔고, 발주 진행 딜은 아직 오는 중이다.
            if deal["stage"] == "order_delivered":
                status, receipt = "delivered", ordered + timedelta(days=14)
            elif deal["stage"] == "order_in_progress":
                status, receipt = "in_production", self.day(2 + _rand(f"rc:{key}", 20))
            else:
                status, receipt = "order_received", ordered + timedelta(days=21)

            rows.append(
                {
                    "id": order_id,
                    "team_id": self.team_id,
                    "order_no": f"SL-PO-{key}",
                    "sales_deal_id": deal["id"],
                    "supplier_name": _pick(f"sup:{key}", SUPPLIERS),
                    "purchase_order_status_id": self.order_status[status],
                    "ordered_on": ordered,
                    "due_on": ordered + timedelta(days=30),
                    "expected_receipt_on": receipt,
                    "request_department": "영업팀",
                    "cooperation_department": "생산팀",
                    "created_by_member_id": self.members[deal["owner"]],
                    "expected_customer_company_id": deal["contact"]["company_id"],
                    "memo": None,
                    "deleted_at": None,
                    "created_at": self.at(ordered, 11),
                    "updated_at": self.at(ordered, 11),
                }
            )
            items.append(
                {
                    "id": self.sid("order_item", f"{key}#0"),
                    "purchase_order_id": order_id,
                    "product_id": deal["product_id"],
                    "quantity": deal["quantity"],
                    "unit_price": self.products[deal["product_name"]][1],
                    "position": 0,
                }
            )
            deal["order_id"] = order_id

        await guard_team(self.db, PurchaseOrder, [r["id"] for r in rows], self.team_id)
        await upsert_many(self.db, PurchaseOrder, rows)
        await upsert_many(self.db, PurchaseOrderItem, items)
        self.bump("order", len(rows))
        self.bump("order_item", len(items))

    # --- 09 활동

    # 단계별 활동 흐름. (분류, 태그, 제목, 딜 개설일로부터의 일수 비율)
    FLOW = (
        ("call", "first_call", "첫 통화"),
        ("visit", "meeting", "첫 방문 미팅"),
        ("call", "demo_requested", "데모 요청 협의"),
        ("demo", "demo_in_progress", "제품 시연"),
        ("visit", "demo_completed", "시연 결과 리뷰"),
        ("visit", "quote_completed", "견적서 전달"),
        ("call", "meeting", "가격·조건 협의"),
        ("visit", "contract_completed", "계약 체결"),
        ("delivery", "delivery_completed", "납품·설치"),
        ("education", "product_training", "사용 교육"),
    )

    async def seed_activities(self) -> None:
        rows = []

        def add(
            key: str,
            owner: str,
            when: datetime,
            title: str,
            category: str,
            tag: str | None,
            *,
            deal: dict[str, Any] | None,
            done: bool,
            note: str | None = None,
        ) -> dict[str, Any]:
            activity_id = self.sid("activity", key)
            contact = deal["contact"] if deal else None
            row = {
                "id": activity_id,
                "team_id": self.team_id,
                "owner_member_id": self.members[owner],
                "customer_contact_id": contact["id"] if contact else None,
                "end_user_contact_id": None,
                "activity_category_id": self.category[category],
                "activity_action_tag_id": self.tag[tag] if tag else None,
                "title": title,
                "starts_at": when,
                "ends_at": when + timedelta(hours=1),
                "all_day": False,
                "due_at": None,
                "location": contact["company"] if contact else None,
                "completed_at": when + timedelta(hours=1) if done else None,
                "note": note,
                "deleted_at": None,
                "created_at": when - timedelta(days=3),
                "updated_at": when,
                "product_id": deal["product_id"] if deal else None,
                "sales_deal_id": deal["id"] if deal else None,
                "purchase_order_id": deal.get("order_id") if deal else None,
            }
            rows.append(row)
            record = {
                "id": activity_id,
                "owner": owner,
                "date": when.date(),
                "title": title,
                "deal": deal,
                "done": done,
            }
            # 실제로 다녀온 방문만 담당자의 '방문' 표시가 된다. 오늘 일정은 아직 진행 중이라
            # 세지 않는다. seed_contact_rollup 이 이 집합을 되짚어 쓴다.
            if done and category == "visit" and contact and when.date() < self.base:
                self.visited_contacts.add(contact["id"])
            if done:
                self.by_day.setdefault((owner, when.date()), []).append(record)
            return record

        # 딜마다 단계까지의 흐름을 과거에 깔고, 진행 중인 딜에는 다음 일정을 미래에 둔다.
        for deal in self.deals:
            steps = min(deal["position"] + 2, len(self.FLOW))
            opened = deal["opened"]
            end = deal["contracted"] or deal["quoted"] or self.base
            total = max((end - opened).days, steps)
            for step in range(steps):
                category, tag, title = self.FLOW[step]
                when_date = opened + timedelta(days=total * step // max(steps - 1, 1))
                # 이미 끝난 단계다. 오늘 칸은 '진행 중' 일정만 쓰므로 어제까지로 민다.
                if when_date >= self.base:
                    when_date = self.base - timedelta(days=1)
                hour = 9 + _rand(f"h:{deal['key']}:{step}", 8)
                add(
                    f"{deal['key']}#{step}",
                    deal["owner"],
                    self.at(when_date, hour),
                    f"{deal['contact']['company']} {title}",
                    category,
                    tag,
                    deal=deal,
                    done=True,
                    note=f"{deal['product_name']} {deal['quantity']}대 건",
                )

            # 진행 중인 딜은 앞으로 할 일이 남아 있다. 9~10월 일정이 여기서 나온다.
            if deal["outcome"] == "in_progress":
                for slot in range(2):
                    ahead = 1 + _rand(f"f:{deal['key']}:{slot}", FUTURE_DAYS - 1)
                    add(
                        f"{deal['key']}~{slot}",
                        deal["owner"],
                        self.at(self.day(ahead), 10 + _rand(f"fh:{deal['key']}:{slot}", 7)),
                        f"{deal['contact']['company']} 후속 미팅",
                        "visit",
                        "meeting",
                        deal=deal,
                        done=False,
                    )

        # 오늘 일정. 지난 시각 몇 건만 완료로 두고 나머지는 진행 중이다.
        for slot, deal in enumerate(self.deals[:18]):
            add(
                f"today#{slot}",
                deal["owner"],
                self.at(self.base, 9 + slot % 9),
                f"{deal['contact']['company']} 방문 상담",
                "visit",
                "meeting",
                deal=deal,
                done=slot < 6,
            )

        await guard_team(self.db, Activity, [r["id"] for r in rows[:BATCH]], self.team_id)
        await upsert_many(self.db, Activity, rows)
        self.bump("activity", len(rows))

    # --- 09-b 담당자 되짚기

    # 딜 단계에서 고객 상태로. 단계가 뒤일수록 관계가 진전됐다는 뜻이다.
    # 니즈 검증(position 0)뿐이면 아직 '신규' 가 맞다.
    STATUS_BY_POSITION = ((5, "contracted"), (3, "negotiation"), (1, "proposal"))

    async def seed_contact_rollup(self) -> None:
        """딜과 활동이 생긴 뒤에 담당자의 상태·방문·메모·등록일을 되짚어 쓴다.

        담당자 행은 딜이 참조하므로 딜보다 먼저 들어가야 한다. 그래서 처음 넣을 때는
        무엇을 진행했는지 알 수 없고, 상태가 전부 '신규' 이고 방문 표시도 없이 남는다.
        여기서 이미 만든 행(self.contact_rows)을 고쳐 같은 id 로 다시 넣는다.
        """
        # 담당자별로 가장 앞선 단계의 딜과 가장 이른 개설일을 모은다. 취소된 딜은 순서상
        # 맨 뒤(position 8)라 그대로 비교하면 성사된 계약을 덮는다. 다른 딜이 없을 때만 쓴다.
        best: dict[UUID, dict[str, Any]] = {}
        earliest: dict[UUID, date] = {}

        def rank(deal: dict[str, Any]) -> tuple[bool, int]:
            return deal["outcome"] != "cancelled", deal["position"]

        for deal in self.deals:
            contact_id = deal["contact"]["id"]
            current = best.get(contact_id)
            if current is None or rank(deal) > rank(current):
                best[contact_id] = deal
            if contact_id not in earliest or deal["opened"] < earliest[contact_id]:
                earliest[contact_id] = deal["opened"]

        for contact_id, row in self.contact_rows.items():
            row["visited"] = contact_id in self.visited_contacts

            deal = best.get(contact_id)
            if deal is not None:
                code = "new"
                if deal["outcome"] == "cancelled":
                    code = "on_hold"
                else:
                    for floor, name in self.STATUS_BY_POSITION:
                        if deal["position"] >= floor:
                            code = name
                            break
                row["customer_contact_status_id"] = self.status[code]

                if _rand(f"mm:{contact_id}", 100) < 45:
                    memo = _pick(f"memo:{contact_id}", data.CONTACT_MEMOS)
                    row["memo"] = f"{memo} {deal['product_name']} 건 진행 중."

            # 갱신 코호트의 딜은 1년 전에 열린다. 담당자가 그보다 늦게 등록될 수 없다.
            opened = earliest.get(contact_id)
            if opened is not None:
                row["registered_at"] = min(
                    row["registered_at"], self.at(opened - timedelta(days=10), 10)
                )

        await upsert_many(self.db, CustomerContact, list(self.contact_rows.values()))
        self.bump("contact_rollup", len(self.contact_rows))

    # --- 10 고객불만

    async def seed_supports(self) -> None:
        pool = self._ordered_deals()
        if len(pool) < len(data.SUPPORTS):
            raise SystemExit(
                f"고객불만 {len(data.SUPPORTS)}건에 붙일 계약 완료 딜이 {len(pool)}건뿐입니다."
            )

        rows, responses = [], []
        for index, seed in enumerate(data.SUPPORTS):
            deal = pool[index % len(pool)]
            request_id = self.sid("support", seed.key)
            occurred = self.at(self.day(seed.occurred_offset), 10 + _rand(f"oc:{seed.key}", 8))
            registered = occurred + timedelta(hours=1 + _rand(f"rg:{seed.key}", 6))
            rows.append(
                {
                    "id": request_id,
                    "team_id": self.team_id,
                    "customer_company_id": deal["contact"]["company_id"],
                    "sales_deal_id": deal["id"],
                    "assignee_member_id": self.members[deal["owner"]],
                    "title": seed.title,
                    "body": seed.body,
                    "is_urgent": seed.is_urgent,
                    "status_code": seed.status_code,
                    "occurred_at": occurred,
                    "registered_at": registered,
                }
            )
            for step, body in enumerate(seed.responses):
                responses.append(
                    {
                        "id": self.sid("support_response", f"{seed.key}#{step}"),
                        "support_request_id": request_id,
                        "responder_member_id": self.members[deal["owner"]],
                        "body": body,
                        "responded_at": registered + timedelta(days=step + 1, hours=2),
                    }
                )

        await guard_team(self.db, SupportRequest, [r["id"] for r in rows], self.team_id)
        await upsert_many(self.db, SupportRequest, rows)
        await upsert_many(self.db, SupportResponse, responses)
        self.bump("support_request", len(rows))
        self.bump("support_response", len(responses))

    # --- 11~12 보고서

    # 화면이 쓰는 기본 양식과 같아야 저장된 보고서를 열었을 때 항목이 어긋나지 않는다.
    # frontend/src/shared/meetings.ts, reports.ts 를 따른다.
    @staticmethod
    def _field(fid: str, label: str, ftype: str, required: bool, ai: bool) -> dict[str, Any]:
        return {"id": fid, "label": label, "type": ftype, "required": required, "aiFilled": ai}

    @classmethod
    def _template(cls, tid: str, name: str, fields: list[tuple]) -> dict[str, Any]:
        return {
            "id": tid,
            "name": name,
            "owner": "",
            "updated": "",
            "fields": [cls._field(*f) for f in fields],
        }

    def templates(self) -> dict[str, dict[str, Any]]:
        return {
            "meeting": self._template(
                "builtin-meeting",
                "기본 미팅 기록 양식",
                [
                    ("attendees", "참석자", "text", True, True),
                    ("reaction", "고객 반응", "textarea", True, True),
                    ("decision", "결정사항", "textarea", True, True),
                    ("next", "다음 행동 · 기한", "textarea", True, True),
                    ("note", "특이사항", "text", False, False),
                ],
            ),
            "daily": self._template(
                "builtin-daily",
                "기본 일일보고 양식",
                [
                    ("summary", "업무 요약", "textarea", True, True),
                    ("issue", "특이사항 · 이슈", "textarea", False, True),
                    ("next", "내일 계획", "textarea", True, True),
                    ("competitor", "경쟁사 동향", "text", False, False),
                ],
            ),
            "weekly": self._template(
                "builtin-weekly",
                "기본 주간보고 양식",
                [
                    ("result", "주간 성과", "textarea", True, True),
                    ("plan", "다음 주 계획", "textarea", True, True),
                    ("risk", "리스크", "textarea", False, True),
                ],
            ),
            "monthly": self._template(
                "builtin-monthly",
                "기본 월간보고 양식",
                [
                    ("perf", "월간 실적", "textarea", True, True),
                    ("gap", "목표 대비", "textarea", True, False),
                    ("focus", "다음 달 중점", "textarea", False, True),
                ],
            ),
        }

    def _review(self, key: str, when: date) -> tuple[str, dict[str, Any]]:
        """제출 시점에 따라 검토 상태를 가른다. 최근 것일수록 아직 검토 전이다."""
        age = (self.base - when).days
        roll = _rand(f"rv:{key}", 100)
        if age > 21:
            # 오래된 것도 전부 확정되지는 않는다. 반려되고 방치된 보고서가 실제로 남는다.
            if roll < 78:
                code = "approved"
            elif roll < 88:
                code = "submitted"
            elif roll < 95:
                code = "changes_requested"
            else:
                code = "rejected"
        elif age > 7:
            code = "approved" if roll < 45 else ("changes_requested" if roll < 60 else "submitted")
        else:
            code = "draft" if roll < 30 else ("changes_requested" if roll < 45 else "submitted")
        extra: dict[str, Any] = {"reviewed_by_member_id": None, "reviewed_at": None}
        if code == "approved":
            extra = {
                "reviewed_by_member_id": self.members[data.MANAGER],
                "reviewed_at": self.at(when + timedelta(days=2), 17),
            }
        return code, extra

    async def seed_reports(self) -> None:
        templates = self.templates()
        rows, links = [], []

        def add(
            key: str,
            kind: str,
            owner: str,
            when: date,
            content: dict[str, str],
            *,
            activity_id: UUID | None = None,
            deal_id: UUID | None = None,
            period: tuple[date, date] | None = None,
        ) -> UUID:
            report_id = self.sid("report", key)
            status, review = self._review(key, when)
            rows.append(
                {
                    "id": report_id,
                    "team_id": self.team_id,
                    "author_member_id": self.members[owner],
                    "recipient_member_id": self.members[data.MANAGER],
                    "template_snapshot": templates[kind],
                    "source_activity_id": activity_id,
                    "sales_deal_id": deal_id,
                    "report_kind": kind,
                    "report_date": when,
                    "period_start": period[0] if period else None,
                    "period_end": period[1] if period else None,
                    "status_code": status,
                    "content": content,
                    "transcript": None,
                    "source_snapshot": None,
                    "ai_evidence": None,
                    "note": None,
                    "created_at": self.at(when, 18),
                    "updated_at": self.at(when, 18),
                    **review,
                }
            )
            return report_id

        # 미팅 보고서. 근거 일정이 반드시 있고, 미래 일정에는 절대 붙지 않는다.
        meeting_count = 0
        for (owner, when), records in sorted(
            self.by_day.items(), key=lambda kv: (kv[0][1], kv[0][0])
        ):
            for record in records:
                deal = record["deal"]
                if deal is None or when >= self.base or meeting_count >= 210:
                    continue
                if _rand(f"mk:{record['id']}", 100) >= 45:
                    continue
                add(
                    f"meeting:{record['id']}",
                    "meeting",
                    owner,
                    when,
                    {
                        "attendees": f"{deal['contact']['company']} 담당자, {owner}",
                        "reaction": f"{deal['product_name']} 사양과 단가에 대체로 긍정적.",
                        "decision": f"{record['title']} 진행. 후속 일정 협의.",
                        "next": "다음 주 중 후속 미팅 일정 확정.",
                        "note": "",
                    },
                    activity_id=record["id"],
                    deal_id=deal["id"],
                )
                meeting_count += 1

        # 일일보고서. 그날 실제로 완료한 활동에서 만든다.
        daily_count = 0
        for (owner, when), records in sorted(
            self.by_day.items(), key=lambda kv: (kv[0][1], kv[0][0])
        ):
            if when >= self.base or daily_count >= 150 or len(records) < 2:
                continue
            titles = ", ".join(r["title"] for r in records[:3])
            report_id = add(
                f"daily:{owner}:{when.isoformat()}",
                "daily",
                owner,
                when,
                {
                    "summary": f"{len(records)}건 진행. {titles}.",
                    "issue": "",
                    "next": "후속 방문 일정 조율.",
                    "competitor": "",
                },
            )
            links.extend({"report_id": report_id, "activity_id": r["id"]} for r in records)
            daily_count += 1

        # 주간·월간보고서. 기간과 근거 일정을 함께 남긴다.
        for owner in data.SALES + (data.MANAGER,):
            monday = self.base - timedelta(days=self.base.weekday())
            for back in range(1, 11):
                start = monday - timedelta(weeks=back)
                end = start + timedelta(days=6)
                records = [
                    r
                    for (o, d), items in self.by_day.items()
                    if o == owner and start <= d <= end
                    for r in items
                ]
                if not records:
                    continue
                report_id = add(
                    f"weekly:{owner}:{start.isoformat()}",
                    "weekly",
                    owner,
                    end,
                    {
                        "result": f"{len(records)}건의 고객 접촉을 진행했다.",
                        "plan": "진행 중인 견적 건의 회신을 확인한다.",
                        "risk": "",
                    },
                    period=(start, end),
                )
                links.extend({"report_id": report_id, "activity_id": r["id"]} for r in records[:8])

            # 이번 달은 아직 끝나지 않았으므로 월간보고서를 만들지 않는다.
            month_end = self.base.replace(day=1) - timedelta(days=1)
            for back in range(3):
                end = month_end
                for _ in range(back):
                    end = end.replace(day=1) - timedelta(days=1)
                start = end.replace(day=1)
                records = [
                    r
                    for (o, d), items in self.by_day.items()
                    if o == owner and start <= d <= end
                    for r in items
                ]
                if not records:
                    continue
                report_id = add(
                    f"monthly:{owner}:{start.isoformat()}",
                    "monthly",
                    owner,
                    end,
                    {
                        "perf": f"{len(records)}건 활동, 진행 딜 기준 실적을 정리했다.",
                        "gap": "월 목표 대비 진행률을 확인했다.",
                        "focus": "다음 달 신규 고객사 접촉을 늘린다.",
                    },
                    period=(start, end),
                )
                links.extend({"report_id": report_id, "activity_id": r["id"]} for r in records[:8])

        await guard_team(self.db, Report, [r["id"] for r in rows[:BATCH]], self.team_id)
        await upsert_many(self.db, Report, rows)
        await link(self.db, ReportActivity, links)
        self.bump("report", len(rows))
        self.bump("report_activity", len(links))

    # --- 13 공지와 지시사항

    async def seed_notices(self) -> None:
        rows, targets = [], []
        for seed in data.NOTICES + data.DIRECTIVES:
            notice_id = self.sid("notice", seed.key)
            start = self.day(seed.start_offset)
            due = self.day(seed.due_offset) if seed.due_offset is not None else None
            rows.append(
                {
                    "id": notice_id,
                    "team_id": self.team_id,
                    "author_member_id": self.members[data.MANAGER],
                    "type": seed.type,
                    "tag": seed.tag,
                    "title": seed.title,
                    "body": seed.body,
                    "image_storage_key": None,
                    "image_alt": None,
                    "published_at": self.at(start, 9),
                    "due_at": self.at(due, 18) if due else None,
                    "due_text": f"{due.month}월 {due.day}일까지" if due else None,
                    "display_start_date": start,
                    "display_end_date": (
                        self.day(seed.end_offset) if seed.end_offset is not None else None
                    ),
                    "is_hidden": False,
                    "sort_order": seed.sort_order,
                    "deleted_at": None,
                    "updated_at": self.at(start, 9),
                }
            )
            targets.extend(
                {
                    "notice_id": notice_id,
                    "member_id": self.members[name],
                    "created_at": self.at(start, 9, slot),
                }
                for slot, name in enumerate(seed.targets)
            )

        await guard_team(self.db, Notice, [r["id"] for r in rows], self.team_id)
        await upsert_many(self.db, Notice, rows)
        await link(self.db, NoticeTarget, targets)
        self.bump("notice", len(rows))
        self.bump("notice_target", len(targets))

    async def seed_directive_work(self) -> None:
        """지시사항을 받은 사람의 일정과 보고서를 만든다.

        notice 에서 activity 로 가는 외래키가 스키마에 없다. 날짜와 담당자, 본문 인용으로만
        잇는다. 기한이 지난 지시는 일정과 보고서가 끝나 있고, 미래 지시는 일정만 있다.
        """
        templates = self.templates()
        activities, reports = [], []
        for seed in data.DIRECTIVES:
            for slot, name in enumerate(seed.targets):
                key = f"{seed.key}#{slot}"
                when = self.day(seed.start_offset + 1 + _rand(f"dw:{key}", 3))
                done = when < self.base
                activity_id = self.sid("activity", f"directive:{key}")
                note = f"지시사항: {seed.title}"
                if seed.due_offset is not None:
                    due_day = self.day(seed.due_offset)
                    note += f" (기한 {due_day.month}월 {due_day.day}일)"
                activities.append(
                    {
                        "id": activity_id,
                        "team_id": self.team_id,
                        "owner_member_id": self.members[name],
                        "customer_contact_id": None,
                        "end_user_contact_id": None,
                        "activity_category_id": self.category["call"],
                        "activity_action_tag_id": self.tag["internal_meeting"],
                        "title": f"[지시] {seed.title}",
                        "starts_at": self.at(when, 9),
                        "ends_at": self.at(when, 10),
                        "all_day": False,
                        "due_at": (
                            self.at(self.day(seed.due_offset), 18)
                            if seed.due_offset is not None
                            else None
                        ),
                        "location": None,
                        "completed_at": self.at(when, 10) if done else None,
                        "note": note,
                        "deleted_at": None,
                        "created_at": self.at(self.day(seed.start_offset), 9),
                        "updated_at": self.at(when, 10),
                        "product_id": None,
                        "sales_deal_id": None,
                        "purchase_order_id": None,
                    }
                )
                # 미래 지시에는 보고서를 만들지 않는다.
                if not done:
                    continue
                status, review = self._review(f"dr:{key}", when)
                reports.append(
                    {
                        "id": self.sid("report", f"directive:{key}"),
                        "team_id": self.team_id,
                        "author_member_id": self.members[name],
                        "recipient_member_id": self.members[data.MANAGER],
                        "template_snapshot": templates["daily"],
                        "source_activity_id": activity_id,
                        "sales_deal_id": None,
                        "report_kind": "daily",
                        "report_date": when,
                        "period_start": None,
                        "period_end": None,
                        "status_code": status,
                        "content": {
                            "summary": f"지시사항 '{seed.title}' 을 처리했습니다.",
                            "issue": "",
                            "next": "후속 확인이 필요하면 회신하겠습니다.",
                            "competitor": "",
                        },
                        "transcript": None,
                        "source_snapshot": None,
                        "ai_evidence": None,
                        "note": None,
                        "created_at": self.at(when, 18),
                        "updated_at": self.at(when, 18),
                        **review,
                    }
                )

        await upsert_many(self.db, Activity, activities)
        await upsert_many(self.db, Report, reports)
        self.bump("activity", len(activities))
        self.bump("report", len(reports))

    # --- 14 매출 목표

    # 담당자·월당 목표를 붙일 고객사 수. 매출 분석이 회사별·지역별로 접어 보여 준다.
    TARGET_COMPANIES = 3

    async def seed_targets(self) -> None:
        """담당자가 실제로 딜을 가진 고객사에만 월 목표를 붙인다.

        고객사를 무관하게 고르면 '목표는 있는데 실적 0, 실적은 있는데 목표 0' 이 되어
        회사별·지역별 달성률이 전부 헛돈다.
        """
        # (담당자, 회사) -> 그 회사에서 확정된 계약 금액. 목표를 실적에 견줄 기준이다.
        owned: dict[str, dict[UUID, int]] = {}
        for deal in self.deals:
            company_id = deal["contact"]["company_id"]
            by_company = owned.setdefault(deal["owner"], {})
            confirmed = deal["amount"] if deal["outcome"] == "confirmed" else 0
            by_company[company_id] = by_company.get(company_id, 0) + confirmed

        rows = []
        first = self.base.replace(day=1)
        for back in range(6):
            month = first
            for _ in range(back):
                month = (month - timedelta(days=1)).replace(day=1)
            for name in data.SALES + (data.MANAGER,):
                # 팀장은 자기 딜이 없다. 그래도 목표는 있어야 대시보드 합계가 선다.
                pool = sorted(owned.get(name, {}).items(), key=lambda kv: (-kv[1], kv[0].bytes))
                if not pool:
                    pool = [
                        (company_id, 0) for _, company_id in self.companies[: self.TARGET_COMPANIES]
                    ]
                # 달마다 다른 회사를 본다. 6개월이 전부 같은 세 곳이면 표가 굳는다.
                # 회사가 모자라면 그만큼만 고른다. 같은 (담당자·회사·월) 은 유니크 제약이다.
                count = min(self.TARGET_COMPANIES, len(pool))
                start = back * self.TARGET_COMPANIES % len(pool)
                chosen = (pool * 2)[start : start + count]
                for company_id, actual in chosen:
                    key = f"{name}:{month.isoformat()}:{company_id}"
                    # 몇 칸은 일부러 비운다. '목표 미설정' 상태도 화면에서 보여야 한다.
                    if _rand(f"tg:{key}", 10) < 1:
                        continue
                    if actual:
                        # 달성률이 70~140% 사이로 흩어져야 잘한 달과 못한 달이 갈린다.
                        amount = round(actual * (70 + _rand(f"amt:{key}", 70)) / 100 / 1_000_000)
                        amount = max(amount, 1) * 1_000_000
                    else:
                        amount = (15 + _rand(f"amt:{key}", 40)) * 1_000_000
                    rows.append(
                        {
                            "id": self.sid("target", key),
                            "owner_member_id": self.members[name],
                            "customer_company_id": company_id,
                            "target_month": month,
                            "target_amount": amount,
                        }
                    )
        await upsert_many(self.db, SalesTarget, rows)
        self.bump("sales_target", len(rows))

    # --- 15 자료실

    async def seed_documents(self) -> None:
        """자료실 자료와 첨부 .docx 를 만든다.

        스키마에 source_url·published_at 컬럼이 없어 출처는 description 과 tags 에 보존한다.
        첨부는 원문 복제가 아니라 출처 링크가 달린 요약 메모다.
        """
        from app.services import storage

        if not self.with_documents:
            print("  자료실을 건너뜁니다.")
            return

        open_deals = [d for d in self.deals if d["outcome"] == "in_progress"]
        rows, files = [], []
        for index, seed in enumerate(data.DOCUMENTS):
            document_id = self.sid("document", seed.key)
            created = self.at(self.day(-60 + index * 4), 11)
            description = (
                " ".join(seed.summary)
                + f" 출처: {seed.source} ({seed.published}). {seed.source_url}"
            )
            product_id = self.products[seed.link_product][0] if seed.link_product else None
            # document_product_or_deal_check: 제품과 딜을 동시에 지정할 수 없다.
            deal_id = open_deals[index % len(open_deals)]["id"] if seed.link_deal else None

            rows.append(
                {
                    "id": document_id,
                    "team_id": self.team_id,
                    "created_by_member_id": self.members[data.MANAGER],
                    "document_no": f"SL-DOC-{seed.key}",
                    "category_code": seed.category_code,
                    "title": seed.title,
                    "description": description,
                    "customer_company_id": None,
                    "sales_deal_id": deal_id,
                    "purchase_order_id": None,
                    "product_id": product_id,
                    "tags": [
                        f"출처:{seed.source}",
                        f"발행:{seed.published}",
                        f"url:{seed.source_url}",
                    ],
                    "created_at": created,
                }
            )

            blob = build_docx(
                seed.title,
                [
                    data.DISCLAIMER,
                    "",
                    *seed.summary,
                    "",
                    f"출처: {seed.source} ({seed.published})",
                    seed.source_url,
                ],
            )
            storage_key = f"{self.team_id}/{SEED_TAG}/{seed.key}.docx"
            await storage.upload(storage_key=storage_key, content=blob, media_type=MEDIA_TYPE)
            self.uploaded.append(storage_key)
            files.append(
                {
                    "id": self.sid("file", seed.key),
                    "report_id": None,
                    "document_id": document_id,
                    "version_no": 1,
                    "file_name": f"{seed.title}_요약.docx",
                    "storage_key": storage_key,
                    "media_type": MEDIA_TYPE,
                    "byte_size": len(blob),
                    "processing_status": "completed",
                    "extracted_text": None,
                    "uploaded_by_member_id": self.members[data.MANAGER],
                    "note": None,
                    "uploaded_at": created,
                }
            )

        await guard_team(self.db, Document, [r["id"] for r in rows], self.team_id)
        await upsert_many(self.db, Document, rows)
        await upsert_many(self.db, File, files)
        self.bump("document", len(rows))
        self.bump("file", len(files))

    async def run(self) -> dict[str, int]:
        await self.load_configuration()
        await self.seed_products()
        await self.seed_companies()
        await self.seed_contacts()
        await self.seed_deals()
        await self.seed_orders()
        await self.seed_activities()
        await self.seed_contact_rollup()
        await self.seed_supports()
        await self.seed_reports()
        await self.seed_notices()
        await self.seed_directive_work()
        await self.seed_targets()
        await self.seed_documents()
        return self.counts


# ---------------------------------------------------------------- reset

# 삭제는 생성의 역순이다. 자식이 먼저 사라져야 부모를 지울 수 있다.
# team·member·config 룩업·파이프라인은 남긴다. 계정은 고정 자산이고,
# 룩업을 지우면 남은 딜이 참조하는 대상이 사라진다.
RESET_ORDER = (
    (File, "file"),
    (Document, "document"),
    (SalesTarget, "sales_target"),
    (NoticeTarget, "notice_target"),
    (Notice, "notice"),
    (ReportActivity, "report_activity"),
    (Report, "report"),
    (SupportResponse, "support_response"),
    (SupportRequest, "support_request"),
    (Activity, "activity"),
    (PurchaseOrderItem, "purchase_order_item"),
    (PurchaseOrder, "purchase_order"),
    (SalesDealItem, "sales_deal_item"),
    (SalesDeal, "sales_deal"),
    (CustomerContactAssignee, "customer_contact_assignee"),
    (CustomerContact, "customer_contact"),
    (CustomerCompany, "customer_company"),
    (Product, "product"),
)


async def reset_demo_data(db: AsyncSession) -> dict[str, int]:
    """이 시드가 만든 행만 지운다. 다른 팀과 손으로 넣은 데이터는 건드리지 않는다."""
    from app.services import storage

    # 지우기 전에 스토리지 키를 모아 둔다. 행이 사라지면 무엇을 지울지 알 수 없다.
    keys = [
        row[0]
        for row in (
            await db.execute(
                select(File.storage_key).where(File.storage_key.like(f"{TEAM_ID}/{SEED_TAG}/%"))
            )
        ).all()
    ]

    removed: dict[str, int] = {}
    for model, label in RESET_ORDER:
        # 연결 표는 id 가 없어 부모 컬럼으로 지운다. 나머지는 팀 범위로 지운다.
        if model is CustomerContactAssignee:
            scope = model.customer_contact_id.in_(
                select(CustomerContact.id)
                .join(CustomerCompany, CustomerCompany.id == CustomerContact.company_id)
                .where(CustomerCompany.team_id == TEAM_ID)
            )
        elif model is NoticeTarget:
            scope = model.notice_id.in_(select(Notice.id).where(Notice.team_id == TEAM_ID))
        elif model is ReportActivity:
            scope = model.report_id.in_(select(Report.id).where(Report.team_id == TEAM_ID))
        elif model is SalesTarget:
            scope = model.owner_member_id.in_(select(Member.id).where(Member.team_id == TEAM_ID))
        elif model is SalesDealItem:
            scope = model.sales_deal_id.in_(
                select(SalesDeal.id).where(SalesDeal.team_id == TEAM_ID)
            )
        elif model is PurchaseOrderItem:
            scope = model.purchase_order_id.in_(
                select(PurchaseOrder.id).where(PurchaseOrder.team_id == TEAM_ID)
            )
        elif model is SupportResponse:
            scope = model.support_request_id.in_(
                select(SupportRequest.id).where(SupportRequest.team_id == TEAM_ID)
            )
        elif model is CustomerContact:
            scope = model.company_id.in_(
                select(CustomerCompany.id).where(CustomerCompany.team_id == TEAM_ID)
            )
        elif model is File:
            scope = model.document_id.in_(select(Document.id).where(Document.team_id == TEAM_ID))
        else:
            scope = model.team_id == TEAM_ID
        result = await db.execute(delete(model).where(scope))
        if result.rowcount:
            removed[label] = result.rowcount

    for key in keys:
        try:
            await storage.remove(storage_key=key)
        except Exception as error:  # noqa: BLE001 - 파일이 없어도 계속 지운다
            print(f"  스토리지 {key} 삭제 실패: {type(error).__name__}")
    if keys:
        removed["storage_object"] = len(keys)
    return removed


# ---------------------------------------------------------------- 진입점


def parse_base_date(raw: str | None) -> date:
    if raw is None:
        return datetime.now(SEOUL).date()
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise SystemExit(f"--base-date 는 YYYY-MM-DD 형식이어야 합니다: {raw}") from error


async def seed(*, base_date: date, reset: bool, dry_run: bool, with_documents: bool) -> None:
    # create_confirmed_user 는 로컬 전용이다. 운영 DB 에 데모 계정을 만들지 않는다.
    if settings.app_env == "production":
        raise SystemExit("운영 환경에서는 실행할 수 없습니다. APP_ENV 를 확인해 주세요.")

    print(f"팀 {TEAM_NAME} ({TEAM_ID})")
    past = base_date - timedelta(days=PAST_DAYS)
    future = base_date + timedelta(days=FUTURE_DAYS)
    print(f"기준일 {base_date.isoformat()}  과거 {past} ~ 미래 {future}")
    if dry_run:
        print("--dry-run: 저장하지 않습니다. 계정 생성과 파일 업로드도 건너뜁니다.")

    try:
        async with get_sessionmaker()() as db, db.begin():
            members, missing = await ensure_team_and_members(db, dry_run=dry_run)
            if missing:
                print("\n다음 계정이 아직 없습니다. --dry-run 은 계정을 만들지 않습니다.")
                for email in missing:
                    print(f"  - {email}")
                print("--dry-run 없이 한 번 실행하면 계정을 만들고 데이터까지 넣습니다.")
                raise _DryRun
            if reset:
                removed = await reset_demo_data(db)
                total = sum(removed.values())
                print(f"  reset: {total}건 삭제" + (f" {removed}" if removed else ""))

            seeder = Seeder(db, members, base_date, with_documents=with_documents and not dry_run)
            counts = await seeder.run()

            print("\n=== 생성 결과 ===")
            for label, value in counts.items():
                print(f"  {label:24} {value:>6}")

            failures = await validate(db, base_date)
            if dry_run:
                raise _DryRun
    except _DryRun:
        print("\n--dry-run 이므로 아무것도 저장하지 않았습니다.")
        return

    if failures:
        raise SystemExit(f"\n검증 {failures}건 실패. 시드를 성공으로 보지 않습니다.")
    print("\n검증을 모두 통과했습니다.")


async def validate(db: AsyncSession, base_date: date) -> int:
    """생성 직후 정합성을 확인한다. verify_demo_dataset 과 같은 검사를 쓴다."""
    from scripts.verify_demo_dataset import run_checks

    print("\n=== 정합성 검사 ===")
    return await run_checks(db, TEAM_ID, base_date)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-date", help="기준일 YYYY-MM-DD. 기본값은 실행일입니다.")
    parser.add_argument(
        "--reset", action="store_true", help="이 시드가 만든 행을 지우고 다시 만듭니다."
    )
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 봅니다.")
    parser.add_argument(
        "--skip-documents", action="store_true", help="자료실과 파일 업로드를 건너뜁니다."
    )
    parser.add_argument("--yes", action="store_true", help="--reset 확인을 건너뜁니다.")
    args = parser.parse_args(argv)

    base_date = parse_base_date(args.base_date)

    # 기준일만 바꿔 다시 넣으면 날짜 축만 움직여 계약일과 발주일이 어긋난다.
    if args.base_date and not args.reset and not args.dry_run:
        raise SystemExit(
            "--base-date 를 바꿀 때는 --reset 이 함께 필요합니다. "
            "날짜만 옮기면 계약·발주·보고서 상태가 어긋납니다."
        )
    if args.reset and not args.yes and not args.dry_run:
        answer = input(f"{TEAM_NAME} 의 시드 데이터를 지우고 다시 만듭니다. 계속할까요? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            raise SystemExit("취소했습니다.")

    asyncio.run(
        seed(
            base_date=base_date,
            reset=args.reset,
            dry_run=args.dry_run,
            with_documents=not args.skip_documents,
        )
    )


if __name__ == "__main__":
    main()
