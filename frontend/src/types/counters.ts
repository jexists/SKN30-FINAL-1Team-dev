// 대시보드 요약 밴드가 세는 것들. 후속·CS·갱신은 각자 화면이 없어 여기 모여 있습니다.

export interface FollowUp {
  /** 담당 영업 */
  owner: string
  task: string
  org: string
  who: string
  note: string
  dueOff: number
}

export type CsState = '처리중' | '처리완료'

export interface CsRequest {
  id: string
  /** 담당 영업 */
  owner: string
  issue: string
  org: string
  /** 접수한 사람. 화면에서 등록한 건은 비어 있습니다. */
  who: string
  /** 문제가 난 제품. 화면에서 등록한 건은 비어 있습니다. */
  product: string
  state: CsState
  urgent: boolean
  agoOff: number
  ago: string
  note: string
}

/** 접수 → 원인파악 → 처리중 → 처리완료 */
export type SupportStatusCode = 'received' | 'diagnosing' | 'in_progress' | 'completed'

export interface SupportResponseResponse {
  id: string
  request_id: string
  responder_member_id: string
  responder_display_name: string
  body: string
  responded_at: string
}

export interface SupportRequestResponse {
  id: string
  customer_company_id: string
  customer_company_name: string
  sales_deal_id: string
  deal_no: string
  contract_no: string | null
  deal_title: string
  /** 관련 제품과 워런티는 계약건이 들고 있는 값입니다. */
  product_name: string | null
  warranty_terms: string | null
  assignee_member_id: string
  assignee_display_name: string
  title: string
  body: string
  is_urgent: boolean
  status_code: SupportStatusCode
  occurred_at: string
  registered_at: string
  responses: SupportResponseResponse[]
}

export interface SupportRequestCreateRequest {
  customer_company_id: string
  sales_deal_id: string
  title: string
  body: string
  is_urgent: boolean
  status_code: SupportStatusCode
  occurred_at: string
}

export interface SupportTransitionRequest {
  expected_status_code: SupportStatusCode
  status_code: SupportStatusCode
}

export interface Renewal {
  /** 담당 영업 */
  owner: string
  org: string
  who: string
  contract: string
  kind: string
  amount: number
  expireOff: number
  note: string
}
