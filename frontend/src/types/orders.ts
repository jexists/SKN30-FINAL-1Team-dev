export interface OrderLine {
  product: string
  qty: number
  price: number
}

export type OrderStageCode =
  | 'order_received'
  | 'dispatch_request_completed'
  | 'in_production'
  | 'stock_received'
  | 'delivered'
  | 'cancelled'

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

export interface ApiOrderLine extends OrderLine {
  id: string
  productId: string
  position: number
}

/** API 응답을 기존 발주 화면이 쓰는 표시 형태로 바꾼 값입니다. */
export interface ApiPurchaseOrder extends PurchaseOrder {
  id: string
  contractId: string | null
  customerCompanyId: string
  ownerMemberId: string
  owner: string
  items: ApiOrderLine[]
  createdAt: string
  updatedAt: string
}

export interface OrderItemResponse {
  id: string
  product_id: string
  product_name: string
  quantity: number
  unit_price: number
  position: number
}

export interface OrderResponse {
  id: string
  order_no: string
  contract_id: string | null
  contract_no: string | null
  customer_company_id: string
  customer_company_name: string
  owner_member_id: string
  owner_display_name: string
  supplier_name: string
  stage_code: OrderStageCode
  ordered_on: string
  due_on: string
  expected_receipt_on: string
  memo: string | null
  items: OrderItemResponse[]
  created_at: string
  updated_at: string
}

export interface OrderItemRequest {
  product_id: string
  quantity: number
  unit_price: number
}

export interface OrderCreateRequest {
  contract_id: string | null
  customer_company_id: string
  supplier_name: string
  stage_code: OrderStageCode
  ordered_on: string
  due_on: string
  expected_receipt_on: string
  memo: string | null
  items: OrderItemRequest[]
}

export type OrderPatchRequest = Omit<OrderCreateRequest, 'stage_code'>

export interface OrderMoveRequest {
  expected_stage_code: OrderStageCode
  stage_code: OrderStageCode
}
