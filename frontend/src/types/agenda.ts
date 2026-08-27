import type { ContractBriefingOutput } from './contractAgent'

/** 일정 종류. 배지 색이 여기에 묶여 있습니다. */
export type AgendaKind = 'visit' | 'demo' | 'edu' | 'call' | 'delivery' | 'booth' | 'internal'

export type ActivityTypeCode = 'meeting' | 'task'

export type ActivityCategoryCode =
  'visit' | 'demo' | 'education' | 'call' | 'delivery' | 'conference' | 'internal'

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
  | 'weekly_review'
  | 'monthly_review'
  | 'quarterly_review'
  | 'conference'
  | 'ojt'

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

/** 사내에서 하는 일. 영업 단계와 무관하게 반복됩니다. */
export type InternalStatus = '내부회의' | '주간점검' | '월간점검' | '분기점검' | '컨퍼런스' | 'OJT'

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
  /** 사내 업무처럼 영업 단계에 걸리지 않는 일정은 비어 있습니다. */
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
  activityType?: ActivityTypeCode
  customerContactId?: string | null
  customerContactName?: string
  salesDealId?: string | null
  productId?: string | null
  ownerMemberId?: string
  startsAt?: string
  endsAt?: string | null
  allDay?: boolean
  /** AI 추천 일정을 승인해 만든 활동에서, 브리핑 큐잉이 실패했을 때만 채워짐 */
  briefingQueueWarning?: string | null
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
  activityType?: ActivityTypeCode
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
  activity_type: ActivityTypeCode
  category_code: ActivityCategoryCode
  title: string
  starts_at: string
  ends_at: string | null
  all_day: boolean
  /** 후속업무의 마감. 미팅에는 대개 비어 있습니다. */
  due_at: string | null
  location: string | null
  action_tag: ActivityActionTagCode | null
  completed_at: string | null
  note: string | null
  created_at: string
  updated_at: string
  /** schedule_management_run_id로 브리핑을 큐잉하려다 실패했을 때만 채워짐 */
  briefing_queue_warning?: string | null
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

export interface ActivityCreateRequest {
  customer_contact_id?: string | null
  sales_deal_id?: string | null
  product_id?: string | null
  activity_type: ActivityTypeCode
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
