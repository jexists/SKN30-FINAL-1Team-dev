import type { TabbedPageResponse } from './customers'
import type { ColumnTone } from './stage'

export interface OrderLine {
  product: string
  qty: number
  price: number
}

/** 사람이 보는 발주 상태는 팀 설정에서 늘어날 수 있습니다. */
export type OrderStageCode = string
export type OrderStatus = string
export type OrderOutcomeCode = 'in_progress' | 'completed' | 'cancelled'

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

export interface ApiPurchaseOrder extends PurchaseOrder {
  id: string
  salesDealId: string
  salesDeal: string
  customerCompanyId: string
  ownerMemberId: string
  owner: string
  stageCode: string
  stageTone: ColumnTone
  stageOutcomeCode: OrderOutcomeCode
  stagePosition: number
  requestDepartment: string
  cooperationDepartment: string
  createdByMemberId: string
  createdBy: string
  expectedCustomerCompanyId: string
  expectedCustomerCompany: string
  items: ApiOrderLine[]
  createdAt: string
  updatedAt: string
}

export interface PurchaseOrderStatusResponse {
  id: string
  code: string
  name: string
  tone: ColumnTone
  outcome_code: OrderOutcomeCode
  position: number
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
  sales_deal_id: string
  deal_no: string
  customer_company_id: string
  customer_company_name: string
  owner_member_id: string
  owner_display_name: string
  supplier_name: string
  purchase_order_status_id: string
  stage_code: string
  stage_name: string
  stage_tone: ColumnTone
  stage_outcome_code: OrderOutcomeCode
  stage_position: number
  ordered_on: string
  due_on: string
  expected_receipt_on: string
  request_department: string
  cooperation_department: string
  created_by_member_id: string
  created_by_display_name: string
  expected_customer_company_id: string
  expected_customer_company_name: string
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
  sales_deal_id: string
  supplier_name: string
  stage_code: string
  ordered_on: string
  due_on: string
  expected_receipt_on: string
  request_department: string
  cooperation_department: string
  expected_customer_company_id: string
  memo: string | null
  items: OrderItemRequest[]
}

export type OrderPatchRequest = Omit<OrderCreateRequest, 'stage_code'>

export interface OrderMoveRequest {
  expected_stage_code: string
  stage_code: string
}

/**
 * 발주 목록 한 쪽. `counts` 는 상태 탭 옆 건수, `suppliers` 는 공급처 고르는 칸에 세울
 * 이름입니다. 둘 다 자기 조건만 빼고 집계한 값이라 쪽이 바뀌어도 그대로입니다.
 */
export interface OrderPageResponse extends TabbedPageResponse<OrderResponse> {
  suppliers: string[]
}
