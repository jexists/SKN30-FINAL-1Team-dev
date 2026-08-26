"""seed_sample_bracelet 이 넣은 데이터를 읽기 전용으로 검증한다.

관계·날짜·금액이 어긋난 행을 세고, 대시보드가 쓰는 것과 같은 기준으로 월별 매출과
담당자별 실적을 집계한다. 아무것도 고치지 않는다.

    uv run python -m scripts.verify_sample_bracelet
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from scripts.seed_sample_bracelet import OWNER_EMAILS, TEAM_NAME

# 팀은 계정 이메일로 찾는다. 스크립트에 UUID 를 두지 않는다.
TEAM_SQL = """
    select distinct m.team_id
    from public.member m
    join public.team t on t.id = m.team_id
    where m.email = any(:emails) and t.name = :team_name
"""

# (제목, SQL, 기대값). 기대값이 None 이면 개수만 보고한다.
CHECKS: tuple[tuple[str, str, int | None], ...] = (
    (
        "딜이 팀 밖 고객사를 참조",
        """
        select count(*) from public.sales_deal d
        left join public.customer_company c on c.id = d.customer_company_id
        where d.team_id = :team and (c.id is null or c.team_id <> d.team_id)
        """,
        0,
    ),
    (
        "딜이 팀 밖 담당자를 참조",
        """
        select count(*) from public.sales_deal d
        left join public.member m on m.id = d.owner_member_id
        where d.team_id = :team and (m.id is null or m.team_id <> d.team_id)
        """,
        0,
    ),
    (
        "고객 담당자가 팀 밖 고객사를 참조",
        """
        select count(*) from public.customer_contact k
        join public.customer_company c on c.id = k.company_id
        join public.member m on m.id = k.owner_member_id
        where m.team_id = :team and c.team_id <> :team
        """,
        0,
    ),
    (
        "활동이 다른 고객사의 딜에 붙음",
        """
        select count(*) from public.activity a
        join public.sales_deal d on d.id = a.sales_deal_id
        join public.customer_contact k on k.id = a.customer_contact_id
        where a.team_id = :team and d.customer_company_id <> k.company_id
        """,
        0,
    ),
    (
        "발주가 팀 밖 딜을 참조",
        """
        select count(*) from public.purchase_order o
        left join public.sales_deal d on d.id = o.sales_deal_id
        where o.team_id = :team and (d.id is null or d.team_id <> o.team_id)
        """,
        0,
    ),
    (
        "불만의 고객사가 딜의 고객사와 다름",
        """
        select count(*) from public.support_request s
        join public.sales_deal d on d.id = s.sales_deal_id
        where s.team_id = :team and s.customer_company_id <> d.customer_company_id
        """,
        0,
    ),
    (
        "미팅보고서에 근거 일정이 없음",
        """
        select count(*) from public.report r
        where r.team_id = :team and r.report_kind = 'meeting' and r.source_activity_id is null
        """,
        0,
    ),
    (
        "보고서가 다른 팀의 일정을 인용",
        """
        select count(*) from public.report r
        join public.report_activity ra on ra.report_id = r.id
        join public.activity a on a.id = ra.activity_id
        where r.team_id = :team and a.team_id <> r.team_id
        """,
        0,
    ),
    (
        "날짜 순서가 어긋난 딜 (개설 > 견적 > 계약)",
        """
        select count(*) from public.sales_deal
        where team_id = :team and (
            (quote_issued_on is not null and quote_issued_on < opened_on)
            or (contract_signed_on is not null and quote_issued_on is not null
                and contract_signed_on < quote_issued_on)
            or (closed_on is not null and closed_on < opened_on)
        )
        """,
        0,
    ),
    (
        "발주일이 계약일보다 앞선 발주",
        """
        select count(*) from public.purchase_order o
        join public.sales_deal d on d.id = o.sales_deal_id
        where o.team_id = :team
          and (d.contract_signed_on is null or o.ordered_on < d.contract_signed_on)
        """,
        0,
    ),
    (
        "기준일(2026-08-25) 이후에 일어난 것으로 기록된 활동",
        """
        select count(*) from public.activity
        where team_id = :team
          and (timezone('Asia/Seoul', starts_at))::date > date '2026-08-25'
        """,
        0,
    ),
    (
        "기준일 이후 날짜의 계약·견적 발행일",
        """
        select count(*) from public.sales_deal
        where team_id = :team and (
            opened_on > date '2026-08-25'
            or quote_issued_on > date '2026-08-25'
            or contract_signed_on > date '2026-08-25'
        )
        """,
        0,
    ),
    (
        "발주 금액이 계약 금액을 넘는 딜",
        """
        select count(*) from (
            select d.id, d.deal_amount, sum(i.quantity * i.unit_price) as ordered
            from public.sales_deal d
            join public.purchase_order o on o.sales_deal_id = d.id and o.deleted_at is null
            join public.purchase_order_item i on i.purchase_order_id = o.id
            where d.team_id = :team
            group by d.id, d.deal_amount
        ) t where t.ordered > t.deal_amount
        """,
        0,
    ),
    (
        "확정 단계인데 계약일이 없는 딜",
        """
        select count(*) from public.sales_deal d
        join public.sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
        where d.team_id = :team and s.outcome_code = 'confirmed'
          and d.contract_signed_on is null
        """,
        0,
    ),
    (
        "견적번호·계약번호가 중복된 딜",
        """
        select coalesce(sum(c), 0) from (
            select count(*) - 1 as c from public.sales_deal
            where team_id = :team and quote_no is not null
            group by quote_no having count(*) > 1
        ) t
        """,
        0,
    ),
)

REPORTS: tuple[tuple[str, str], ...] = (
    (
        "테이블별 행 수",
        """
        select '고객사' as 항목, count(*)::text as 값 from public.customer_company
            where team_id = :team
        union all select '고객 담당자', count(*)::text from public.customer_contact k
            join public.customer_company c on c.id = k.company_id where c.team_id = :team
        union all select '딜', count(*)::text from public.sales_deal where team_id = :team
        union all select '활동', count(*)::text from public.activity where team_id = :team
        union all select '보고서', count(*)::text from public.report where team_id = :team
        union all select '발주', count(*)::text from public.purchase_order where team_id = :team
        union all select '고객불만', count(*)::text from public.support_request
            where team_id = :team
        union all select '매출목표', count(*)::text from public.sales_target t
            join public.member m on m.id = t.owner_member_id where m.team_id = :team
        union all select '공지·지시', count(*)::text from public.notice where team_id = :team
        """,
    ),
    (
        "단계별 딜",
        """
        select s.name as 단계, s.outcome_code as 결과,
               count(*)::text as 건수, to_char(sum(d.deal_amount), 'FM999,999,999,999') as 금액
        from public.sales_deal d
        join public.sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
        where d.team_id = :team
        group by s.name, s.outcome_code, s.position order by s.position
        """,
    ),
    (
        "월별 매출 (확정 딜의 계약월 기준, 대시보드와 같은 집계)",
        """
        select to_char(d.contract_signed_on, 'YYYY-MM') as 월,
               count(*)::text as 계약건수,
               to_char(sum(d.deal_amount), 'FM999,999,999,999') as 매출
        from public.sales_deal d
        join public.sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
        where d.team_id = :team and s.outcome_code = 'confirmed'
        group by 1 order by 1
        """,
    ),
    (
        "담당자별 실적",
        """
        select m.display_name as 담당자,
               count(*)::text as 딜,
               count(*) filter (where s.outcome_code = 'confirmed')::text as 확정,
               count(*) filter (where d.quote_issued_on is not null)::text as 견적,
               to_char(coalesce(sum(d.deal_amount) filter
                   (where s.outcome_code = 'confirmed'), 0), 'FM999,999,999,999') as 매출
        from public.sales_deal d
        join public.sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
        join public.member m on m.id = d.owner_member_id
        where d.team_id = :team
        group by m.display_name order by m.display_name
        """,
    ),
    (
        "담당자별 활동·보고서",
        """
        select m.display_name as 담당자,
               (select count(*) from public.activity a
                where a.owner_member_id = m.id and a.activity_type = 'meeting')::text as 미팅,
               (select count(*) from public.activity a
                where a.owner_member_id = m.id and a.activity_type = 'task')::text as 업무,
               (select count(*) from public.report r
                where r.author_member_id = m.id)::text as 보고서,
               (select count(*) from public.customer_contact k
                where k.owner_member_id = m.id)::text as 고객
        from public.member m where m.team_id = :team order by m.display_name
        """,
    ),
    (
        "월 목표 대비 달성률",
        """
        select to_char(t.target_month, 'YYYY-MM') as 월, m.display_name as 담당자,
               to_char(sum(t.target_amount), 'FM999,999,999,999') as 목표,
               to_char(coalesce((
                   select sum(d.deal_amount) from public.sales_deal d
                   join public.sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
                   where d.owner_member_id = m.id and s.outcome_code = 'confirmed'
                     and date_trunc('month', d.contract_signed_on) = t.target_month
               ), 0), 'FM999,999,999,999') as 실적
        from public.sales_target t
        join public.member m on m.id = t.owner_member_id
        where m.team_id = :team
        group by t.target_month, m.id, m.display_name
        order by 1, 2
        """,
    ),
    (
        "계약 → 발주 → 납품 흐름",
        """
        select d.deal_no as 딜, c.name as 고객사, d.contract_no as 계약번호,
               to_char(d.deal_amount, 'FM999,999,999,999') as 계약금액,
               count(o.id)::text as 발주건수,
               to_char(coalesce(sum(i.quantity * i.unit_price), 0),
                       'FM999,999,999,999') as 발주금액
        from public.sales_deal d
        join public.customer_company c on c.id = d.customer_company_id
        join public.sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id
        left join public.purchase_order o on o.sales_deal_id = d.id and o.deleted_at is null
        left join public.purchase_order_item i on i.purchase_order_id = o.id
        where d.team_id = :team and s.outcome_code = 'confirmed'
        group by d.deal_no, c.name, d.contract_no, d.deal_amount
        order by d.deal_no
        """,
    ),
    (
        "보고서 종류·상태",
        """
        select report_kind as 종류, status_code as 상태, count(*)::text as 건수
        from public.report where team_id = :team
        group by 1, 2 order by 1, 2
        """,
    ),
)


async def run(db: AsyncSession, team_id: str) -> int:
    failures = 0
    print("=== 정합성 검사 ===")
    for label, sql, expected in CHECKS:
        value = (await db.execute(text(sql), {"team": team_id})).scalar_one()
        ok = expected is None or value == expected
        failures += 0 if ok else 1
        print(f"  [{'OK' if ok else 'FAIL'}] {label}: {value}")

    for label, sql in REPORTS:
        print(f"\n=== {label} ===")
        result = await db.execute(text(sql), {"team": team_id})
        columns = list(result.keys())
        rows = result.all()
        widths = [
            max(len(str(column)), *(len(str(row[index])) for row in rows))
            if rows
            else len(str(column))
            for index, column in enumerate(columns)
        ]
        header = "  ".join(
            str(column).ljust(width) for column, width in zip(columns, widths, strict=True)
        )
        print("  " + header)
        print("  " + "-" * len(header))
        for row in rows:
            print(
                "  "
                + "  ".join(
                    str(value).ljust(width) for value, width in zip(row, widths, strict=True)
                )
            )
    return failures


async def main() -> None:
    async with get_sessionmaker()() as session:
        team_id = (
            await session.execute(
                text(TEAM_SQL),
                {"emails": list(OWNER_EMAILS.values()), "team_name": TEAM_NAME},
            )
        ).scalar_one_or_none()
        if team_id is None:
            raise SystemExit(f"'{TEAM_NAME}' 팀을 찾지 못했습니다.")
        print(f"팀 {TEAM_NAME} ({team_id})\n")
        failures = await run(session, team_id)
    print(f"\n실패한 검사 {failures} 건")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
