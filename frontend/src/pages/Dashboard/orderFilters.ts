// 발주 진행 현황의 다섯 조건입니다. 타일과 드로어 필터 칩이 같은 표를 봐야
// 숫자가 어긋나지 않아서 컴포넌트가 아니라 여기에 둡니다.
//
// 다섯 조건은 서로 겹칩니다(한 발주가 진행중이면서 납기 지연일 수 있습니다).
// 그래서 단계 표시가 아니라 나란한 타일입니다 — 연결선은 순서를 암시합니다.
import { dday, isLate } from '@/shared/orders'
import type { PurchaseOrder } from '@/types'
import { addDays, fmtDay, TODAY } from '@/utils/date'

export type OrderFilterKey = 'pending' | 'request' | 'inflight' | 'thisweek' | 'late'

export interface OrderFilter {
  key: OrderFilterKey
  label: string
  note: () => string
  /** 납기를 넘긴 건처럼 그냥 두면 안 되는 조건 */
  alert?: boolean
  test: (o: PurchaseOrder) => boolean
}

export const ORDER_FILTERS: OrderFilter[] = [
  {
    key: 'pending',
    label: '승인 대기',
    note: () => '팀장 승인 필요',
    test: (o) => o.status === '승인대기',
  },
  {
    key: 'request',
    label: '출고의뢰서 처리',
    note: () => '출고 준비 단계',
    test: (o) => o.status === '출고의뢰서 작성완료',
  },
  {
    key: 'inflight',
    label: '생산·출고 진행중',
    note: () => '승인부터 출고까지',
    test: (o) => ['승인', '출고의뢰서 작성완료', '생산중', '출고'].includes(o.status),
  },
  {
    key: 'thisweek',
    label: '이번 주 입고 예정',
    note: () => `${fmtDay(TODAY).slice(0, -4)} – ${fmtDay(addDays(TODAY, 7)).slice(0, -4)}`,
    test: (o) => o.status !== '입고완료' && dday(o) >= 0 && dday(o) <= 7,
  },
  {
    key: 'late',
    label: '납기 지연',
    note: () => '예상 입고일이 납기 초과',
    alert: true,
    test: isLate,
  },
]

export function orderFilter(key: OrderFilterKey): OrderFilter {
  // 키가 이 표에서만 나오므로 못 찾는 경우는 없습니다.
  return ORDER_FILTERS.find((f) => f.key === key) ?? ORDER_FILTERS[0]
}
