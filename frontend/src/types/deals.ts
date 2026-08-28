import type { CustomerSourceCode } from './customers'
import type { OrderOutcomeCode } from './orders'
import type { ColumnTone } from './stage'

export type SalesDealStatus = '확정' | '진행중' | '취소'
export type SalesPipelineStatusCode = 'published' | 'archived'
export type SalesPipelineOutcomeCode = 'in_progress' | 'confirmed' | 'cancelled'
export type SalesPipelinePhaseCode = 'sales' | 'quote' | 'contract' | 'order' | 'closed'

export interface SalesPipelineResponse {
  id: string
  name: string
  description: string | null
  status_code: SalesPipelineStatusCode
  is_default: boolean
  published_at: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface SalesPipelineStageResponse {
  id: string
  sales_pipeline_id: string
  stage_code: string
  name: string
  tone: ColumnTone
  phase_code: SalesPipelinePhaseCode
  outcome_code: SalesPipelineOutcomeCode
  position: number
}

export interface SalesDealTypeResponse {
  id: string
  code: string
  name: string
  position: number
}

export type ProductCategoryCode = 'system' | 'probe' | 'consumable'

export interface ProductResponse {
  id: string
  name: string
  active: boolean
  category_code: ProductCategoryCode
  /** 원 단위 정수 */
  unit_price: number
  /** 유효기간(개월). 없으면 null */
  shelf_life_months: number | null
  memo: string | null
  /** 사진 주소는 GET /products/{id}/image 로 따로 받습니다. */
  has_image: boolean
}

export interface ProductCreateRequest {
  name: string
  category_code: ProductCategoryCode
  unit_price: number
  shelf_life_months: number | null
  memo: string | null
}

export interface ProductImageResponse {
  url: string
  expires_in: number
}

/**
 * 견적·계약 상태. 팀마다 고칠 수 있는 설정 표라 발주 상태와 모양이 같습니다.
 * 이름과 색은 서버가 주는 것을 그대로 씁니다. 화면에 한글을 다시 적지 않습니다.
 */
export interface DocumentStatusResponse {
  id: string
  code: string
  name: string
  tone: ColumnTone
  outcome_code: OrderOutcomeCode
  position: number
}

export interface SalesDealItemResponse {
  id: string
  product_id: string
  product_name: string
  quantity: number
  unit_price: number
  position: number
}

export interface SalesDealItemRequest {
  product_id: string
  quantity: number
  unit_price: number
}

export interface SalesDealParticipantResponse {
  customer_contact_id: string
  customer_contact_name: string
}

/** 견적·계약 국면에서 함께 저장하는 값. 만드는 요청과 고치는 요청이 같이 씁니다. */
export interface SalesDealDocumentFields {
  title?: string
  quote_no?: string | null
  quote_issued_on?: string | null
  quote_valid_until?: string | null
  quote_status_code?: string | null
  quote_amount?: number | null
  quote_delivery_terms?: string | null
  contract_payment_terms?: string | null
  contract_late_interest_terms?: string | null
  contract_no?: string | null
  contract_signed_on?: string | null
  contract_ends_on?: string | null
  contract_status_code?: string | null
  contract_amount?: number | null
  warranty_terms?: string | null
  expected_delivery_at?: string | null
  items?: SalesDealItemRequest[]
  participant_contact_ids?: string[]
}

export interface SalesDealCreateRequest extends SalesDealDocumentFields {
  customer_company_id: string
  customer_contact_id: string | null
  product_id: string
  sales_pipeline_id: string
  sales_pipeline_stage_id: string
  deal_type_code: string
  deal_amount: number
  opened_on: string
  memo: string | null
  source_code: CustomerSourceCode | null
}

export interface SalesDealPatchRequest extends SalesDealDocumentFields {
  customer_company_id: string
  customer_contact_id?: string | null
  product_id?: string
  deal_type_code?: string
  deal_amount: number
  opened_on: string
  memo: string | null
  source_code: CustomerSourceCode | null
}

export interface SalesDealMoveRequest {
  expected_sales_pipeline_stage_id: string
  sales_pipeline_stage_id: string
  stage_position: number
}

export interface SalesDealResponse {
  id: string
  deal_no: string
  customer_company_id: string
  customer_company_name: string
  customer_company_region_code: string | null
  customer_contact_id: string | null
  customer_contact_name: string | null
  owner_member_id: string
  owner_display_name: string
  product_id: string | null
  product_name: string | null
  sales_pipeline_id: string
  sales_pipeline_name: string
  sales_pipeline_status_code: SalesPipelineStatusCode
  sales_pipeline_is_default: boolean
  sales_pipeline_stage_id: string
  sales_pipeline_stage_code: string
  sales_pipeline_stage_name: string
  sales_pipeline_stage_tone: ColumnTone
  sales_pipeline_stage_phase_code: SalesPipelinePhaseCode
  sales_pipeline_stage_outcome_code: SalesPipelineOutcomeCode
  sales_pipeline_stage_position: number
  sales_deal_type_id: string
  deal_type_code: string
  deal_type_name: string
  title: string
  description: string | null
  deal_amount: number
  opened_on: string
  closed_on: string | null
  quote_no: string | null
  quote_issued_on: string | null
  quote_valid_until: string | null
  contract_no: string | null
  contract_signed_on: string | null
  contract_ends_on: string | null
  warranty_terms: string | null
  expected_delivery_at: string | null
  memo: string | null
  /** 예전 데이터에는 아래 목록 밖의 코드도 있어 문자열을 그대로 받습니다. */
  source_code: CustomerSourceCode | string | null
  quote_status_id: string | null
  quote_status_code: string | null
  quote_status_name: string | null
  quote_status_tone: ColumnTone | null
  contract_status_id: string | null
  contract_status_code: string | null
  contract_status_name: string | null
  contract_status_tone: ColumnTone | null
  quote_amount: number | null
  contract_amount: number | null
  quote_delivery_terms: string | null
  contract_payment_terms: string | null
  contract_late_interest_terms: string | null
  /**
   * 계약서의 계약자정보(갑)(을). 을은 팀, 갑은 딜의 고객사입니다. 딜이 이미 들고 있는
   * 것에서 유도하므로 계약이 따로 적어 두지 않습니다. 사업자번호는 하이픈 없는 10자리입니다.
   */
  team_company_name: string | null
  team_business_no: string | null
  customer_company_business_no: string | null
  items: SalesDealItemResponse[]
  participants: SalesDealParticipantResponse[]
  /** 이 딜에 걸린 발주 중 가장 최근 것의 상태. 발주가 없으면 셋 다 null 입니다. */
  order_status_code: string | null
  order_status_name: string | null
  order_status_tone: ColumnTone | null
  stage_position: number
  created_at: string
  updated_at: string
}
