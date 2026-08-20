import type { PurchaseOrder } from '@/types'

export const orders: PurchaseOrder[] = []

export function isLate(order: PurchaseOrder): boolean {
  return order.expectOff > order.dueOff
}

export function dday(order: PurchaseOrder): number {
  return order.expectOff
}

export function orderTotal(order: PurchaseOrder): number {
  return order.items.reduce((sum, item) => sum + item.qty * item.price, 0)
}

export function orderItemLabel(order: PurchaseOrder): string {
  return order.items.map((item) => `${item.product} ${item.qty}개`).join(', ')
}

export const activeOrders = (): PurchaseOrder[] => []

export function findOrderFor(_hospital: string, _product: string): PurchaseOrder | undefined {
  return undefined
}
