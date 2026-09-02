"""seed_demo_dataset 이 넣은 데이터를 읽기 전용으로 검증한다.

수량·관계·날짜·고아 행을 세고 기대값과 맞는지 확인한다. 아무것도 고치지 않는다.
기준일이 필요한 검사는 --base-date 로 받는다. 기본값은 실행일이다.

    uv run python -m scripts.verify_demo_dataset [--base-date YYYY-MM-DD]
"""

import argparse
import asyncio
from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from scripts.demo import data, hospitals
from scripts.seed_demo_dataset import DEALS, ORDERS, RENEWALS, TEAM_ID, TEAM_NAME

SEOUL = ZoneInfo("Asia/Seoul")


def expected_counts() -> dict[str, int]:
    """엑셀과 상수에서 직접 뽑는다. 숫자를 두 곳에 적어 두면 언젠가 어긋난다."""
    return {
        "company": len(hospitals.load()),
        "product": len(data.PRODUCTS),
        "support_request": len(data.SUPPORTS),
        "notice_all": len(data.NOTICES) + len(data.DIRECTIVES),
        "notice_notice": len(data.NOTICES),
        "notice_directive": len(data.DIRECTIVES),
        "document": len(data.DOCUMENTS),
        "member": len(data.MEMBERS),
        "deal": DEALS,
        "order": ORDERS,
        "renewal": RENEWALS,
    }


# (제목, SQL, 기대값). 기대값이 None 이면 개수만 보고한다.
# :team 과 :base 를 바인딩한다.
def checks(expected: dict[str, int]) -> tuple[tuple[str, str, int | None], ...]:
    return (
        # ---------------- 수량
        (
            "고객사 수",
            "select count(*) from customer_company where team_id = :team",
            expected["company"],
        ),
        ("제품 수", "select count(*) from product where team_id = :team", expected["product"]),
        ("딜 수", "select count(*) from sales_deal where team_id = :team", expected["deal"]),
        ("발주 수", "select count(*) from purchase_order where team_id = :team", expected["order"]),
        (
            "고객불만 수",
            "select count(*) from support_request where team_id = :team",
            expected["support_request"],
        ),
        (
            "공지 수 (NOTICE)",
            "select count(*) from notice where team_id = :team and type = 'NOTICE'",
            expected["notice_notice"],
        ),
        (
            "지시 수 (DIRECTIVE)",
            "select count(*) from notice where team_id = :team and type = 'DIRECTIVE'",
            expected["notice_directive"],
        ),
        ("자료실 수", "select count(*) from document where team_id = :team", expected["document"]),
        ("구성원 수", "select count(*) from member where team_id = :team", expected["member"]),
        (
            "활성 팀장 수",
            """select count(*) from member
            where team_id = :team and role_code = 'manager' and active""",
            1,
        ),
        (
            "영업 파이프라인 단계",
            """
            select count(*) from sales_pipeline_stage s
            join sales_pipeline p on p.id = s.sales_pipeline_id where p.team_id = :team
        """,
            9,
        ),
        (
            "딜이 채우지 못한 단계",
            """
            select count(*) from sales_pipeline_stage s
            join sales_pipeline p on p.id = s.sales_pipeline_id
            where p.team_id = :team
              and not exists (select 1 from sales_deal d where d.sales_pipeline_stage_id = s.id)
        """,
            0,
        ),
        # ---------------- 관계
        (
            "딜이 팀 밖 고객사를 참조",
            """
            select count(*) from sales_deal d
            left join customer_company c on c.id = d.customer_company_id
            where d.team_id = :team and (c.id is null or c.team_id <> d.team_id)
        """,
            0,
        ),
        (
            "딜이 팀 밖 담당자를 참조",
            """
            select count(*) from sales_deal d
            left join member m on m.id = d.owner_member_id
            where d.team_id = :team and (m.id is null or m.team_id <> d.team_id)
        """,
            0,
        ),
        (
            "딜이 팀 밖 제품을 참조",
            """
            select count(*) from sales_deal d
            left join product p on p.id = d.product_id
            where d.team_id = :team and d.product_id is not null
              and (p.id is null or p.team_id <> d.team_id)
        """,
            0,
        ),
        (
            "고객 담당자가 팀 밖 고객사를 참조",
            """
            select count(*) from customer_contact k
            join member m on m.id = k.owner_member_id
            join customer_company c on c.id = k.company_id
            where m.team_id = :team and c.team_id <> :team
        """,
            0,
        ),
        (
            "불만의 고객사가 딜의 고객사와 다름",
            """
            select count(*) from support_request r
            join sales_deal d on d.id = r.sales_deal_id
            where r.team_id = :team and d.customer_company_id <> r.customer_company_id
        """,
            0,
        ),
        (
            "불만이 계약 전 딜에 붙음",
            """
            select count(*) from support_request r
            join sales_deal d on d.id = r.sales_deal_id
            where r.team_id = :team and d.contract_signed_on is null
        """,
            0,
        ),
        (
            "활동이 다른 고객사의 딜에 붙음",
            """
            select count(*) from activity a
            join sales_deal d on d.id = a.sales_deal_id
            join customer_contact k on k.id = a.customer_contact_id
            where a.team_id = :team and d.customer_company_id <> k.company_id
        """,
            0,
        ),
        (
            "미팅보고서에 근거 일정이 없음",
            """
            select count(*) from report
            where team_id = :team and report_kind = 'meeting' and source_activity_id is null
        """,
            0,
        ),
        (
            "주간·월간보고서에 근거 일정이 없음",
            """
            select count(*) from report r
            where r.team_id = :team and r.report_kind in ('weekly', 'monthly')
              and not exists (select 1 from report_activity ra where ra.report_id = r.id)
        """,
            0,
        ),
        (
            "지시사항에 수신자가 없음",
            """
            select count(*) from notice n
            where n.team_id = :team and n.type = 'DIRECTIVE'
              and not exists (select 1 from notice_target t where t.notice_id = n.id)
        """,
            0,
        ),
        (
            "공지에 수신자가 붙음",
            """
            select count(*) from notice n
            join notice_target t on t.notice_id = n.id
            where n.team_id = :team and n.type = 'NOTICE'
        """,
            0,
        ),
        (
            "발주 품목이 팀 밖 제품을 참조",
            """
            select count(*) from purchase_order_item i
            join purchase_order o on o.id = i.purchase_order_id
            left join product p on p.id = i.product_id
            where o.team_id = :team and (p.id is null or p.team_id <> :team)
        """,
            0,
        ),
        # ---------------- 날짜 (기준일 불변식)
        (
            "미래 일정에 보고서가 붙음",
            """
            select count(*) from report r
            join activity a on a.id = r.source_activity_id
            where r.team_id = :team and a.starts_at::date > :base
        """,
            0,
        ),
        (
            "미래 일정이 완료 처리됨",
            """
            select count(*) from activity
            where team_id = :team and starts_at::date > :base and completed_at is not null
        """,
            0,
        ),
        (
            "오늘 일정에 확정된 보고서가 붙음",
            """
            select count(*) from report r
            join activity a on a.id = r.source_activity_id
            where r.team_id = :team and a.starts_at::date = :base and r.status_code = 'approved'
        """,
            0,
        ),
        (
            "보고 기준일이 기준일보다 미래",
            "select count(*) from report where team_id = :team and report_date > :base",
            0,
        ),
        (
            "미래 일정이 없음 (0이면 실패)",
            """
            select case when count(*) = 0 then 1 else 0 end from activity
            where team_id = :team and starts_at::date > :base
        """,
            0,
        ),
        (
            "오늘 일정이 없음 (0이면 실패)",
            """
            select case when count(*) = 0 then 1 else 0 end from activity
            where team_id = :team and starts_at::date = :base
        """,
            0,
        ),
        (
            "개설일 ≤ 견적일 ≤ 계약일 위반",
            """
            select count(*) from sales_deal
            where team_id = :team and (
              (quote_issued_on is not null and quote_issued_on < opened_on)
              or (contract_signed_on is not null and quote_issued_on is not null
                  and contract_signed_on < quote_issued_on))
        """,
            0,
        ),
        (
            "계약일보다 앞선 발주",
            """
            select count(*) from purchase_order o
            join sales_deal d on d.id = o.sales_deal_id
            where o.team_id = :team
              and (d.contract_signed_on is null or o.ordered_on < d.contract_signed_on)
        """,
            0,
        ),
        (
            "기준일 이후에 체결된 계약",
            "select count(*) from sales_deal where team_id = :team and contract_signed_on > :base",
            0,
        ),
        (
            "불만 발생이 접수보다 늦음",
            """select count(*) from support_request
            where team_id = :team and occurred_at > registered_at""",
            0,
        ),
        (
            "보고 기간이 뒤집힘",
            """
            select count(*) from report
            where team_id = :team and period_start is not null and period_end < period_start
        """,
            0,
        ),
        # ---------------- 값 · 중복 · 고아
        (
            "고객사 이름 중복",
            """
            select coalesce(sum(c - 1), 0) from (
              select count(*) c from customer_company where team_id = :team
              group by name having count(*) > 1
            ) t
        """,
            0,
        ),
        (
            "우편번호가 5자리 숫자가 아님",
            """
            select count(*) from customer_company
            where team_id = :team and postcode is not null and postcode !~ '^[0-9]{5}$'
        """,
            0,
        ),
        (
            "견적번호 중복",
            """
            select coalesce(sum(c - 1), 0) from (
              select count(*) c from sales_deal where team_id = :team and quote_no is not null
              group by quote_no having count(*) > 1
            ) t
        """,
            0,
        ),
        (
            "자료 번호 중복",
            """
            select coalesce(sum(c - 1), 0) from (
              select count(*) c from document where team_id = :team
              group by document_no having count(*) > 1
            ) t
        """,
            0,
        ),
        (
            "확정 단계인데 계약일이 없음",
            """
            select count(*) from sales_deal d
            join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
            where d.team_id = :team and s.outcome_code = 'confirmed'
              and d.contract_signed_on is null
        """,
            0,
        ),
        (
            "발주 합계가 계약 금액을 넘음",
            """
            select count(*) from (
              select d.id, d.deal_amount, sum(i.quantity * i.unit_price) total
              from sales_deal d
              join purchase_order o on o.sales_deal_id = d.id
              join purchase_order_item i on i.purchase_order_id = o.id
              where d.team_id = :team group by d.id, d.deal_amount
            ) t where t.total > t.deal_amount
        """,
            0,
        ),
        (
            "자료에 제품과 딜이 함께 지정됨",
            """
            select count(*) from document
            where team_id = :team and product_id is not null and sales_deal_id is not null
        """,
            0,
        ),
        (
            "자료실 첨부의 부모가 하나가 아님",
            """
            select count(*) from file f
            join document d on d.id = f.document_id
            where d.team_id = :team and num_nonnulls(f.report_id, f.document_id) <> 1
        """,
            0,
        ),
        (
            "자료실 첨부에 버전이 없음",
            """
            select count(*) from file f
            join document d on d.id = f.document_id
            where d.team_id = :team and f.version_no is null
        """,
            0,
        ),
        (
            "보고서 상태값이 목록 밖",
            """
            select count(*) from report where team_id = :team
              and status_code not in ('draft','submitted','approved','rejected','changes_requested')
        """,
            0,
        ),
        (
            "보고서 종류가 목록 밖",
            """
            select count(*) from report where team_id = :team
              and report_kind not in ('meeting','daily','weekly','monthly')
        """,
            0,
        ),
        (
            "확정 보고서에 검토자가 없음",
            """
            select count(*) from report
            where team_id = :team and status_code = 'approved'
              and (reviewed_by_member_id is null or reviewed_at is null)
        """,
            0,
        ),
        (
            "담당자 없는 고객 담당자",
            """
            select count(*) from customer_contact k
            join customer_company c on c.id = k.company_id
            where c.team_id = :team
              and not exists (
                select 1 from customer_contact_assignee a where a.customer_contact_id = k.id
              )
        """,
            0,
        ),
        # ---------------- 화면이 비어 보이던 자리
        (
            "고객 담당자 이메일 없음",
            """
            select count(*) from customer_contact k
            join customer_company c on c.id = k.company_id
            where c.team_id = :team and k.email is null
        """,
            0,
        ),
        (
            "고객 담당자 이메일 중복",
            """
            select coalesce(sum(n - 1), 0) from (
              select count(*) n from customer_contact k
              join customer_company c on c.id = k.company_id
              where c.team_id = :team and k.email is not null
              group by k.email having count(*) > 1
            ) t
        """,
            0,
        ),
        (
            "완료된 방문 활동이 있는데 미방문",
            """
            select count(distinct k.id) from customer_contact k
            join customer_company c on c.id = k.company_id
            join activity a on a.customer_contact_id = k.id
            join activity_category g on g.id = a.activity_category_id
            where c.team_id = :team and not k.visited
              and g.code = 'visit' and a.completed_at is not null and a.starts_at::date < :base
        """,
            0,
        ),
        (
            "니즈 검증을 넘긴 딜이 있는데 고객 상태가 신규",
            """
            select count(*) from (
              select k.id, cs.code, max(s.position) as p
              from customer_contact k
              join customer_company c on c.id = k.company_id
              join customer_contact_status cs on cs.id = k.customer_contact_status_id
              join sales_deal d on d.customer_contact_id = k.id
              join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
              where c.team_id = :team
              group by k.id, cs.code
            ) t where t.code = 'new' and t.p >= 1
        """,
            0,
        ),
        (
            "고객 담당자 메모가 하나도 없음 (0이면 실패)",
            """
            select case when count(*) = 0 then 1 else 0 end from customer_contact k
            join customer_company c on c.id = k.company_id
            where c.team_id = :team and k.memo is not null
        """,
            0,
        ),
        (
            "담당자 등록보다 딜 개설이 빠름",
            """
            select count(*) from sales_deal d
            join customer_contact k on k.id = d.customer_contact_id
            where d.team_id = :team and d.opened_on < k.registered_at::date
        """,
            0,
        ),
        (
            "고객사 등록보다 딜 개설이 빠름",
            """
            select count(*) from sales_deal d
            join customer_company c on c.id = d.customer_company_id
            where d.team_id = :team and d.opened_on < c.created_at::date
        """,
            0,
        ),
        (
            "30일 이내 계약 종료 확정 딜 수",
            """
            select count(*) from sales_deal d
            join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
            where d.team_id = :team and s.outcome_code = 'confirmed'
              and d.contract_ends_on between :base and :base + 30
        """,
            expected["renewal"],
        ),
        (
            "이번 달 매출목표가 없음 (0이면 실패)",
            """
            select case when coalesce(sum(t.target_amount), 0) = 0 then 1 else 0 end
            from sales_target t
            join member m on m.id = t.owner_member_id
            where m.team_id = :team and m.active
              and t.target_month = date_trunc('month', :base::date)
        """,
            0,
        ),
        (
            "목표가 붙은 고객사에 그 담당자의 딜이 없음",
            """
            select count(*) from sales_target t
            join member m on m.id = t.owner_member_id
            where m.team_id = :team and m.role_code = 'member'
              and not exists (
                select 1 from sales_deal d
                where d.owner_member_id = t.owner_member_id
                  and d.customer_company_id = t.customer_company_id
              )
        """,
            0,
        ),
    )


# 요약으로 함께 보여줄 분포. 실패로 치지 않는다.
SUMMARIES = (
    (
        "일정 분포",
        """
        select case when starts_at::date < :base then '과거'
                    when starts_at::date = :base then '오늘' else '미래' end as 구간,
               count(*) as 건수,
               count(completed_at) as 완료
        from activity where team_id = :team group by 1 order by 1
    """,
    ),
    (
        "보고서 종류·상태",
        """
        select report_kind as 종류, status_code as 상태, count(*) as 건수
        from report where team_id = :team group by 1, 2 order by 1, 2
    """,
    ),
    (
        "고객불만 상태",
        """
        select status_code as 상태, count(*) as 건수,
               count(*) filter (where is_urgent) as 긴급
        from support_request where team_id = :team group by 1 order by 1
    """,
    ),
    (
        "딜 단계",
        """
        select s.position as 순서, s.name as 단계, s.outcome_code as 결과,
               count(d.id) as 건수, coalesce(sum(d.deal_amount), 0) as 금액
        from sales_pipeline_stage s
        join sales_pipeline p on p.id = s.sales_pipeline_id
        left join sales_deal d on d.sales_pipeline_stage_id = s.id
        where p.team_id = :team group by 1, 2, 3 order by 1
    """,
    ),
    (
        "고객 담당자 상태",
        """
        select s.name as 상태, count(*) as 건수,
               count(*) filter (where k.visited) as 방문,
               count(k.memo) as 메모
        from customer_contact k
        join customer_company c on c.id = k.company_id
        join customer_contact_status s on s.id = k.customer_contact_status_id
        where c.team_id = :team group by s.position, 1 order by s.position
    """,
    ),
    (
        "월 매출목표",
        """
        select to_char(t.target_month, 'YYYY-MM') as 월, count(*) as 건수,
               sum(t.target_amount) as 목표
        from sales_target t
        join member m on m.id = t.owner_member_id
        where m.team_id = :team group by 1 order by 1
    """,
    ),
    (
        "자료실 분류",
        """
        select category_code as 분류, count(*) as 건수 from document
        where team_id = :team group by 1 order by 1
    """,
    ),
    (
        "담당자별",
        """
        select m.display_name as 담당자,
               count(distinct d.id) as 딜,
               count(distinct a.id) as 일정,
               count(distinct r.id) as 보고서
        from member m
        left join sales_deal d on d.owner_member_id = m.id
        left join activity a on a.owner_member_id = m.id
        left join report r on r.author_member_id = m.id
        where m.team_id = :team group by 1 order by 1
    """,
    ),
)


async def run_checks(db: AsyncSession, team_id: UUID, base_date: date) -> int:
    params = {"team": str(team_id), "base": base_date}
    failures = 0
    for label, sql, want in checks(expected_counts()):
        value = (await db.execute(text(sql), params)).scalar_one()
        if want is None:
            print(f"  [--] {label}: {value}")
            continue
        ok = value == want
        failures += not ok
        print(f"  [{'OK' if ok else 'FAIL'}] {label}: {value}" + ("" if ok else f" (기대 {want})"))
    return failures


async def show_summaries(db: AsyncSession, team_id: UUID, base_date: date) -> None:
    params = {"team": str(team_id), "base": base_date}
    for label, sql in SUMMARIES:
        rows = (await db.execute(text(sql), params)).all()
        if not rows:
            continue
        print(f"\n=== {label} ===")
        headers = list(rows[0]._mapping)
        widths = [
            max(
                len(str(h)),
                max(
                    (
                        len(
                            f"{r._mapping[h]:,}"
                            if isinstance(r._mapping[h], int)
                            else str(r._mapping[h])
                        )
                        for r in rows
                    ),
                    default=0,
                ),
            )
            for h in headers
        ]
        print("  " + "  ".join(str(h).ljust(w) for h, w in zip(headers, widths, strict=True)))
        print("  " + "  ".join("-" * w for w in widths))
        for row in rows:
            cells = [
                f"{row._mapping[h]:,}" if isinstance(row._mapping[h], int) else str(row._mapping[h])
                for h in headers
            ]
            print("  " + "  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)))


async def main_async(base_date: date) -> None:
    async with get_sessionmaker()() as db:
        print(f"팀 {TEAM_NAME} ({TEAM_ID})")
        print(f"기준일 {base_date.isoformat()}\n")
        print("=== 정합성 검사 ===")
        failures = await run_checks(db, TEAM_ID, base_date)
        await show_summaries(db, TEAM_ID, base_date)
    print(f"\n실패한 검사 {failures}건")
    if failures:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-date", help="기준일 YYYY-MM-DD. 기본값은 실행일입니다.")
    args = parser.parse_args()
    base = date.fromisoformat(args.base_date) if args.base_date else datetime.now(SEOUL).date()
    asyncio.run(main_async(base))


if __name__ == "__main__":
    main()
