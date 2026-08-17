/** 영업 진행 단계. 목록의 상태 배지가 여기에 묶여 있습니다. */
export type CustomerStatus = '신규' | '제안' | '협의' | '계약' | '보류' | '미지정'

/** 고객을 처음 만난 경로 */
export type CustomerSource = '소개' | '박람회' | '홈페이지' | '콜드콜' | '기존 거래' | '미지정'

export type CustomerStatusCode = 'new' | 'proposal' | 'negotiation' | 'contracted' | 'on_hold'

export type CustomerSourceCode =
  'referral' | 'exhibition' | 'website' | 'cold_call' | 'existing_customer'

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

/** 화면에 표시하는 고객. 목업과 API 응답이 같은 표시 모델을 쓸 수 있게 둡니다. */
export interface Customer {
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
  memo: string
  /** 최근 접촉. 활동 API가 없는 고객은 null 입니다. */
  last: string | null
  next: string | null
  created: string
  /** 활동 데이터에서 계산한 후속 지연 여부. API 기본 상세에서는 false 입니다. */
  overdue: boolean
  /** API 응답에만 있는 식별자와 지역 코드 */
  companyId?: string
  ownerMemberId?: string
  regionCode?: string | null
}

export interface CustomerContactResponse {
  id: string
  company_id: string
  owner_member_id: string
  name: string
  department: string | null
  job_title: string | null
  email: string | null
  phone: string
  status_code: CustomerStatusCode | null
  source_code: CustomerSourceCode | null
  memo: string | null
  registered_at: string
  company_name: string
  company_region_code: string | null
  owner_display_name: string
}

export interface CustomerCompanyResponse {
  id: string
  team_id: string
  name: string
  region_code: string | null
  created_at: string
}

export interface CustomerContactCreateRequest {
  company_id: string
  name: string
  department: string | null
  job_title: string | null
  email: string | null
  phone: string
  status_code: CustomerStatusCode | null
  source_code: CustomerSourceCode | null
  memo: string | null
}

export interface PageResponse<T> {
  items: T[]
  skip: number
  limit: number
  total: number
  has_more: boolean
  next_skip: number | null
}
