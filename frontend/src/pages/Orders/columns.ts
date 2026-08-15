// 목록 표의 열입니다. 무엇을 보여 주고 무엇으로 정렬하는지를 한 곳에 모읍니다.
//
// 상태 열만 보이는 값과 정렬 기준이 다릅니다. 이름순으로 세우면 '승인대기 → 입고완료'
// 같은 진행 순서가 흐트러져 ORDER_STATUSES 의 순서를 그대로 씁니다.
import { orderItemLabel, orderTotal } from '@/shared/orders'
import type { PurchaseOrder } from '@/types'
import { fmtDotShort, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import { ORDER_STATUSES, ownerOfOrder } from './pipeline'

export interface OrderColumn {
  id: string
  header: string
  width: number
  /** 금액처럼 오른쪽에 붙는 열 */
  align?: 'right'
  /** 자릿수를 맞출 열(tnum) */
  numeric?: boolean
  sortable?: boolean
  /** 셀에 찍을 글자. 상태는 표에서 배지로 그립니다. */
  text: (order: PurchaseOrder) => string
  /** 정렬 기준. 없으면 text 를 씁니다. */
  sortValue?: (order: PurchaseOrder) => string | number
}

export const ORDER_COLUMNS: OrderColumn[] = [
  { id: 'no', header: '발주번호', width: 140, numeric: true, sortable: true, text: (o) => o.no },
  { id: 'hospital', header: '고객사', width: 150, sortable: true, text: (o) => o.hospital },
  { id: 'items', header: '품목', width: 170, sortable: true, text: orderItemLabel },
  { id: 'supplier', header: '공급처', width: 140, sortable: true, text: (o) => o.supplier },
  {
    // 발주에는 담당자가 없어 연결된 계약에서 가져옵니다. 계약 없는 선발주는 빈칸입니다.
    // 여러 사람의 발주가 섞여 보일 때만 표에 나옵니다.
    id: 'owner',
    header: '담당 영업',
    width: 96,
    sortable: true,
    text: (o) => ownerOfOrder(o) ?? '—',
  },
  {
    id: 'amount',
    header: '금액',
    width: 110,
    align: 'right',
    numeric: true,
    sortable: true,
    text: (o) => won(orderTotal(o)),
    sortValue: orderTotal,
  },
  // 날짜 세 열은 정렬 기준이 ISO 문자열 그대로가 곧 날짜순입니다.
  {
    id: 'ordered',
    header: '발주일',
    width: 96,
    numeric: true,
    sortable: true,
    text: (o) => fmtDotShort(parseISO(o.ordered)),
    sortValue: (o) => o.ordered,
  },
  {
    id: 'due',
    header: '납기',
    width: 96,
    numeric: true,
    sortable: true,
    text: (o) => fmtDotShort(parseISO(o.due)),
    sortValue: (o) => o.due,
  },
  {
    id: 'expect',
    header: '예상 입고',
    width: 124,
    numeric: true,
    sortable: true,
    text: (o) => fmtDotShort(parseISO(o.expect)),
    sortValue: (o) => o.expect,
  },
  {
    id: 'status',
    // '출고의뢰서 작성완료' 배지가 그대로 들어가야 해서 다른 열보다 넓습니다.
    header: '상태',
    width: 160,
    sortable: true,
    text: (o) => o.status,
    sortValue: (o) => ORDER_STATUSES.indexOf(o.status),
  },
]

/** 지금 어느 열로 세워 두었는지. null 이면 원래 순서입니다. */
export type SortState = { id: string; dir: 'asc' | 'desc' } | null

const COLUMN_BY_ID = new Map(ORDER_COLUMNS.map((col) => [col.id, col]))

/** 한 열을 기준으로 세우는 비교 함수. 숫자는 크기로, 글자는 한국어 순서로 봅니다. */
export function compareBy(columnId: string) {
  const column = COLUMN_BY_ID.get(columnId)
  const of = (order: PurchaseOrder) =>
    column?.sortValue ? column.sortValue(order) : (column?.text(order) ?? '')

  return (a: PurchaseOrder, b: PurchaseOrder) => {
    const left = of(a)
    const right = of(b)
    if (typeof left === 'number' && typeof right === 'number') return left - right
    return String(left).localeCompare(String(right), 'ko')
  }
}
