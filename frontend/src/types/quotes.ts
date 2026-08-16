import type { ContractKind } from './contracts'

/** 견적 진행 단계. 견적서 한 장이 작성에서 완료까지 지나는 다섯 칸입니다. */
export type QuoteStageId = 'draft' | 'review' | 'sent' | 'negotiate' | 'done'

export interface QuoteSeed {
  no: string
  /** 고객사. customers.ts 의 org 와 같은 표기를 씁니다. */
  org: string
  product: string
  amount: number
  kind: ContractKind
  stageId: QuoteStageId
  /** 견적일. 오늘로부터 며칠이며 과거이므로 음수입니다. */
  issuedOff: number
  /** 견적일로부터 며칠까지 유효한지 */
  validDays: number
  /** 담당 영업 */
  owner: string
}

/** 실제 날짜가 붙은 견적 */
export interface Quote extends QuoteSeed {
  /** 견적일 YYYY-MM-DD */
  date: string
  /** 유효기한 YYYY-MM-DD */
  validUntil: string
}
