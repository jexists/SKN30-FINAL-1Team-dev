/** 일정 종류. 배지 색이 여기에 묶여 있습니다. */
export type AgendaKind = 'visit' | 'demo' | 'edu' | 'call' | 'delivery' | 'booth' | 'internal'

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
  stage: ScheduleStatus
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
}
