/** 영업 진행 단계. 목록의 상태 배지가 여기에 묶여 있습니다. */
export type CustomerStatus = '신규' | '제안' | '협의' | '계약' | '보류' | '미지정'

/** 고객을 처음 만난 경로 */
export type CustomerSource = '소개' | '박람회' | '홈페이지' | '콜드콜' | '기존 거래' | '미지정'

export type CustomerStatusCode = 'new' | 'proposal' | 'negotiation' | 'contracted' | 'on_hold'

export type CustomerSourceCode =
  'referral' | 'exhibition' | 'website' | 'cold_call' | 'existing_customer'

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
  /** 방문 여부. 등록 직후에는 아직 만나기 전이므로 false 입니다. */
  visited: boolean
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
  /** 담당자 전체. 첫 번째가 owner 와 같은 대표 담당자입니다. */
  owners?: CustomerOwner[]
}

/** 목록에 이름을 보여줄 담당자 한 명 */
export interface CustomerOwner {
  id: string
  name: string
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
  visited: boolean
  registered_at: string
  company_name: string
  company_region_code: string | null
  /** 대표 담당자. assignees 의 첫 번째와 같습니다. */
  owner_display_name: string
  created_by_member_id: string
  created_by_display_name: string
  assignees: ContactAssigneeResponse[]
}

export interface ContactAssigneeResponse {
  id: string
  display_name: string
}

export interface CustomerCompanyResponse {
  id: string
  team_id: string
  name: string
  region_code: string | null
  /** 하이픈 없는 10자리. 화면에 보일 하이픈은 프론트가 붙입니다. */
  business_no: string | null
  created_at: string
}

export interface CustomerCompanyCreateRequest {
  name: string
  region_code: string | null
  business_no: string | null
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
  visited: boolean
  /** 팀장만 보낼 수 있습니다. 비우면 등록한 사람이 담당자가 됩니다. */
  assignee_member_ids?: string[]
}

export interface PageResponse<T> {
  items: T[]
  skip: number
  limit: number
  total: number
  has_more: boolean
  next_skip: number | null
}
