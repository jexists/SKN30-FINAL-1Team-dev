/** 계약 진행 상태. 매출 실적으로 잡히는 것은 '확정' 뿐입니다. */
export type ContractStatus = '확정' | '진행중' | '취소'

export type ContractKind = '신규 도입' | '증설' | '갱신' | '유지보수' | '소모품 공급'

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
}
