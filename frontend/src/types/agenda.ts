import type { ContractBriefingOutput } from './contractAgent'

/** 일정 종류. 배지 색이 여기에 묶여 있습니다. */
export type AgendaKind = 'visit' | 'demo' | 'edu' | 'call' | 'delivery' | 'booth'

export type ActivityCategoryCode =
  'visit' | 'demo' | 'education' | 'call' | 'delivery' | 'conference'

export type ActivityActionTagCode =
  | 'first_call'
  | 'meeting'
  | 'demo_requested'
  | 'demo_in_progress'
  | 'demo_completed'
  | 'quote_completed'
  | 'contract_completed'
  | 'product_training'
  | 'delivery_completed'
  | 'internal_meeting'
  | 'conference'

/** 고객을 만나서 하는 일. 영업이 어디까지 갔는지를 말합니다. */
export type ExternalStatus =
  | '첫 전화'
  | '미팅'
  | '데모 요청'
  | '데모 진행'
  | '데모 완료'
  | '견적완료'
  | '계약완료'
  | '제품교육'
  | '납품완료'

/** 고객을 만나지 않고 사내에서 소화하는 일정. 영업 단계와 무관합니다. */
export type InternalStatus = '내부회의' | '컨퍼런스'

/** 일정의 상태. 외부·내부 두 계열로 나뉘고 태그 색이 계열을 따릅니다. */
export type ScheduleStatus = ExternalStatus | InternalStatus

export interface AgendaHistory {
  when: string
  what: string
}

export interface AgendaSeed {
  id: string
  /** 담당 영업. 데모 프로필이 이 값으로 시드를 거릅니다. */
  owner: string
  /** 오늘로부터 며칠 */
  off: number
  time: string
  dur: string
  kind: AgendaKind
  hospital: string
  dept: string
  contact: string
  product: string
  /** 영업 단계에 걸리지 않는 일정은 비어 있습니다. */
  stage?: ScheduleStatus
  place: string
  title: string
  brief: string
  history: AgendaHistory[]
  tags: string[]
  done: boolean
  /** 업무보고를 썼는지. 일정을 끝냈다는 done 과는 별개입니다. */
  reported: boolean
}

/** 실제 날짜 키가 붙은 일정 */
export interface AgendaItem extends AgendaSeed {
  date: string
  customerContactId?: string | null
  customerContactName?: string
  /** 이 일정의 고객사. 회사에 걸린 영업 현황을 찾을 때 씁니다. */
  customerCompanyId?: string | null
  salesDealId?: string | null
  productId?: string | null
  ownerMemberId?: string
  startsAt?: string
  endsAt?: string | null
  allDay?: boolean
  /** AI 추천 일정을 승인해 만든 활동에서, 브리핑 큐잉이 실패했을 때만 채워짐 */
  briefingQueueWarning?: string | null
  /** AI 추천 일정을 승인했는데 그 시간에 이미 다른 일정이 있을 때만 채워짐 */
  scheduleConflictWarning?: string | null
}

/**
 * 캘린더가 다루는 일정. AgendaItem 보다 느슨해서 화면에서 새로 만든 일정도 담습니다.
 * AgendaItem 은 이 형태를 그대로 만족하므로 캘린더의 초기 데이터로 바로 씁니다.
 */
export interface CalendarEvent {
  id: string
  /** YYYY-MM-DD */
  date: string
  /** HH:MM */
  time: string
  /** '40분' 처럼 표시용 라벨입니다. 계산에 쓰지 않습니다. */
  dur: string
  kind: AgendaKind
  /** 화면에서 새로 만든 일정은 아직 상태가 없을 수 있습니다. */
  stage?: ScheduleStatus
  title: string
  hospital?: string
  dept?: string
  contact?: string
  place?: string
  brief?: string
  done: boolean
  customerContactId?: string | null
  customerContactName?: string
  salesDealId?: string | null
  productId?: string | null
  product?: string
  owner?: string
  startsAt?: string
  endsAt?: string | null
  allDay?: boolean
  /** AI 추천 일정을 승인할 때만 채운다 — schedule_management 실행 id. 있으면 서버가 등록
   * 커밋 직후 브리핑 실행을 자동으로 큐잉한다. */
  scheduleManagementRunId?: string | null
}

export interface ActivityRead {
  id: string
  owner_member_id: string
  owner_display_name: string
  customer_contact_id: string | null
  customer_contact_name: string | null
  customer_contact_department: string | null
  customer_contact_job_title: string | null
  customer_company_id: string | null
  customer_company_name: string | null
  sales_deal_id: string | null
  purchase_order_id: string | null
  product_id: string | null
  product_name: string | null
  category_code: ActivityCategoryCode
  title: string
  starts_at: string
  ends_at: string | null
  all_day: boolean
  /** 후속업무의 마감. 대개는 비어 있습니다. */
  due_at: string | null
  location: string | null
  action_tag: ActivityActionTagCode | null
  completed_at: string | null
  note: string | null
  created_at: string
  updated_at: string
  /** schedule_management_run_id로 브리핑을 큐잉하려다 실패했을 때만 채워짐 */
  briefing_queue_warning?: string | null
  /** 승인한 시간에 이미 다른 일정이 있을 때만 채워짐. 등록 자체는 성공한 상태다 */
  schedule_conflict_warning?: string | null
  /** 이 활동에 연결된 최신 브리핑 실행. 실행 기록 자체가 없으면(한 번도 요청 안 했으면) null */
  ai_briefing?: AiBriefing | null
}

export type AiBriefingStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface AiBriefing {
  run_id: string
  status: AiBriefingStatus
  content: ContractBriefingOutput | null
  error: string | null
  generated_at: string | null
}

/** 미팅에 관련된 자료실 문서 한 건. AI 브리핑과 무관하게 조회된다. */
export interface ActivityDocument {
  document_id: string
  document_no: string
  category_code: string
  title: string
  file_id: string
  file_name: string
  /** 자료요약 Agent 가 만든 요약. 아직 요약이 없는 파일이면 null 이다. */
  summary_markdown: string | null
  uploaded_at: string
}

/**
 * `GET /activities/{id}/documents` 의 응답. 브리핑 실행 기록이 아니라 연결 관계만 보므로
 * 미팅을 열 때마다 새로 조회하며, 브리핑을 만든 뒤 올라온 자료도 곧바로 보인다.
 *
 * `product` 는 고객사와 무관한 공용 자료(카탈로그·스펙)라 화면에서도 섞지 않는다.
 */
export interface ActivityDocuments {
  related: ActivityDocument[]
  product: ActivityDocument[]
}

export interface ActivityCreateRequest {
  customer_contact_id?: string | null
  sales_deal_id?: string | null
  product_id?: string | null
  category_code: ActivityCategoryCode
  title: string
  starts_at: string
  ends_at?: string | null
  all_day: boolean
  location?: string | null
  action_tag?: ActivityActionTagCode | null
  note?: string | null
  /** AI가 추천한 일정 후보를 승인해서 등록할 때만 채운다 */
  schedule_management_run_id?: string | null
}

export type ActivityPatchRequest = Partial<
  Omit<ActivityCreateRequest, 'schedule_management_run_id'>
>
