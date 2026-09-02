"""DB 없이 시더가 만드는 행을 검사한다. 공유 DB 에 쓰기 전에 돌린다.

Seeder 를 그대로 쓰되 DB 접근만 가로채 만들어진 행을 모은다. 수량·날짜 불변식·중복을
확인하므로 시더를 고친 뒤 여기서 먼저 걸러낼 수 있다. 기준일을 바꿔 돌려 보면 실행일이
달라져도 구조가 유지되는지 알 수 있다.

    uv run python -m scripts.demo.check_offline               # 오늘 기준
    uv run python -m scripts.demo.check_offline 2026-12-25    # 기준일 지정
"""

import asyncio
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from scripts import seed_demo_dataset as seeder_module
from scripts.demo import data

SEOUL = ZoneInfo("Asia/Seoul")

# seed_demo_auth.DEFAULT_PIPELINE_STAGES 와 같은 순서·결과값이어야 한다.
STAGE_DEFS = (
    ("needs_validation", "in_progress", 0),
    ("product_demo", "in_progress", 1),
    ("quote_sent", "in_progress", 2),
    ("contract_sent", "in_progress", 3),
    ("contract_review", "in_progress", 4),
    ("contract_completed", "confirmed", 5),
    ("order_in_progress", "confirmed", 6),
    ("order_delivered", "confirmed", 7),
    ("closed_cancelled", "cancelled", 8),
)

LOOKUPS = {
    "status": ("new", "proposal", "negotiation", "contracted", "on_hold"),
    "category": ("visit", "demo", "education", "call", "delivery", "conference"),
    "tag": (
        "first_call",
        "meeting",
        "demo_requested",
        "demo_in_progress",
        "demo_completed",
        "quote_completed",
        "contract_completed",
        "product_training",
        "delivery_completed",
        "internal_meeting",
        "conference",
    ),
    "deal_type": ("new_installation", "expansion", "renewal", "maintenance", "consumables_supply"),
    "order_status": (
        "order_received",
        "dispatch_request_completed",
        "in_production",
        "stock_received",
        "delivered",
        "cancelled",
    ),
    "quote_status": ("drafting", "reviewing", "sent", "negotiating", "completed"),
    "contract_status": ("drafting", "reviewing", "negotiating", "signed", "completed"),
}


class _StubDB:
    """Seeder 가 들고 있기만 하고 직접 쓰지는 않는다. 쓰면 그 자리에서 드러나야 한다."""

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("check_offline 은 DB 에 접근하지 않는다")


async def collect(base: date) -> tuple[dict[str, list[dict[str, Any]]], Any]:
    """시더를 돌려 테이블별 행을 모은다. 실제 저장은 하지 않는다.

    룩업 id 를 봐야 하는 검사가 있어 시더 자신도 함께 돌려준다.
    """
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def one(_db: Any, model: Any, values: dict[str, Any]) -> None:
        rows[model.__tablename__].append(values)

    async def many(_db: Any, model: Any, values: list[dict[str, Any]]) -> None:
        rows[model.__tablename__].extend(values)

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    original = (
        seeder_module.upsert,
        seeder_module.upsert_many,
        seeder_module.link,
        seeder_module.guard_team,
    )
    seeder_module.upsert = one
    seeder_module.upsert_many = many
    seeder_module.link = many
    seeder_module.guard_team = noop
    try:
        members = {member.key: uuid4() for member in data.MEMBERS}
        seeder = seeder_module.Seeder(_StubDB(), members, base, with_documents=False)
        for field, codes in LOOKUPS.items():
            setattr(seeder, field, {code: uuid4() for code in codes})
        seeder.pipeline_id = uuid4()
        seeder.stages = {code: (uuid4(), outcome, pos) for code, outcome, pos in STAGE_DEFS}

        for step in (
            seeder.seed_products,
            seeder.seed_companies,
            seeder.seed_contacts,
            seeder.seed_deals,
            seeder.seed_orders,
            seeder.seed_activities,
            seeder.seed_contact_rollup,
            seeder.seed_supports,
            seeder.seed_reports,
            seeder.seed_notices,
            seeder.seed_directive_work,
            seeder.seed_targets,
            seeder.seed_documents,
        ):
            await step()
    finally:
        (
            seeder_module.upsert,
            seeder_module.upsert_many,
            seeder_module.link,
            seeder_module.guard_team,
        ) = original
    return rows, seeder


def report(base: date, rows: dict[str, list[dict[str, Any]]], seeder: Any) -> list[str]:
    failures: list[str] = []

    def check(label: str, got: int, want: int) -> None:
        ok = got == want
        print(f"  [{'OK' if ok else 'FAIL'}] {label}: {got}" + ("" if ok else f" (기대 {want})"))
        if not ok:
            failures.append(label)

    deals = {deal["id"]: deal for deal in rows["sales_deal"]}
    activities = {item["id"]: item for item in rows["activity"]}
    reports = rows["report"]
    confirmed = {
        stage_id
        for stage_id, (_c, outcome, _p) in ()  # 자리표시. 아래에서 position 으로 본다
    }
    del confirmed

    # --- 수량
    check("제품", len(rows["product"]), len(data.PRODUCTS))
    check(
        "고객사", len(rows["customer_company"]), len({c["name"] for c in rows["customer_company"]})
    )
    check("딜", len(rows["sales_deal"]), seeder_module.DEALS)
    check("발주", len(rows["purchase_order"]), seeder_module.ORDERS)
    check("고객불만", len(rows["support_request"]), len(data.SUPPORTS))
    check("공지 + 지시", len(rows["notice"]), len(data.NOTICES) + len(data.DIRECTIVES))
    check("모든 단계에 딜이 있음", len({d["stage_position"] for d in rows["sales_deal"]}), 9)

    # --- 날짜 불변식
    past = sum(1 for a in activities.values() if a["starts_at"].date() < base)
    today = sum(1 for a in activities.values() if a["starts_at"].date() == base)
    future = sum(1 for a in activities.values() if a["starts_at"].date() > base)
    print(f"  [--] 일정: 과거 {past} · 오늘 {today} · 미래 {future} (합 {len(activities)})")
    if today == 0:
        failures.append("오늘 일정이 없다")
    if future == 0:
        failures.append("미래 일정이 없다")

    check(
        "미래 일정이 완료 처리됨",
        sum(1 for a in activities.values() if a["starts_at"].date() > base and a["completed_at"]),
        0,
    )
    check(
        "미래 일정에 보고서가 붙음",
        sum(
            1
            for r in reports
            if r["source_activity_id"]
            and activities[r["source_activity_id"]]["starts_at"].date() > base
        ),
        0,
    )
    check("보고 기준일이 미래", sum(1 for r in reports if r["report_date"] > base), 0)
    check(
        "오늘 일정에 확정 보고서가 붙음",
        sum(
            1
            for r in reports
            if r["source_activity_id"]
            and activities[r["source_activity_id"]]["starts_at"].date() == base
            and r["status_code"] == "approved"
        ),
        0,
    )
    check(
        "미팅보고서에 근거 일정이 없음",
        sum(1 for r in reports if r["report_kind"] == "meeting" and not r["source_activity_id"]),
        0,
    )
    check(
        "기준일 이후에 체결된 계약",
        sum(
            1 for d in deals.values() if d["contract_signed_on"] and d["contract_signed_on"] > base
        ),
        0,
    )
    check(
        "견적일이 개설일보다 앞섬",
        sum(
            1
            for d in deals.values()
            if d["quote_issued_on"] and d["quote_issued_on"] < d["opened_on"]
        ),
        0,
    )
    check(
        "계약일이 견적일보다 앞섬",
        sum(
            1
            for d in deals.values()
            if d["contract_signed_on"]
            and d["quote_issued_on"]
            and d["contract_signed_on"] < d["quote_issued_on"]
        ),
        0,
    )
    check(
        "발주일이 계약일보다 앞섬",
        sum(
            1
            for o in rows["purchase_order"]
            if deals[o["sales_deal_id"]]["contract_signed_on"] is None
            or o["ordered_on"] < deals[o["sales_deal_id"]]["contract_signed_on"]
        ),
        0,
    )
    check(
        "종료 시각이 시작 시각보다 앞섬",
        sum(1 for a in activities.values() if a["ends_at"] and a["ends_at"] <= a["starts_at"]),
        0,
    )

    # --- 관계
    check(
        "불만이 계약 전 딜에 붙음",
        sum(
            1
            for r in rows["support_request"]
            if deals[r["sales_deal_id"]]["contract_signed_on"] is None
        ),
        0,
    )
    check(
        "불만의 고객사가 딜의 고객사와 다름",
        sum(
            1
            for r in rows["support_request"]
            if r["customer_company_id"] != deals[r["sales_deal_id"]]["customer_company_id"]
        ),
        0,
    )
    check(
        "불만 발생이 접수보다 늦음",
        sum(1 for r in rows["support_request"] if r["occurred_at"] > r["registered_at"]),
        0,
    )
    check(
        "확정 단계인데 계약일이 없음",
        sum(
            1
            for d in deals.values()
            if d["stage_position"] in (5, 6, 7) and d["contract_signed_on"] is None
        ),
        0,
    )

    # --- 중복
    for table in ("sales_deal", "activity", "report", "customer_company", "product"):
        check(f"{table} id 중복", len(rows[table]) - len({r["id"] for r in rows[table]}), 0)
    check(
        "고객사 이름 중복",
        len(rows["customer_company"]) - len({c["name"] for c in rows["customer_company"]}),
        0,
    )

    # --- 고객 담당자 (seed_contact_rollup 이 되짚어 쓴 값)
    # 같은 행을 두 번 넣으므로(최초 + 되짚기) id 로 접어 마지막 상태만 본다.
    contacts = {c["id"]: c for c in rows["customer_contact"]}
    status_name = {uid: code for code, uid in seeder.status.items()}
    check("담당자 이메일 없음", sum(1 for c in contacts.values() if not c["email"]), 0)
    check(
        "담당자 이메일 중복",
        len(contacts) - len({c["email"] for c in contacts.values()}),
        0,
    )
    visited = sum(1 for c in contacts.values() if c["visited"])
    memoed = sum(1 for c in contacts.values() if c["memo"])
    print(f"  [--] 담당자 {len(contacts)} · 방문 {visited} · 메모 {memoed}")
    if not visited:
        failures.append("방문한 담당자가 없다")
    if not memoed:
        failures.append("메모가 있는 담당자가 없다")

    visit_category = seeder.category["visit"]
    check(
        "완료된 방문 활동이 있는데 미방문",
        len(
            {
                a["customer_contact_id"]
                for a in activities.values()
                if a["customer_contact_id"]
                and a["activity_category_id"] == visit_category
                and a["completed_at"]
                and a["starts_at"].date() < base
                and not contacts[a["customer_contact_id"]]["visited"]
            }
        ),
        0,
    )
    best_position: dict[Any, int] = {}
    for deal in deals.values():
        contact_id = deal["customer_contact_id"]
        best_position[contact_id] = max(best_position.get(contact_id, 0), deal["stage_position"])
    check(
        "니즈 검증을 넘긴 딜이 있는데 상태가 신규",
        sum(
            1
            for contact_id, position in best_position.items()
            if position >= 1
            and status_name[contacts[contact_id]["customer_contact_status_id"]] == "new"
        ),
        0,
    )
    print(
        "  [--] 담당자 상태 "
        f"{dict(Counter(status_name[c['customer_contact_status_id']] for c in contacts.values()))}"
    )
    check(
        "담당자 등록보다 딜 개설이 빠름",
        sum(
            1
            for d in deals.values()
            if d["opened_on"] < contacts[d["customer_contact_id"]]["registered_at"].date()
        ),
        0,
    )
    companies = {c["id"]: c for c in rows["customer_company"]}
    check(
        "고객사 등록보다 딜 개설이 빠름",
        sum(
            1
            for d in deals.values()
            if d["opened_on"] < companies[d["customer_company_id"]]["created_at"].date()
        ),
        0,
    )

    # --- 계약갱신
    check(
        "30일 이내 계약 종료 확정 딜",
        sum(
            1
            for d in deals.values()
            if d["stage_position"] in (5, 6, 7)
            and d["contract_ends_on"]
            and base <= d["contract_ends_on"] <= base + timedelta(days=30)
        ),
        seeder_module.RENEWALS,
    )

    # --- 매출목표
    targets = rows["sales_target"]
    month = base.replace(day=1)
    this_month = sum(t["target_amount"] for t in targets if t["target_month"] == month)
    print(f"  [--] 매출목표 {len(targets)}건 · 이번 달 {this_month:,}원")
    if not this_month:
        failures.append("이번 달 매출목표가 없다")
    check(
        "매출목표 (담당자·회사·월) 중복",
        len(targets)
        - len(
            {(t["owner_member_id"], t["customer_company_id"], t["target_month"]) for t in targets}
        ),
        0,
    )
    owned = {(d["owner_member_id"], d["customer_company_id"]) for d in deals.values()}
    manager_id = seeder.members[data.MANAGER]
    check(
        "목표가 붙은 고객사에 그 담당자의 딜이 없음",
        sum(
            1
            for t in targets
            if t["owner_member_id"] != manager_id
            and (t["owner_member_id"], t["customer_company_id"]) not in owned
        ),
        0,
    )

    print(f"  [--] 보고서 {len(reports)} {dict(Counter(r['report_kind'] for r in reports))}")
    print(f"  [--] 상태 {dict(Counter(r['status_code'] for r in reports))}")
    print(f"  [--] 불만 {dict(Counter(r['status_code'] for r in rows['support_request']))}")
    return failures


def main() -> None:
    raw = sys.argv[1] if len(sys.argv) > 1 else None
    base = date.fromisoformat(raw) if raw else datetime.now(SEOUL).date()
    print(f"=== 기준일 {base} (DB 에 접근하지 않음) ===")
    rows, seeder = asyncio.run(collect(base))
    failures = report(base, rows, seeder)
    print(f"\n실패 {len(failures)}건" + (f": {failures}" if failures else ""))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
