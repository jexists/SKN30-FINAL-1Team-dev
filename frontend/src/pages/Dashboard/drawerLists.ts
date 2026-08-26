// KPI 타일을 누르면 열리는 목록 세 가지. 셋 다 같은 드로어 한 벌에 담깁니다.
//
// 어느 목록이든 서버가 준 것을 그리기만 합니다. 거르고 정렬하는 일은 카드 숫자를 만든
// 조건과 같아야 해서 서버에 두었습니다. 여기서 다시 거르면 타일과 목록이 어긋납니다.
import { STATUS_LABEL as SUPPORT_STATUS_LABEL } from '@/pages/Complaints/statuses'
import type { ActivityRead, FollowUpCard, SalesDealResponse, SupportRequestResponse } from '@/types'
import { ddayLabel, fmtDay, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

export type DrawerListTone = 'risk' | 'good' | 'now'

export interface DrawerListRow {
  key: string
  title: string
  titleNote?: string
  note: string
  tags: { text: string; tone?: DrawerListTone }[]
  side: {
    strong: string
    late?: boolean
    numeric?: boolean
    lines?: { text: string; numeric?: boolean }[]
  }
  orderNo?: string
}

export interface DrawerList {
  title: string
  sub: string
  rows: DrawerListRow[]
  empty?: string
}

export type KpiListKey = 'followUp' | 'cs' | 'renewal'

const DAY = 86_400_000
const daysUntil = (dateISO: string) =>
  Math.round((parseISO(dateISO).getTime() - TODAY.getTime()) / DAY)

export function csList(requests: SupportRequestResponse[]): DrawerList {
  // 상태는 접수·원인파악·처리중·처리완료 네 가지입니다. 처리완료가 아니면 아직 남은
  // 건이므로 '미완료' 로 묶어 셉니다. in_progress 만 세면 접수와 원인파악이 완료 쪽으로
  // 넘어가 숫자가 틀립니다.
  const open = requests.filter((request) => request.status_code !== 'completed').length
  const done = requests.length - open
  return {
    title: 'C/S 대응요청',
    sub: `미완료 ${open}건 · 처리완료 ${done}건`,
    rows: [...requests]
      .sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))
      .map((request) => ({
        key: request.id,
        title: request.title,
        titleNote: `${request.customer_company_name} · ${request.contract_no ?? request.deal_no}`,
        note: request.body,
        tags: [
          ...(request.is_urgent ? [{ text: '긴급', tone: 'risk' as const }] : []),
          {
            text: SUPPORT_STATUS_LABEL[request.status_code],
            tone: request.status_code === 'completed' ? ('good' as const) : undefined,
          },
        ],
        side: {
          strong: SUPPORT_STATUS_LABEL[request.status_code],
          late: request.status_code !== 'completed',
          lines: [{ text: fmtDay(new Date(request.occurred_at)) }],
        },
      })),
    empty: '등록된 C/S 대응요청이 없습니다.',
  }
}

export function renewalList(deals: SalesDealResponse[]): DrawerList {
  return {
    title: '계약갱신 예정',
    sub: '계약 종료일 30일 이내',
    rows: deals.map((deal) => {
      // 서버가 종료일 있는 딜만 보내지만 타입에는 남아 있습니다. 없으면 오늘로 읽습니다.
      const endsOn = deal.contract_ends_on
      return {
        key: deal.id,
        title: deal.customer_company_name,
        titleNote: deal.owner_display_name,
        note: deal.description ?? deal.memo ?? '등록된 메모가 없습니다.',
        tags: [
          { text: deal.deal_type_name },
          { text: deal.contract_no ?? deal.deal_no },
          ...(endsOn ? [{ text: `종료 ${fmtDay(parseISO(endsOn))}`, tone: 'now' as const }] : []),
        ],
        side: {
          strong: endsOn ? ddayLabel(daysUntil(endsOn)) : '종료일 미정',
          numeric: endsOn !== null,
          lines: [{ text: won(deal.deal_amount), numeric: true }],
        },
      }
    }),
    empty: '30일 이내 종료 예정인 계약이 없습니다.',
  }
}

export function followUpList(items: ActivityRead[], card: FollowUpCard): DrawerList {
  return {
    title: '미완료 후속업무',
    // 지연과 이번 주 마감은 타일과 같은 숫자여야 합니다. 서버가 센 값을 그대로 씁니다.
    sub: `지연 ${card.overdue}건 · 이번 주 마감 ${card.due_within_7_days}건`,
    rows: items.map((item) => {
      const dueISO = item.due_at?.slice(0, 10) ?? null
      const remaining = dueISO === null ? null : daysUntil(dueISO)
      const late = remaining !== null && remaining < 0
      return {
        key: item.id,
        title: item.title,
        titleNote: [item.customer_company_name, item.customer_contact_name]
          .filter(Boolean)
          .join(' · '),
        note: item.note ?? '등록된 메모가 없습니다.',
        tags: [
          ...(late ? [{ text: '지연', tone: 'risk' as const }] : []),
          { text: dueISO === null ? '마감 미정' : `마감 ${fmtDay(parseISO(dueISO))}` },
        ],
        side: {
          strong: remaining === null ? '마감 미정' : ddayLabel(remaining),
          late,
          numeric: remaining !== null,
        },
      }
    }),
    empty: '미완료 후속업무가 없습니다.',
  }
}
