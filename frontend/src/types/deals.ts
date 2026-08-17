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

export interface ProductResponse {
  id: string
  name: string
  active: boolean
}

export interface SalesDealCreateRequest {
  customer_company_id: string
  customer_contact_id: string | null
  product_id: string
  sales_pipeline_id: string
  sales_pipeline_stage_id: string
  deal_type_code: string
  deal_amount: number
  opened_on: string
  memo: string | null
}

export interface SalesDealPatchRequest {
  customer_company_id: string
  customer_contact_id?: string | null
  product_id?: string
  deal_type_code?: string
  deal_amount: number
  opened_on: string
  memo: string | null
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
  stage_position: number
  created_at: string
  updated_at: string
}
