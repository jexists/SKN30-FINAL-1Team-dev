import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { followUps } from '@/shared/counters'
import type { SupportRequestResponse } from '@/types'
import { addDays, ddayLabel, fmtDay, parseISO, TODAY, TODAY_ISO } from '@/utils/date'
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

function csList(requests: SupportRequestResponse[]): DrawerList {
  const working = requests.filter((request) => request.status_code === 'in_progress').length
  const done = requests.length - working
  return {
    title: 'C/S 대응요청',
    sub: `처리중 ${working}건 · 처리완료 ${done}건`,
    rows: [...requests]
      .sort((a, b) => b.registered_at.localeCompare(a.registered_at))
      .map((request) => ({
        key: request.id,
        title: request.title,
        titleNote: `${request.customer_company_name} · ${request.customer_contact_name}`,
        note: request.body,
        tags: [
          ...(request.is_urgent ? [{ text: '긴급', tone: 'risk' as const }] : []),
          {
            text: request.status_code === 'completed' ? '처리완료' : '처리중',
            tone: request.status_code === 'completed' ? ('good' as const) : undefined,
          },
        ],
        side: {
          strong: request.status_code === 'completed' ? '처리완료' : '처리중',
          late: request.status_code === 'in_progress',
          lines: [{ text: fmtDay(new Date(request.registered_at)) }],
        },
      })),
    empty: '등록된 C/S 대응요청이 없습니다.',
  }
}

function renewalList(deals: SalesDeal[]): DrawerList {
  const end = addDays(TODAY, 30)
  const rows = deals
    .filter(
      (deal) =>
        deal.contractEndsOn !== null &&
        deal.status !== '취소' &&
        deal.contractEndsOn >= TODAY_ISO &&
        deal.contractEndsOn <= end.toISOString().slice(0, 10),
    )
    .sort((a, b) => (a.contractEndsOn ?? '').localeCompare(b.contractEndsOn ?? ''))

  return {
    title: '계약갱신 예정',
    sub: '계약 종료일 30일 이내',
    rows: rows.map((deal) => {
      const remaining = daysUntil(deal.contractEndsOn ?? TODAY_ISO)
      return {
        key: deal.id,
        title: deal.org,
        titleNote: deal.owner,
        note: deal.memo ?? deal.warrantyTerms ?? '등록된 메모가 없습니다.',
        tags: [
          { text: deal.kind },
          { text: deal.contractNo ?? deal.no },
          { text: `종료 ${fmtDay(parseISO(deal.contractEndsOn ?? TODAY_ISO))}`, tone: 'now' },
        ],
        side: {
          strong: ddayLabel(remaining),
          numeric: true,
          lines: [{ text: won(deal.amount), numeric: true }],
        },
      }
    }),
    empty: '30일 이내 종료 예정인 계약이 없습니다.',
  }
}

function followUpList(): DrawerList {
  const late = followUps.filter((item) => item.dueOff < 0).length
  const week = followUps.filter((item) => item.dueOff >= 0 && item.dueOff <= 7).length

  return {
    title: '미완료 후속업무',
    sub: `지연 ${late}건 · 이번 주 마감 ${week}건`,
    rows: [...followUps]
      .sort((a, b) => a.dueOff - b.dueOff)
      .map((item, index) => ({
        key: `followUp-${index}`,
        title: item.task,
        titleNote: `${item.org} · ${item.who}`,
        note: item.note,
        tags: [
          ...(item.dueOff < 0 ? [{ text: '지연', tone: 'risk' as const }] : []),
          { text: `마감 ${fmtDay(addDays(TODAY, item.dueOff))}` },
        ],
        side: { strong: ddayLabel(item.dueOff), late: item.dueOff < 0, numeric: true },
      })),
    empty: '미완료 후속업무가 없습니다.',
  }
}

export function kpiList(
  key: KpiListKey,
  requests: SupportRequestResponse[],
  deals: SalesDeal[],
): DrawerList {
  if (key === 'cs') return csList(requests)
  if (key === 'renewal') return renewalList(deals)
  return followUpList()
}
