"""DB 없이 시더 로직을 검사한다.

개발과 운영이 같은 DB 를 쓰고 있어서, 시더를 고칠 때마다 공유 DB 에 넣어 보며 확인할 수는
없다. 여기서 같은 불변식을 순수 파이썬으로 먼저 거른다.

    uv run python -m scripts.demo.check_offline
    uv run python -m scripts.demo.check_offline 2026-12-25   # 기준일을 바꿔도 되는지

SQL 은 검사하지 않는다. 날짜 축·금액·키·참조 관계가 목표다.
"""

import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from scripts import seed_demo_medion as seeder_module
from scripts.demo import medion
from scripts.seed_demo_medion import (
    DENSE_FROM,
    DENSE_MIN,
    DENSE_TO,
    FLOW,
    ORDER_STAGES,
    SIGNED_STAGES,
    SPARSE_MIN,
    SPARSE_MONTHS,
    Seeder,
    add_months,
    month_start,
    weekdays,
)


class _StubDB:
    """execute 를 삼킨다. 원본 NoticeTarget insert 만 여기로 온다."""

    async def execute(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _install_recorder() -> dict[str, list[dict[str, Any]]]:
    """upsert/link 를 가로채 무엇을 쓰려 했는지 모은다."""
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    async def upsert(_session: Any, model: Any, values: dict[str, Any]) -> None:
        rows[model.__tablename__].append(values)

    async def link(_session: Any, model: Any, values: dict[str, Any]) -> None:
        rows[model.__tablename__].append(values)

    async def upsert_report_deal(_session: Any, values: dict[str, Any]) -> None:
        rows["report_deal"].append(values)

    seeder_module.upsert = upsert
    seeder_module.link = link
    seeder_module.upsert_report_deal = upsert_report_deal
    return rows


async def build(base: date) -> tuple[Seeder, dict[str, list[dict[str, Any]]]]:
    rows = _install_recorder()
    members = {medion.LEADER: uuid4(), medion.MEMBER: uuid4()}
    seeder = Seeder(_StubDB(), base, members)

    # load_configuration 은 DB 를 읽는다. 룩업을 직접 채워 그 단계를 건너뛴다.
    codes = {
        "status": medion.CONTACT_STATUS_CODES,
        "category": ("visit", "demo", "education", "call", "delivery", "conference"),
        "action_tag": tuple({f[2] for f in FLOW} | {"demo_requested"}),
        "deal_type": ("new_installation", "expansion", "renewal", "maintenance"),
        "order_status": (
            "order_received", "dispatch_request_completed", "in_production",
            "stock_received", "delivered", "cancelled",
        ),
        "quote_status": ("drafting", "reviewing", "sent", "negotiating", "completed"),
        "contract_status": ("drafting", "reviewing", "negotiating", "signed", "completed"),
    }
    for attribute, values in codes.items():
        getattr(seeder, attribute).update({code: uuid4() for code in values})
    seeder.pipeline_id = uuid4()
    outcomes = {
        "needs_validation": ("sales", "in_progress"),
        "product_demo": ("sales", "in_progress"),
        "quote_sent": ("quote", "in_progress"),
        "contract_sent": ("contract", "in_progress"),
        "contract_review": ("contract", "in_progress"),
        "contract_completed": ("contract", "confirmed"),
        "order_in_progress": ("order", "confirmed"),
        "order_delivered": ("order", "confirmed"),
        "closed_cancelled": ("closed", "cancelled"),
    }
    seeder.stages = {code: (uuid4(), oc, 0) for code, (_, oc) in outcomes.items()}
    seeder.phases = {code: ph for code, (ph, _) in outcomes.items()}

    await seeder.seed_products()
    await seeder.seed_companies()
    await seeder.seed_contacts()
    seeder.plan_deals()
    await seeder.seed_deals()
    await seeder.seed_activities()
    await seeder.seed_reports()
    await seeder.seed_orders()
    await seeder.seed_supports()
    await seeder.seed_targets()
    await seeder.seed_notices()
    return seeder, rows


def check(seeder: Seeder, rows: dict[str, list[dict[str, Any]]], base: date) -> None:
    companies = rows["customer_company"]
    assert len(companies) == seeder_module.COMPANY_COUNT, len(companies)
    names = [c["name"] for c in companies]
    assert len(names) == len(set(names)), "고객사 이름이 겹치면 유일 인덱스에 걸린다"
    assert all(c["region_code"] for c in companies), "지역이 없으면 지역 필터에서 사라진다"

    contacts = rows["customer_contact"]
    assert contacts, "담당자가 없으면 딜을 걸 데가 없다"
    assert all(c["phone"].startswith("010-0000-") for c in contacts), "통화되는 번호를 쓰면 안 된다"
    assert all(c["email"].endswith("@demo.test") for c in contacts), "예약 도메인만 쓴다"

    deals = {d["deal_no"]: d for d in rows["sales_deal"]}
    assert len(deals) == len(rows["sales_deal"]), "딜 번호가 겹친다"
    quotes = [d["quote_no"] for d in rows["sales_deal"] if d["quote_no"]]
    assert len(quotes) == len(set(quotes)), "견적 번호가 겹친다"
    contracts = [d["contract_no"] for d in rows["sales_deal"] if d["contract_no"]]
    assert len(contracts) == len(set(contracts)), "계약 번호가 겹친다"

    for deal in rows["sales_deal"]:
        opened = deal["opened_on"]
        quote_on = deal["quote_issued_on"]
        signed = deal["contract_signed_on"]
        assert quote_on is None or quote_on >= opened, deal["deal_no"]
        assert signed is None or signed >= opened, deal["deal_no"]
        if quote_on and signed:
            assert signed >= quote_on, deal["deal_no"]
        assert signed is None or signed <= base, f"미래 계약: {deal['deal_no']}"
        if deal["contract_ends_on"]:
            assert deal["contract_ends_on"] >= signed, deal["deal_no"]

    for plan in seeder.deals:
        if plan["stage"] in SIGNED_STAGES:
            assert plan["signed"] is not None, f"확정인데 계약일 없음: {plan['key']}"
        else:
            assert plan["signed"] is None, f"미확정인데 계약일 있음: {plan['key']}"
        assert plan["order_amount"] <= plan["contract_amount"], (
            f"발주가 계약금액보다 큼: {plan['key']}"
        )

    # 활동: 미래 일정은 완료되지 않고, 오늘 일정도 완료되지 않는다.
    for activity in rows["activity"]:
        day = activity["starts_at"].date()
        assert activity["ends_at"] > activity["starts_at"]
        if day >= base:
            assert activity["completed_at"] is None, f"미래·오늘 일정이 완료됨: {activity['title']}"
        else:
            assert activity["completed_at"] is not None
        assert activity["customer_company_id"] is not None

    today = [a for a in rows["activity"] if a["starts_at"].date() == base]
    owners_today = {a["owner_member_id"] for a in today}
    assert len(owners_today) == 2, "오늘 일정이 두 사람 모두에게 있어야 한다"
    assert any(a["starts_at"].date() > base for a in rows["activity"]), "미래 일정이 없다"
    this_month = [
        a
        for a in rows["activity"]
        if (a["starts_at"].date().year, a["starts_at"].date().month) == (base.year, base.month)
    ]
    assert len(this_month) >= 15, f"이번 달 일정이 적다: {len(this_month)}"

    # 활동 담당자와 고객 담당자의 소유자가 같아야 팀원 화면에서 사라지지 않는다.
    contact_owner = {c["id"]: c["owner_member_id"] for c in contacts}
    for activity in rows["activity"]:
        assert contact_owner[activity["customer_contact_id"]] == activity["owner_member_id"]

    # 보고서
    reports = rows["report"]
    kinds = {r["report_kind"] for r in reports}
    assert kinds == {"meeting", "daily", "weekly", "monthly"}, kinds
    statuses = {r["status_code"] for r in reports}
    assert "submitted" in statuses, "검토 대기 보고서가 없으면 검토 흐름을 시연할 수 없다"
    assert "changes_requested" in statuses, "반려 보고서가 없다"
    assert any(r["status_code"] == "approved" and r["reviewed_by_member_id"] for r in reports)
    activity_day = {a["id"]: a["starts_at"].date() for a in rows["activity"]}
    meeting_sources = []
    for report in reports:
        if report["report_kind"] != "meeting":
            continue
        assert report["source_activity_id"] is not None
        meeting_sources.append(report["source_activity_id"])
        assert activity_day[report["source_activity_id"]] < base, "미래·오늘 일정에 보고서가 붙었다"
    assert len(meeting_sources) == len(set(meeting_sources)), "한 일정에 미팅 보고서가 둘이다"
    past = {a["id"] for a in rows["activity"] if a["starts_at"].date() < base}
    missing = past - set(meeting_sources)
    assert not missing, f"보고서 없는 지난 일정 {len(missing)}건 — 화면에 '보고서 미작성' 으로 뜬다"
    assert len(rows["report_deal"]) >= len(meeting_sources), "미팅 보고서마다 딜 섹션이 하나 이상"

    daily_keys = [
        (r["author_member_id"], r["report_date"]) for r in reports if r["report_kind"] == "daily"
    ]
    assert len(daily_keys) == len(set(daily_keys)), "report_daily_author_date_key 위반"
    period_keys = [
        (r["author_member_id"], r["report_kind"], r["period_start"], r["period_end"])
        for r in reports
        if r["report_kind"] in ("weekly", "monthly")
    ]
    assert len(period_keys) == len(set(period_keys)), "report_period_author_range_key 위반"

    # 평일이 비지 않는지. 영업 화면에 미팅이 하루도 없는 날이 있으면 데모가 멈춘다.
    per_day: dict[tuple[Any, date], int] = defaultdict(int)
    for activity in rows["activity"]:
        per_day[(activity["owner_member_id"], activity["starts_at"].date())] += 1
    owners = sorted({c["owner_member_id"] for c in contacts}, key=str)
    for day in weekdays(base + timedelta(days=DENSE_FROM), base + timedelta(days=DENSE_TO)):
        for owner in owners:
            assert per_day[(owner, day)] >= DENSE_MIN, (
                f"{day} 에 미팅이 {per_day[(owner, day)]}건뿐이다 (목표 {DENSE_MIN})"
            )
    sparse = weekdays(
        add_months(month_start(base), -SPARSE_MONTHS), base + timedelta(days=DENSE_FROM - 1)
    )
    for owner in owners:
        filled = sum(1 for day in sparse if per_day[(owner, day)] >= SPARSE_MIN)
        assert filled >= len(sparse) * 0.7, f"미팅 없는 평일이 너무 많다: {filled}/{len(sparse)}"

    # 보고서 상세의 '관련 보고서' 는 하위 보고서를 날짜로 다시 조회해 그린다
    # (frontend/src/pages/Daily/sources.ts). 구간이 어긋나면 열었을 때 빈다.
    rolled = ("submitted", "approved")
    children = defaultdict(list)
    for report in reports:
        if report["report_kind"] in ("daily", "weekly") and report["status_code"] in rolled:
            children[(report["author_member_id"], report["report_kind"])].append(
                report["report_date"]
            )
    for report in reports:
        if report["report_kind"] not in ("weekly", "monthly"):
            continue
        kind = "weekly" if report["report_kind"] == "monthly" else "daily"
        first = seeder_module.week_start(report["period_start"])
        found = [
            d
            for d in children[(report["author_member_id"], kind)]
            if first <= d <= report["period_end"]
        ]
        assert found, f"{report['title']} 의 관련 보고서가 비어 있다"

    # 한 주가 지난 보고서는 확정돼 있어야 한다. 한 달 전 글이 검토 대기로 남으면 안 된다.
    old_reports = [r for r in reports if (base - r["report_date"]).days > 7]
    approved = sum(1 for r in old_reports if r["status_code"] == "approved")
    assert approved >= len(old_reports) * 0.8, f"오래된 보고서의 확정 비율이 낮다: {approved}"
    assert not [r for r in old_reports if r["status_code"] == "draft"], (
        "한 주가 지났는데 작성중인 보고서가 있다"
    )

    # 고객현황 메모. 대부분 채우고 일부는 빈 화면 시연용으로 남긴다.
    written = [c for c in contacts if c["memo"]]
    assert len(written) >= len(contacts) * 0.7, f"메모가 적다: {len(written)}/{len(contacts)}"
    assert len(written) < len(contacts), "빈 메모가 하나도 없다"
    assert all("{" not in c["memo"] for c in written), "메모 서식 자리가 남아 있다"

    # 발주
    for order in rows["purchase_order"]:
        assert order["due_on"] >= order["ordered_on"]
        assert order["expected_receipt_on"] >= order["ordered_on"]
    order_deals = {o["sales_deal_id"] for o in rows["purchase_order"]}
    by_id = {p["id"]: p for p in seeder.deals}
    assert all(by_id[i]["stage"] in ORDER_STAGES for i in order_deals), (
        "발주가 order 단계가 아닌 딜에 붙으면 발주 목록에서 보이지 않는다"
    )

    # C/S 는 계약 이후 딜에만 붙는다.
    company_of = {p["id"]: p["contact"]["company_id"] for p in seeder.deals}
    for request in rows["support_request"]:
        assert request["customer_company_id"] == company_of[request["sales_deal_id"]]
        assert seeder.phases[by_id[request["sales_deal_id"]]["stage"]] in (
            "contract", "order", "closed",
        )

    # 목표: 이번 달은 두 사람 모두 있어야 하고, 회사별 목표는 없어야 한다.
    month = base.replace(day=1)
    current = [t for t in rows["sales_target"] if t["target_month"] == month]
    assert len(current) == 2, f"이번 달 목표가 {len(current)}건"
    assert all(t["target_amount"] > 0 for t in current), "이번 달 목표가 0이면 카드가 빈다"
    assert all(t["customer_company_id"] is None for t in rows["sales_target"])

    # 매출: 확정 딜이 24개월 이상에 걸쳐 있어야 2년 매출분석이 성립한다.
    revenue: dict[tuple[int, int], int] = defaultdict(int)
    for plan in seeder.deals:
        if plan["signed"] and seeder.stages[plan["stage"]][1] == "confirmed":
            revenue[(plan["signed"].year, plan["signed"].month)] += plan["contract_amount"]
    assert len(revenue) >= 24, f"확정 매출이 잡히는 달이 {len(revenue)}개뿐이다"
    assert revenue.get((base.year, base.month), 0) > 0, "이번 달 확정 매출이 없다"
    assert len({y for y, _ in revenue}) >= 3, "연도가 세 해에 걸치지 않는다"

    # 공지: 지시사항은 수신자가 있어야 하고 공지는 없어야 한다.
    notices = rows["notice"]
    assert sum(1 for n in notices if n["type"] == "NOTICE") == 3
    assert sum(1 for n in notices if n["type"] == "DIRECTIVE") == 3
    assert all(n["display_start_date"] <= base for n in notices), "게시 시작일이 미래면 안 보인다"
    assert not any(n["is_hidden"] for n in notices)

    # 갱신 카드: 30일 안에 끝나는 확정 계약이 있어야 한다.
    ends = [d["contract_ends_on"] for d in rows["sales_deal"] if d["contract_ends_on"]]
    assert any(base <= e <= base.fromordinal(base.toordinal() + 30) for e in ends), (
        "계약 갱신 예정 카드가 빈다"
    )

    check_templates()
    check_report_format(reports, rows, base)

BLANK = "해당사항 없음"
# 자리표시자 바로 뒤에 붙은 조사. 받침에 따라 달라지므로 박아 두면 안 된다.
PLACEHOLDER_JOSA = re.compile(r"\}(와|과|이|가|은|는|을|를)")


def check_templates() -> None:
    """템플릿에 조사를 박아 두지 않았는지 본다.

    '{company}와' 처럼 쓰면 받침에 따라 '이화병원와' 같은 비문이 나온다. 값이 무엇이든
    맞으려면 josa() 가 붙여 준 자리표시자(person_sub·company_with 등)를 써야 한다.
    이 검사가 그 실수를 본문이 아니라 원인 자리에서 잡는다.
    """
    from scripts.seed_demo_medion import DIRECTIVE_SECTIONS, MEETING_SECTIONS

    specs = [*MEETING_SECTIONS.values(), DIRECTIVE_SECTIONS]
    for spec in specs:
        for key, value in spec.items():
            if not isinstance(value, str):
                continue
            for match in PLACEHOLDER_JOSA.finditer(value):
                raise AssertionError(
                    f"템플릿 '{key}' 의 {match.group(0)!r} 은 조사를 박아 두었다."
                    " josa() 를 거친 자리표시자를 쓰세요."
                )


def check_report_format(
    reports: list[dict[str, Any]], rows: dict[str, list[dict[str, Any]]], base: date
) -> None:
    """화면이 본문을 구획으로 읽을 수 있는 꼴인지 본다.

    frontend/src/shared/reportSections.ts 와 같은 규칙을 그대로 옮겼다. 여기가 통과해야
    보고서가 LLM 이 쓴 것처럼 구획으로 나뉘어 그려진다.
    """
    from scripts.seed_demo_medion import (
        DAILY_ORDER,
        MEETING_ORDER,
        MONTHLY_ORDER,
        WEEKLY_ORDER,
    )

    orders = {
        "daily": DAILY_ORDER,
        "weekly": WEEKLY_ORDER,
        "monthly": MONTHLY_ORDER,
    }

    # 미팅 정보는 report.content 에서만 읽는다. 비면 화면이 '—' 를 그린다.
    for report in reports:
        if report["report_kind"] != "meeting":
            continue
        content = report["content"]
        for key in ("time", "hospital", "dept", "contact", "place", "title"):
            assert content.get(key), f"report.content.{key} 가 비면 미팅 정보가 '—' 로 뜬다"
        assert TIME.match(content["time"]), content["time"]
        # 공통·미지정 기록은 소제목 없는 평목록이다.
        for key in ("common_body", "unassigned_body"):
            value = report[key]
            assert value is None or "**" not in value, f"{key} 에는 소제목을 쓰지 않는다"
            assert value is None or all(
                line.startswith("- ") for line in value.splitlines() if line.strip()
            ), f"{key} 는 '- ' 목록이어야 한다"
        assert report["body"] is None, "미팅 보고서의 report.body 는 비어 있어야 한다"

    for report in reports:
        order = orders.get(report["report_kind"])
        if order is None:
            continue
        assert_sections(report["body"], order, f"{report['report_kind']} 보고서")

    for section in rows["report_deal"]:
        assert_sections(section["body"], MEETING_ORDER, "미팅 딜 섹션")
        assert section["title"], "딜 섹션 제목이 비었다"
        assert section["content"]["values"]["body"] == section["body"], (
            "report_deal.body 와 content.values.body 가 갈리면 화면 두 곳이 다른 글을 보인다"
        )
        evidence = section["ai_evidence"]
        assessment = evidence["deal_assessment"]
        # 셋이 모두 맞아야 프런트가 ML 배지를 그린다 (generatedDraft.readMeetingAnalysis).
        assert assessment["label"] in ("high", "watch"), assessment
        assert isinstance(assessment["high_probability"], float), assessment
        assert 0 < assessment["high_probability"] < 1, assessment
        assert isinstance(assessment["model_version"], str) and assessment["model_version"]
        assert evidence["analysis_status"] == "completed"

    del base


# frontend/src/shared/reportSections.ts 의 HEADING 과 같은 정규식이다.
HEADING = re.compile(r"^\*\*(.+?)\*\*$")
TIME = re.compile(r"^[0-2][0-9]:[0-5][0-9]$")
# reportSections.ts 의 FIELD_LABELS. 여기 없는 이름표는 파싱되지 않는다.
FIELD_LABELS = (
    "담당자", "담당", "기한", "완료 기준", "상태", "이행 여부", "조건", "선행조건",
    "전달 방식", "요청 대상",
)
# 받침 없는 직급 뒤에 조사를 박아 두면 '대리이' 같은 비문이 된다. 이름에는 '다은' 처럼
# 조사로 보이는 글자가 흔해 본문 전체를 훑으면 오탐이 난다. 직급만 정확히 본다.
BAD_JOSA = tuple(
    f"{title}{particle} "
    for title in medion.JOB_TITLES
    if (ord(title[-1]) - 0xAC00) % 28 == 0
    for particle in ("이", "은", "을")
)


def assert_sections(body: str, order: tuple[str, ...], label: str) -> None:
    headings = [
        match.group(1) for line in body.splitlines() if (match := HEADING.match(line.strip()))
    ]
    assert headings == list(order), f"{label} 의 소제목이 {headings} — 기대 {list(order)}"

    for index, heading in enumerate(order):
        marker = f"**{heading}**\n\n"
        assert marker in body, f"{label} 의 '{heading}' 뒤에 빈 줄이 없다"
        del index

    # 마지막 항목은 목록이다.
    tail = body.split(f"**{order[-1]}**\n\n", 1)[1]
    for line in tail.splitlines():
        if not line.strip():
            continue
        assert line.startswith("- "), f"{label} 의 마지막 항목은 목록이어야 한다: {line}"
        if line.startswith(f"- {BLANK}"):
            continue
        fields = line[2:].split(" · ")
        assert fields[0].startswith("**"), f"{label} 의 할 일이 굵게 써 있지 않다: {line}"
        for field in fields[1:]:
            name = field.split(":", 1)[0].strip()
            assert name in FIELD_LABELS, f"{label} 의 이름표 '{name}' 은 화면이 모른다"

    # 조사 비문. '대리이 내부 검토' 처럼 받침 없는 직급 뒤의 이/은/을을 잡는다.
    for bad in BAD_JOSA:
        assert bad not in body, f"{label} 에 조사 비문이 있다: {bad!r}"
    # 병원 이름 뒤의 와/과도 같은 문제다. 본문에 드러난 것만 본다.
    for bad in ("병원와", "의원와", "센터와", "병원을를", "의원과과"):
        assert bad not in body, f"{label} 에 조사 비문이 있다: {bad!r}"

async def go(base: date) -> None:
    seeder, rows = await build(base)
    check(seeder, rows, base)
    print(f"기준일 {base.isoformat()}")
    for label in sorted(seeder.counts):
        print(f"  {label:<32} {seeder.counts[label]:>6}")
    print("  자체 검사 통과")


def main() -> None:
    import asyncio

    raw = sys.argv[1] if len(sys.argv) > 1 else None
    bases = (
        [date.fromisoformat(raw)]
        if raw
        else [
            datetime.now(ZoneInfo("Asia/Seoul")).date(),
            date(2026, 12, 25),
            date(2027, 3, 1),
        ]
    )
    for base in bases:
        asyncio.run(go(base))
    print("전부 통과")


if __name__ == "__main__":
    main()
