// 발주 도메인. 시드는 mocks/ 에서 받고 여기서는 상수·로직·파생만 둡니다.
import { purchaseOrderSeed } from '@/mocks'
import type { PurchaseOrder } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

export const orders: PurchaseOrder[] = purchaseOrderSeed.map((o) => ({
  ...o,
  ordered: iso(addDays(TODAY, o.orderedOff)),
  due: iso(addDays(TODAY, o.dueOff)),
  expect: iso(addDays(TODAY, o.expectOff)),
}))

/** 예상 입고일이 납기를 넘긴 발주 */
export function isLate(o: PurchaseOrder): boolean {
  return o.expectOff > o.dueOff
}

/** 예상 입고까지 남은 일수. offset 이 이미 오늘 기준이라 그대로 씁니다. */
export function dday(o: PurchaseOrder): number {
  return o.expectOff
}

export function orderTotal(o: PurchaseOrder): number {
  return o.items.reduce((sum, it) => sum + it.qty * it.price, 0)
}

export function orderItemLabel(o: PurchaseOrder): string {
  return o.items.map((it) => `${it.product} ${it.qty}개`).join(', ')
}

export const activeOrders = (): PurchaseOrder[] => orders.filter((o) => o.status !== '취소')

/** 일정에 걸린 발주. 같은 고객사에 같은 제품을 넣은 건이면 그 일정의 발주로 봅니다. */
export function findOrderFor(hospital: string, product: string): PurchaseOrder | undefined {
  return orders.find((o) => o.hospital === hospital && o.items.some((it) => it.product === product))
}
