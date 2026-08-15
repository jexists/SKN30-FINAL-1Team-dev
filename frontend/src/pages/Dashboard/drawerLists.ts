// demo/layout_v3.html 의 "Shared list drawer" 입니다.
// KPI 타일 뒤에도, 발주 타일 뒤에도 같은 목록 드로어 하나가 섭니다.
//
// 타일의 숫자는 SummaryBand·PurchaseOrders 가 같은 원본에서 세고, 여기서는
// 그 원본을 줄로 펼치기만 합니다. 목록을 따로 만들면 숫자와 어긋납니다.
import { csSnapshot, followUps, renewals } from '@/shared/counters'
import { activeOrders, orderItemLabel, orderTotal } from '@/shared/orders'
import { addDays, ddayLabel, fmtDay, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

import { ORDER_FILTERS, orderFilter, type OrderFilterKey } from './orderFilters'

export type DrawerListTone = 'risk' | 'good' | 'now'

export interface DrawerListRow {
  key: string
  title: string
  /** 제목 옆에 붙는 작은 글씨. 보통 고객사와 담당자입니다. */
  titleNote?: string
  note: string
  tags: { text: string; tone?: DrawerListTone }[]
  side: {
    strong: string
    /** 기한을 넘긴 값. 주황으로 세웁니다. */
    late?: boolean
    numeric?: boolean
    lines?: { text: string; numeric?: boolean }[]
  }
  /** 있으면 그 줄은 버튼이 되고 누르면 발주 상세로 넘어갑니다. */
  orderNo?: string
}

export interface DrawerList {
  title: string
  sub: string
  rows: DrawerListRow[]
  empty?: string
}

export type KpiListKey = 'followUp' | 'cs' | 'renewal'

function followUpList(): DrawerList {
  const late = followUps.filter((f) => f.dueOff < 0).length
  const week = followUps.filter((f) => f.dueOff >= 0 && f.dueOff <= 7).length

  return {
    title: '미완료 후속업무',
    sub: `지연 ${late}건 · 이번 주 마감 ${week}건`,
    rows: [...followUps]
      .sort((a, b) => a.dueOff - b.dueOff)
      .map((f, i) => ({
        key: `followUp-${i}`,
        title: f.task,
        titleNote: `${f.org} · ${f.who}`,
        note: f.note,
        tags: [
          ...(f.dueOff < 0 ? [{ text: '지연', tone: 'risk' as const }] : []),
          { text: `마감 ${fmtDay(addDays(TODAY, f.dueOff))}` },
        ],
        side: { strong: ddayLabel(f.dueOff), late: f.dueOff < 0, numeric: true },
      })),
  }
}

function csList(): DrawerList {
  // 고객불만관리 화면과 같은 목록입니다. 그쪽에서 등록하거나 상태를 바꾼 것이 여기 그대로 보입니다.
  const rows = csSnapshot()
  const working = rows.filter((c) => c.state === '처리중').length
  const done = rows.length - working

  return {
    title: 'C/S 대응요청',
    sub: `처리중 ${working}건 · 처리완료 ${done}건`,
    // 스토어가 이미 접수 최신순으로 들고 있습니다.
    rows: rows.map((c) => ({
      key: c.id,
      title: c.issue,
      // 화면에서 등록한 건에는 접수자·제품이 없습니다. 빈 칸을 가운뎃점으로 잇지 않습니다.
      titleNote: [c.org, c.who].filter(Boolean).join(' · '),
      note: c.note,
      tags: [
        ...(c.urgent ? [{ text: '긴급', tone: 'risk' as const }] : []),
        { text: c.state, tone: c.state === '처리완료' ? ('good' as const) : undefined },
        ...(c.product ? [{ text: c.product }] : []),
      ],
      side: {
        strong: c.state,
        late: c.state === '처리중',
        lines: [{ text: c.ago }],
      },
    })),
  }
}

function renewalList(): DrawerList {
  return {
    title: '계약갱신 예정',
    sub: '만료 30일 이내 계약',
    rows: [...renewals]
      .sort((a, b) => a.expireOff - b.expireOff)
      .map((r, i) => ({
        key: `renewal-${i}`,
        title: r.org,
        titleNote: r.who,
        note: r.note,
        tags: [
          { text: r.kind },
          { text: r.contract },
          { text: `만료 ${fmtDay(addDays(TODAY, r.expireOff))}`, tone: 'now' as const },
        ],
        side: {
          strong: ddayLabel(r.expireOff),
          numeric: true,
          lines: [{ text: won(r.amount), numeric: true }],
        },
      })),
  }
}

export function kpiList(key: KpiListKey): DrawerList {
  if (key === 'followUp') return followUpList()
  if (key === 'cs') return csList()
  return renewalList()
}

export function orderList(key: OrderFilterKey): DrawerList {
  const f = orderFilter(key)

  return {
    title: '발주 진행 현황',
    sub: `${f.label} · ${f.note()}`,
    empty: `${f.label}에 해당하는 발주가 없습니다.`,
    // 입고가 빠른 건부터 봅니다.
    rows: activeOrders()
      .filter(f.test)
      .sort((a, b) => a.expectOff - b.expectOff)
      .map((o) => {
        const over = o.expectOff - o.dueOff
        return {
          key: o.no,
          title: o.hospital,
          titleNote: o.no,
          note: `${orderItemLabel(o)} · ${o.supplier}`,
          tags: [
            { text: o.status },
            ...(over > 0 ? [{ text: `납기 ${over}일 초과`, tone: 'risk' as const }] : []),
            { text: `납기 ${fmtDay(parseISO(o.due))}` },
          ],
          side: {
            strong: ddayLabel(o.expectOff),
            late: over > 0,
            numeric: true,
            lines: [{ text: won(orderTotal(o)), numeric: true }, { text: '예상 입고' }],
          },
          orderNo: o.no,
        }
      }),
  }
}

/** 목록 드로어 위에 서는 발주 필터 칩. 건수는 타일과 같은 조건표에서 셉니다. */
export function orderFilterChips(): { key: OrderFilterKey; label: string; n: number }[] {
  const active = activeOrders()
  return ORDER_FILTERS.map((f) => ({
    key: f.key,
    label: f.label,
    n: active.filter(f.test).length,
  }))
}
