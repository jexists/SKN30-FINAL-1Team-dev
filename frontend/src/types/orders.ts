export interface OrderLine {
  product: string
  qty: number
  price: number
}

export type OrderStatus =
  '승인대기' | '승인' | '출고의뢰서 작성완료' | '생산중' | '출고' | '입고완료' | '취소'

export interface PurchaseOrderSeed {
  no: string
  contract: string
  hospital: string
  supplier: string
  orderedOff: number
  dueOff: number
  expectOff: number
  status: OrderStatus
  memo: string
  items: OrderLine[]
}

/** 실제 날짜가 붙은 발주 */
export interface PurchaseOrder extends PurchaseOrderSeed {
  ordered: string
  due: string
  expect: string
}
