/** 영업 진행 단계. 목록의 상태 배지가 여기에 묶여 있습니다. */
export type CustomerStatus = '신규' | '제안' | '협의' | '계약' | '보류'

/** 고객을 처음 만난 경로 */
export type CustomerSource = '소개' | '박람회' | '홈페이지' | '콜드콜' | '기존 거래'

export interface CustomerSeed {
  id: string
  name: string
  /** 소속 고객사·기관 */
  org: string
  dept: string
  /** 직함 */
  title: string
  email: string
  phone: string
  /** 담당 영업 */
  owner: string
  source: CustomerSource
  status: CustomerStatus
  /** 최근 접촉. 과거이므로 음수입니다. */
  lastOff: number
  /** 다음 일정. null 이면 아직 잡지 않았다는 뜻입니다. */
  nextOff: number | null
  createdOff: number
  memo: string
}

/** 실제 날짜와 지연 여부가 붙은 고객 */
export interface Customer extends CustomerSeed {
  last: string
  next: string | null
  created: string
  /** 다음 일정이 없거나 이미 지났으면 후속이 늦은 것입니다. */
  overdue: boolean
}
