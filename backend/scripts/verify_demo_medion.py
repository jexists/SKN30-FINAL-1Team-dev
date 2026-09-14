"""메디온 데모 데이터 검증. 읽기 전용이다.

시더가 끝나면 자동으로 돌고, 따로 돌릴 수도 있다.

    cd backend
    uv run python -m scripts.verify_demo_medion
    uv run python -m scripts.verify_demo_medion --base-date 2026-09-14

검사 하나가 실패하면 종료 코드 1 로 끝난다. 수량은 상수와 원본 엑셀에서 직접 끌어오므로
같은 숫자를 두 곳에 적어 두지 않는다.
"""

import argparse
import asyncio
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from scripts.demo import medion
from scripts.seed_demo_medion import COMPANY_COUNT, STAGE_STEPS

MIN = "min"

DIRECTIVE_COUNT = sum(1 for n in medion.NOTICES if n.type == "DIRECTIVE")
NOTICE_COUNT = sum(1 for n in medion.NOTICES if n.type == "NOTICE")


def _checks() -> tuple[tuple[str, str, Any], ...]:
    """(설명, SQL, 기대값). 기대값이 ('min', n) 이면 n 이상이면 통과, None 이면 보고만 한다.

    SQL 은 스칼라 하나를 돌려준다. :team 과 :base 를 바인딩해 쓴다.
    """
    return (
        # --- 계정·팀 -------------------------------------------------
        (
            "두 데모 계정이 이 팀에서 활성",
            "select count(*) from member"
            " where team_id = :team and active and email = any(:emails)",
            len(medion.MEMBERS),
        ),
        (
            "활성 팀장 1명",
            "select count(*) from member"
            " where team_id = :team and active and role_code = 'manager'",
            1,
        ),
        (
            "팀 전체 활성 구성원 (데모 계정 외에도 있을 수 있음)",
            "select count(*) from member where team_id = :team and active",
            None,
        ),
        (
            "member 가 auth.users 에 없음",
            "select count(*) from member m"
            " where m.team_id = :team"
            "   and not exists (select 1 from auth.users u where u.id = m.id)",
            0,
        ),
        # --- 수량 ----------------------------------------------------
        (
            "고객사 수",
            "select count(*) from customer_company where team_id = :team",
            COMPANY_COUNT,
        ),
        (
            "제품 수",
            "select count(*) from product where team_id = :team",
            len(medion.PRODUCTS),
        ),
        (
            "노출 조건을 통과하는 공지",
            "select count(*) from notice"
            " where team_id = :team and type = 'NOTICE' and deleted_at is null"
            "   and not is_hidden and display_start_date <= :base"
            "   and (display_end_date is null or display_end_date >= :base)",
            NOTICE_COUNT,
        ),
        (
            "노출 조건을 통과하는 팀장 지시사항",
            "select count(*) from notice"
            " where team_id = :team and type = 'DIRECTIVE' and deleted_at is null"
            "   and not is_hidden and display_start_date <= :base"
            "   and (display_end_date is null or display_end_date >= :base)",
            DIRECTIVE_COUNT,
        ),
        (
            "수신자가 없는 지시사항",
            "select count(*) from notice n"
            " where n.team_id = :team and n.type = 'DIRECTIVE'"
            "   and not exists (select 1 from notice_target t where t.notice_id = n.id)",
            0,
        ),
        (
            "수신자가 붙은 공지",
            "select count(*) from notice n"
            " where n.team_id = :team and n.type = 'NOTICE'"
            "   and exists (select 1 from notice_target t where t.notice_id = n.id)",
            0,
        ),
        (
            "지시 이행 상태 종류",
            "select count(distinct t.status_code) from notice_target t"
            " join notice n on n.id = t.notice_id where n.team_id = :team",
            DIRECTIVE_COUNT,
        ),
        (
            "C/S 건수",
            "select count(*) from support_request where team_id = :team",
            len(medion.SUPPORTS),
        ),
        (
            "딜이 모든 파이프라인 단계를 채움",
            "select count(distinct s.stage_code) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and d.deleted_at is null",
            len(STAGE_STEPS),
        ),
        # --- 대시보드가 비지 않는가 ----------------------------------
        (
            "오늘 일정이 있는 담당자 수",
            "select count(distinct owner_member_id) from activity"
            " where team_id = :team and deleted_at is null"
            "   and (starts_at at time zone 'Asia/Seoul')::date = :base",
            len(medion.MEMBERS),
        ),
        (
            "이번 달 일정 수",
            "select count(*) from activity"
            " where team_id = :team and deleted_at is null"
            "   and date_trunc('month', (starts_at at time zone 'Asia/Seoul')::date)"
            "       = date_trunc('month', cast(:base as date))",
            (MIN, 15),
        ),
        (
            "이번 달 목표가 있는 담당자 수",
            "select count(*) from sales_target t join member m on m.id = t.owner_member_id"
            " where m.team_id = :team and m.active and m.email = any(:emails)"
            "   and t.target_month = date_trunc('month', cast(:base as date))::date"
            "   and t.target_amount > 0",
            len(medion.MEMBERS),
        ),
        (
            "이번 달 확정 매출이 있는 담당자 수",
            "select count(distinct d.owner_member_id) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and d.deleted_at is null"
            "   and s.outcome_code = 'confirmed' and d.contract_signed_on is not null"
            "   and date_trunc('month', d.contract_signed_on)"
            "       = date_trunc('month', cast(:base as date))"
            "   and coalesce(d.contract_amount, 0) > 0",
            len(medion.MEMBERS),
        ),
        (
            "계약 갱신 예정(30일 내) 건수",
            "select count(*) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and d.deleted_at is null"
            "   and s.outcome_code = 'confirmed' and d.contract_ends_on is not null"
            "   and d.contract_ends_on between :base and (cast(:base as date) + 30)",
            (MIN, 1),
        ),
        (
            "발주 목록에 보이는 발주 건수 (딜이 order 단계)",
            "select count(*) from purchase_order o"
            " join sales_deal d on d.id = o.sales_deal_id"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where o.team_id = :team and o.deleted_at is null and s.phase_code = 'order'",
            (MIN, 10),
        ),
        (
            "발주가 붙었는데 딜이 order 단계가 아님",
            "select count(*) from purchase_order o"
            " join sales_deal d on d.id = o.sales_deal_id"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where o.team_id = :team and s.phase_code <> 'order'",
            0,
        ),
        # --- 보고서 --------------------------------------------------
        (
            "미팅 보고서에 근거 일정이 없음",
            "select count(*) from report"
            " where team_id = :team and report_kind = 'meeting' and source_activity_id is null",
            0,
        ),
        (
            "미팅 보고서에 딜 섹션이 없음",
            "select count(*) from report r"
            " where r.team_id = :team and r.report_kind = 'meeting'"
            "   and not exists (select 1 from report_deal d where d.report_id = r.id)",
            0,
        ),
        (
            "미팅 정보(부서·담당자·장소)가 빈 보고서",
            "select count(*) from report"
            " where team_id = :team and report_kind = 'meeting'"
            "   and (coalesce(content->>'dept', '') = ''"
            "     or coalesce(content->>'contact', '') = ''"
            "     or coalesce(content->>'place', '') = ''"
            "     or coalesce(content->>'hospital', '') = ''"
            "     or coalesce(content->>'time', '') = '')",
            0,
        ),
        (
            "소제목이 없는 미팅 딜 본문",
            "select count(*) from report_deal d join report r on r.id = d.report_id"
            " where r.team_id = :team and coalesce(d.body, '') not like '%**미팅 목적%'",
            0,
        ),
        (
            "소제목이 없는 일일·주간·월간 본문",
            "select count(*) from report"
            " where team_id = :team and report_kind <> 'meeting'"
            "   and coalesce(body, '') not like '%**%'",
            0,
        ),
        (
            "미팅 공통 기록에 소제목이 섞임",
            "select count(*) from report"
            " where team_id = :team"
            "   and (coalesce(common_body, '') like '%**%'"
            "     or coalesce(unassigned_body, '') like '%**%')",
            0,
        ),
        (
            "ML 근거가 없는 딜 섹션",
            "select count(*) from report_deal d join report r on r.id = d.report_id"
            " where r.team_id = :team"
            "   and coalesce(d.ai_evidence->'deal_assessment'->>'label', '')"
            "       not in ('high', 'watch')",
            0,
        ),
        (
            "딜 2건이 붙은 미팅",
            "select count(*) from ("
            "  select d.report_id from report_deal d join report r on r.id = d.report_id"
            "  where r.team_id = :team group by d.report_id having count(*) > 1) x",
            (MIN, 1),
        ),
        (
            "한 미팅에 고객사가 다른 딜이 섞임",
            "select count(*) from ("
            "  select d.report_id from report_deal d"
            "  join report r on r.id = d.report_id"
            "  join sales_deal s on s.id = d.sales_deal_id"
            "  where r.team_id = :team"
            "  group by d.report_id having count(distinct s.customer_company_id) > 1) x",
            0,
        ),
        (
            "미팅 공통 기록이 있는 보고서",
            "select count(*) from report"
            " where team_id = :team and coalesce(common_body, '') <> ''",
            (MIN, 1),
        ),
        (
            "보고서가 없는 지난 일정",
            "select count(*) from activity a"
            " where a.team_id = :team and a.deleted_at is null"
            "   and (a.starts_at at time zone 'Asia/Seoul')::date < :base"
            "   and not exists (select 1 from report r where r.source_activity_id = a.id)",
            0,
        ),
        (
            "미래 일정에 붙은 보고서",
            "select count(*) from report r join activity a on a.id = r.source_activity_id"
            " where r.team_id = :team"
            "   and (a.starts_at at time zone 'Asia/Seoul')::date > :base",
            0,
        ),
        (
            "오늘 일정에 붙은 확정 보고서",
            "select count(*) from report r join activity a on a.id = r.source_activity_id"
            " where r.team_id = :team and r.status_code = 'approved'"
            "   and (a.starts_at at time zone 'Asia/Seoul')::date = :base",
            0,
        ),
        (
            "검토 대기(submitted) 보고서",
            "select count(*) from report where team_id = :team and status_code = 'submitted'",
            (MIN, 1),
        ),
        (
            "팀장이 검토 완료한 팀원 보고서",
            "select count(*) from report"
            " where team_id = :team and status_code = 'approved'"
            "   and reviewed_by_member_id is not null",
            (MIN, 1),
        ),
        (
            "반려(changes_requested) 보고서",
            "select count(*) from report"
            " where team_id = :team and status_code = 'changes_requested'",
            (MIN, 1),
        ),
        (
            "보고서 종류 수 (미팅·일일·주간·월간)",
            "select count(distinct report_kind) from report where team_id = :team",
            4,
        ),
        (
            "미래 일정이 완료 처리됨",
            "select count(*) from activity"
            " where team_id = :team and completed_at is not null"
            "   and (starts_at at time zone 'Asia/Seoul')::date > :base",
            0,
        ),
        # --- 팀 격리·참조 무결성 -------------------------------------
        (
            "딜이 팀 밖 고객사·담당자를 참조",
            "select count(*) from sales_deal d"
            " left join customer_company c on c.id = d.customer_company_id"
            " left join member m on m.id = d.owner_member_id"
            " where d.team_id = :team and (c.team_id <> :team or m.team_id <> :team)",
            0,
        ),
        (
            "고객 담당자가 팀 밖 고객사에 속함",
            "select count(*) from customer_contact ct"
            " join customer_company c on c.id = ct.company_id"
            " join member m on m.id = ct.owner_member_id"
            " where m.team_id = :team and c.team_id <> :team",
            0,
        ),
        (
            "활동의 고객사가 딜의 고객사와 다름",
            "select count(*) from activity a join sales_deal d on d.id = a.sales_deal_id"
            " where a.team_id = :team and a.customer_company_id <> d.customer_company_id",
            0,
        ),
        (
            "활동 담당자와 고객 담당자의 소유자가 다름",
            "select count(*) from activity a"
            " join customer_contact ct on ct.id = a.customer_contact_id"
            " where a.team_id = :team and a.owner_member_id <> ct.owner_member_id",
            0,
        ),
        (
            "C/S 의 고객사가 딜의 고객사와 다름",
            "select count(*) from support_request r"
            " join sales_deal d on d.id = r.sales_deal_id"
            " where r.team_id = :team and r.customer_company_id <> d.customer_company_id",
            0,
        ),
        (
            "C/S 가 계약 전 딜에 붙음",
            "select count(*) from support_request r"
            " join sales_deal d on d.id = r.sales_deal_id"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where r.team_id = :team and s.phase_code not in ('contract', 'order', 'closed')",
            0,
        ),
        (
            "보고서가 팀 밖 일정을 인용",
            "select count(*) from report r join activity a on a.id = r.source_activity_id"
            " where r.team_id = :team and a.team_id <> :team",
            0,
        ),
        (
            "담당 배정이 없는 고객 담당자",
            "select count(*) from customer_contact ct"
            " join customer_company c on c.id = ct.company_id"
            " where c.team_id = :team and ct.deleted_at is null"
            "   and not exists ("
            "     select 1 from customer_contact_assignee a where a.customer_contact_id = ct.id)",
            0,
        ),
        # --- 값·날짜·중복 --------------------------------------------
        (
            "고객사 이름 중복",
            "select count(*) from ("
            "  select name from customer_company where team_id = :team"
            "  group by name having count(*) > 1) x",
            0,
        ),
        (
            "우편번호 형식 위반",
            "select count(*) from customer_company"
            " where team_id = :team and postcode is not null and postcode !~ '^[0-9]{5}$'",
            0,
        ),
        (
            "지역 코드가 없는 고객사",
            "select count(*) from customer_company where team_id = :team and region_code is null",
            0,
        ),
        (
            "개설일 > 견적일",
            "select count(*) from sales_deal"
            " where team_id = :team and quote_issued_on is not null"
            "   and quote_issued_on < opened_on",
            0,
        ),
        (
            "견적일 > 계약일",
            "select count(*) from sales_deal"
            " where team_id = :team and quote_issued_on is not null"
            "   and contract_signed_on is not null and contract_signed_on < quote_issued_on",
            0,
        ),
        (
            "계약일보다 앞선 발주",
            "select count(*) from purchase_order o join sales_deal d on d.id = o.sales_deal_id"
            " where o.team_id = :team"
            "   and (d.contract_signed_on is null or o.ordered_on < d.contract_signed_on)",
            0,
        ),
        (
            "발주 합계가 계약금액보다 큼",
            "select count(*) from ("
            "  select o.id from purchase_order o"
            "  join sales_deal d on d.id = o.sales_deal_id"
            "  join purchase_order_item i on i.purchase_order_id = o.id"
            "  where o.team_id = :team"
            "  group by o.id, d.contract_amount"
            "  having sum(i.quantity * i.unit_price) > coalesce(d.contract_amount, 0)) x",
            0,
        ),
        (
            "확정 단계인데 계약일이 없음",
            "select count(*) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and s.outcome_code = 'confirmed'"
            "   and d.contract_signed_on is null",
            0,
        ),
        (
            "미래 날짜로 체결된 계약",
            "select count(*) from sales_deal"
            " where team_id = :team and contract_signed_on > :base",
            0,
        ),
        (
            "딜 번호 중복",
            "select count(*) from ("
            "  select deal_no from sales_deal where team_id = :team"
            "  group by deal_no having count(*) > 1) x",
            0,
        ),
        (
            "견적 번호 중복",
            "select count(*) from ("
            "  select quote_no from sales_deal"
            "  where team_id = :team and quote_no is not null"
            "  group by quote_no having count(*) > 1) x",
            0,
        ),
        (
            "계약 번호 중복",
            "select count(*) from ("
            "  select contract_no from sales_deal"
            "  where team_id = :team and contract_no is not null"
            "  group by contract_no having count(*) > 1) x",
            0,
        ),
        (
            "발주 번호 중복",
            "select count(*) from ("
            "  select order_no from purchase_order where team_id = :team"
            "  group by order_no having count(*) > 1) x",
            0,
        ),
        # --- 2년 매출 ------------------------------------------------
        (
            "확정 매출이 잡히는 월 수 (24개월 이상)",
            "select count(*) from ("
            "  select date_trunc('month', d.contract_signed_on) as m from sales_deal d"
            "  join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            "  where d.team_id = :team and d.deleted_at is null"
            "    and s.outcome_code = 'confirmed' and d.contract_signed_on is not null"
            "  group by 1 having sum(coalesce(d.contract_amount, 0)) > 0) x",
            (MIN, 24),
        ),
        (
            "확정 매출이 잡히는 연도 수",
            "select count(distinct extract(year from d.contract_signed_on)) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and s.outcome_code = 'confirmed'",
            (MIN, 3),
        ),
        (
            "목표를 넘긴 담당자·월",
            "select count(*) from ("
            "  select t.owner_member_id, t.target_month,"
            "         sum(coalesce(d.contract_amount, 0)) as actual, t.target_amount"
            "  from sales_target t"
            "  join member m on m.id = t.owner_member_id"
            "  left join sales_deal d on d.owner_member_id = t.owner_member_id"
            "    and date_trunc('month', d.contract_signed_on) = t.target_month"
            "  left join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            "    and s.outcome_code = 'confirmed'"
            "  where m.team_id = :team and m.email = any(:emails)"
            "    and s.outcome_code = 'confirmed'"
            "  group by 1, 2, 4 having sum(coalesce(d.contract_amount, 0)) > t.target_amount) x",
            (MIN, 1),
        ),
        (
            "회사별 목표 행 (팀 화면과 대시보드가 갈리므로 0이어야 함)",
            "select count(*) from sales_target t join member m on m.id = t.owner_member_id"
            " where m.team_id = :team and m.email = any(:emails)"
            "   and t.customer_company_id is not null",
            0,
        ),
    )


def _reports() -> tuple[tuple[str, str], ...]:
    return (
        (
            "표별 행 수",
            "select 'customer_company' as t, count(*) from customer_company where team_id = :team"
            " union all select 'customer_contact', count(*) from customer_contact ct"
            "   join customer_company c on c.id = ct.company_id where c.team_id = :team"
            " union all select 'sales_deal', count(*) from sales_deal where team_id = :team"
            " union all select 'activity', count(*) from activity where team_id = :team"
            " union all select 'report', count(*) from report where team_id = :team"
            " union all select 'purchase_order', count(*) from purchase_order where team_id = :team"
            " union all select 'support_request', count(*) from support_request"
            "   where team_id = :team"
            " union all select 'notice', count(*) from notice where team_id = :team"
            " union all select 'sales_target', count(*) from sales_target t"
            "   join member m on m.id = t.owner_member_id where m.team_id = :team"
            " union all select 'product', count(*) from product where team_id = :team",
        ),
        (
            "단계별 딜",
            "select s.position, s.name, count(*), sum(d.deal_amount) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and d.deleted_at is null"
            " group by 1, 2 order by 1",
        ),
        (
            "연도별 확정 매출",
            "select extract(year from d.contract_signed_on)::int as y, count(*),"
            "       sum(coalesce(d.contract_amount, 0)) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and s.outcome_code = 'confirmed'"
            " group by 1 order by 1",
        ),
        (
            "최근 6개월 확정 매출",
            "select to_char(d.contract_signed_on, 'YYYY-MM') as m, count(*),"
            "       sum(coalesce(d.contract_amount, 0)) from sales_deal d"
            " join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where d.team_id = :team and s.outcome_code = 'confirmed'"
            "   and d.contract_signed_on > (cast(:base as date) - 185)"
            " group by 1 order by 1",
        ),
        (
            "담당자별 이번 달 목표 대비 실적",
            "select m.display_name, t.target_amount,"
            "       coalesce(sum(d.contract_amount) filter (where s.outcome_code = 'confirmed'), 0)"
            " from member m"
            " left join sales_target t on t.owner_member_id = m.id"
            "   and t.target_month = date_trunc('month', cast(:base as date))::date"
            " left join sales_deal d on d.owner_member_id = m.id"
            "   and date_trunc('month', d.contract_signed_on)"
            "       = date_trunc('month', cast(:base as date))"
            " left join sales_pipeline_stage s on s.id = d.sales_pipeline_stage_id"
            " where m.team_id = :team and m.email = any(:emails)"
            " group by 1, 2 order by 1",
        ),
        (
            "보고서 종류·상태",
            "select report_kind, status_code, count(*) from report"
            " where team_id = :team group by 1, 2 order by 1, 2",
        ),
        (
            "일정 구간",
            "select case"
            "    when (starts_at at time zone 'Asia/Seoul')::date < :base then '과거'"
            "    when (starts_at at time zone 'Asia/Seoul')::date = :base then '오늘'"
            "    else '미래' end as bucket,"
            "  count(*), count(completed_at) from activity"
            " where team_id = :team and deleted_at is null group by 1 order by 1",
        ),
        (
            "C/S 상태",
            "select status_code, count(*), count(*) filter (where is_urgent)"
            " from support_request where team_id = :team group by 1 order by 1",
        ),
        (
            "지시사항 이행 현황",
            "select n.title, t.status_code from notice n"
            " join notice_target t on t.notice_id = n.id"
            " where n.team_id = :team order by n.sort_order",
        ),
    )


def _table(rows: list[Any]) -> str:
    if not rows:
        return "    (없음)"
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(cells[0]))]
    return "\n".join(
        "    " + "  ".join(cell.rjust(widths[i]) for i, cell in enumerate(row)) for row in cells
    )


async def run(db: AsyncSession, base: date) -> int:
    params = {
        "team": str(medion.TEAM_ID),
        "base": base,
        "emails": list(medion.EMAILS),
    }
    failures = 0

    print("검증")
    for label, sql, expected in _checks():
        value = (await db.execute(text(sql), params)).scalar_one()
        if expected is None:
            print(f"  [--] {label}: {value}")
            continue
        if isinstance(expected, tuple):
            ok = value >= expected[1]
            want = f">= {expected[1]}"
        else:
            ok = value == expected
            want = str(expected)
        if ok:
            print(f"  [OK] {label}: {value}")
        else:
            failures += 1
            print(f"  [FAIL] {label}: {value} (기대 {want})")

    print()
    for label, sql in _reports():
        rows = (await db.execute(text(sql), params)).all()
        print(f"  {label}")
        print(_table([list(r) for r in rows]))
        print()

    if failures:
        print(f"실패한 검사 {failures}건")
    else:
        print("검사 전부 통과")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="메디온 데모 데이터 검증 (읽기 전용)")
    parser.add_argument("--base-date", help="기준일 YYYY-MM-DD. 기본값은 실행일입니다.")
    args = parser.parse_args()
    base = (
        date.fromisoformat(args.base_date)
        if args.base_date
        else datetime.now(ZoneInfo("Asia/Seoul")).date()
    )

    async def go() -> int:
        async with get_sessionmaker()() as db:
            return await run(db, base)

    if asyncio.run(go()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
