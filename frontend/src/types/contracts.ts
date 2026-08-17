import type { ColumnTone } from './stage'

/** 계약 진행 상태. 매출 실적으로 잡히는 것은 '확정' 뿐입니다. */
export type ContractStatus = '확정' | '진행중' | '취소'

export type PipelineOutcomeCode = 'in_progress' | 'confirmed' | 'cancelled'

export type ContractKind = '신규 도입' | '증설' | '갱신' | '유지보수' | '소모품 공급'

/** API/DB에 저장하는 계약 유형 코드. 화면에서는 ContractKind의 한국어 라벨을 씁니다. */
export type ContractKindCode =
  'new_installation' | 'expansion' | 'renewal' | 'maintenance' | 'consumables_supply'

export interface ContractSeed {
  no: string
  /** 고객사. customers.ts 의 org 와 같은 표기를 씁니다. */
  org: string
  product: string
  amount: number
  kind: ContractKind
  status: ContractStatus
  /**
   * 계약일. 오늘로부터 며칠이며 과거이므로 음수입니다.
   * 아직 체결하지 않은 '진행중' 건은 협의를 시작한 날입니다.
   */
  signedOff: number
  /** 담당 영업 */
  owner: string
}

/** 실제 날짜와 지역이 붙은 계약 */
export interface Contract extends ContractSeed {
  /** 계약일 YYYY-MM-DD */
  date: string
  /** 고객사가 있는 시. regions.ts 에서 파생합니다. */
  region: string
  /** 화면에서 적어 넣은 메모. 시드에는 없습니다. */
  memo?: string
}

/** 계약 하나가 놓인 단계. 영업현황·계약현황이 저마다 다른 단계 집합을 씁니다. */
export interface StagedContract extends Contract {
  stageId: string
}

/** 계약 입력 폼이 내놓는 값. 계약번호·단계는 폼 밖에서 정합니다. */
export interface ContractDraft {
  org: string
  product: string
  amount: number
  kind: ContractKind
  owner: string
  /** YYYY-MM-DD */
  date: string
  memo: string
}

/** GET /api/pipeline-stages 응답. 순서는 position 오름차순입니다. */
export interface PipelineStageResponse {
  id: string
  name: string
  tone: ColumnTone
  outcome_code: PipelineOutcomeCode
  position: number
}

/** GET /api/products 응답. */
export interface ProductResponse {
  id: string
  name: string
  active: boolean
}

export interface ContractCreateRequest {
  customer_company_id: string
  contact_id: null
  product_id: string
  stage_id: string
  contract_type: ContractKindCode
  amount: number
  contract_date: string
  memo: string | null
}

export interface ContractPatchRequest {
  customer_company_id: string
  contact_id?: null
  product_id: string
  contract_type: ContractKindCode
  amount: number
  contract_date: string
  memo: string | null
}

export interface ContractMoveRequest {
  expected_stage_id: string
  stage_id: string
  position: number
}

/** GET /api/contracts 및 상세 조회 응답. 내부 UUID와 표시값을 함께 보존합니다. */
export interface ContractResponse {
  id: string
  contract_no: string
  customer_company_id: string
  customer_company_name: string
  customer_company_region_code: string | null
  contact_id: string | null
  contact_name: string | null
  owner_member_id: string
  owner_display_name: string
  product_id: string | null
  product_name: string | null
  stage_id: string
  stage_name: string
  stage_tone: ColumnTone
  stage_outcome_code: PipelineOutcomeCode
  stage_position: number
  title: string
  description: string | null
  contract_type: ContractKindCode
  amount: number
  contract_date: string
  ends_on: string | null
  warranty_terms: string | null
  expected_delivery_at: string | null
  memo: string | null
  position: number
  created_at: string
  updated_at: string
}
