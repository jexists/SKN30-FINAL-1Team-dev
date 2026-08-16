// 발주 화면의 어휘입니다. 상태가 무엇이고 무슨 색으로 보이는지, 폼과 필터가
// 어떤 선택지를 내놓는지를 여기서 정합니다.
//
// 영업현황의 board.ts 와 달리 상태 집합은 데이터가 아니라 타입입니다. 발주 상태는
// 결재·생산·물류 흐름이라 화면에서 늘리고 줄일 수 있는 것이 아닙니다.
// (파일 이름이 orders.ts 가 아닌 이유: Orders.tsx 와 대소문자만 달라 충돌합니다.)
import { contracts } from '@/shared/contracts'
import { orders as seed } from '@/shared/orders'
import type { ColumnTone, OrderStatus, PurchaseOrder, Stage } from '@/types'

/** 상태 선택지. 타입에 적힌 순서가 곧 진행 순서입니다. 탭·정렬이 이 순서를 씁니다. */
export const ORDER_STATUSES: OrderStatus[] = [
  '발주 접수',
  '출고 의뢰서 완료',
  '생산중',
  '입고 완료',
  '납품 완료',
  '취소',
]

export const TONE_OF: Record<OrderStatus, ColumnTone> = {
  '발주 접수': 'gray',
  '출고 의뢰서 완료': 'purple',
  생산중: 'orange',
  '입고 완료': 'blue',
  '납품 완료': 'green',
  취소: 'red',
}

/** 단계 탭이 쓰는 어휘. 상태 하나가 곧 단계 하나입니다. */
export const ORDER_STAGES: Stage[] = ORDER_STATUSES.map((status) => ({
  id: status,
  name: status,
  tone: TONE_OF[status],
}))

/** 진행 스텝바가 보여 줄 다섯 칸 */
export const ORDER_STEPS: OrderStatus[] = ORDER_STATUSES.filter((status) => status !== '취소')

/** 상태가 놓이는 칸. 취소는 흐름 밖이라 -1 입니다. */
export const stepOf = (status: OrderStatus): number => ORDER_STEPS.indexOf(status)

/** 필터와 폼의 선택지. 데이터에서 뽑아야 목록과 어긋나지 않습니다. */
export const SUPPLIERS: string[] = [...new Set(seed.map((o) => o.supplier))].sort()
export const HOSPITALS: string[] = [...new Set(seed.map((o) => o.hospital))].sort()
export const PRODUCTS: string[] = [
  ...new Set(seed.flatMap((o) => o.items.map((it) => it.product))),
].sort()

const OWNER_BY_CONTRACT = new Map(contracts.map((contract) => [contract.no, contract.owner]))

/**
 * 발주의 담당 영업. 발주 자체에는 담당자가 없어 연결된 계약에서 가져옵니다.
 * 계약 없는 선발주는 누구 것인지 알 수 없어 undefined 입니다.
 */
export function ownerOfOrder(order: PurchaseOrder): string | undefined {
  return order.contract ? OWNER_BY_CONTRACT.get(order.contract) : undefined
}

/** 시드를 목록의 초기 상태로. 발주일 최신순으로 세워 둡니다. */
export function initialOrders(): PurchaseOrder[] {
  return [...seed].sort((a, b) => b.ordered.localeCompare(a.ordered))
}

/** 다음 발주번호. 올해 번호 중 가장 큰 것에 1 을 더합니다. */
export function nextOrderNo(list: PurchaseOrder[]): string {
  const year = new Date().getFullYear()
  const prefix = `FM-PO-${year}-`
  const last = list.reduce((max, o) => {
    if (!o.no.startsWith(prefix)) return max
    const n = Number(o.no.slice(prefix.length))
    return Number.isNaN(n) ? max : Math.max(max, n)
  }, 0)
  return `${prefix}${String(last + 1).padStart(4, '0')}`
}
