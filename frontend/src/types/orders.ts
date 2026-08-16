export interface OrderLine {
  product: string
  qty: number
  price: number
}

/**
 * 발주 상태. 결재·생산·물류 흐름을 다섯 단계로 두고, 흐름 밖의 취소를 하나 더 둡니다.
 * 순서가 곧 진행 순서라 탭·정렬·스텝바가 이 배열 순서를 그대로 씁니다.
 */
export type OrderStatus =
  '발주 접수' | '출고 의뢰서 완료' | '생산중' | '입고 완료' | '납품 완료' | '취소'

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
