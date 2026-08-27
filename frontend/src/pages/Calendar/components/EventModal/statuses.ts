// 일정 등록 모달이 고르게 하는 상태 목록입니다.
//
// shared/agenda 의 EXTERNAL_STATUSES·INTERNAL_STATUSES 는 서버 action_tag 와
// 일대일로 묶여 있어 화면 어휘를 바꾸면 저장이 깨집니다. 그래서 화면에 보일
// 목록은 여기서 따로 갖고, 저장할 때만 기존 값으로 옮겨 적습니다.
import type { AgendaKind, ScheduleStatus } from '@/types'

export interface ScheduleStatusOption {
  /** 화면에 보이는 이름 */
  label: string
  /** 저장할 때 쓸 기존 상태. 대응하는 값이 없으면 태그 없이 저장합니다. */
  stage?: ScheduleStatus
  /** 상태를 고르면 종류도 따라 정해집니다(배지 색과 category_code 가 여기서 나옵니다). */
  kind: AgendaKind
}

/**
 * 일정 탭의 상태. 첫 항목이 기본값입니다.
 *
 * '영업미팅'→'미팅', '제품 시연 평가'→'데모 진행' 은 가장 가까운 기존 값으로
 * 옮겨 적은 것이고, '휴가' 는 대응하는 태그가 없어 비워 둡니다. 서버에 태그가
 * 생기면 이 표만 고치면 됩니다.
 *
 * 서버 태그는 하나도 빠뜨리지 않습니다. 목록에 없는 태그가 붙은 일정을 수정으로
 * 열면 scheduleStatusLabel 이 기본값으로 되돌려, 그대로 저장할 때 원래 태그가
 * '미팅' 으로 덮어써지기 때문입니다.
 */
export const SCHEDULE_STATUSES: readonly ScheduleStatusOption[] = [
  { label: '영업미팅', stage: '미팅', kind: 'visit' },
  { label: '첫 전화', stage: '첫 전화', kind: 'call' },
  { label: '데모 요청', stage: '데모 요청', kind: 'demo' },
  { label: '제품 시연 평가', stage: '데모 진행', kind: 'demo' },
  { label: '데모 완료', stage: '데모 완료', kind: 'demo' },
  { label: '견적완료', stage: '견적완료', kind: 'visit' },
  { label: '계약완료', stage: '계약완료', kind: 'visit' },
  { label: 'OJT', stage: 'OJT', kind: 'internal' },
  { label: '제품교육', stage: '제품교육', kind: 'edu' },
  { label: '납품완료', stage: '납품완료', kind: 'delivery' },
  { label: '내부회의', stage: '내부회의', kind: 'internal' },
  { label: '주간점검', stage: '주간점검', kind: 'internal' },
  { label: '월간점검', stage: '월간점검', kind: 'internal' },
  { label: '분기점검', stage: '분기점검', kind: 'internal' },
  { label: '컨퍼런스', stage: '컨퍼런스', kind: 'booth' },
  { label: '휴가', kind: 'internal' },
]

export const DEFAULT_SCHEDULE_STATUS = SCHEDULE_STATUSES[0].label

/** 저장된 일정을 다시 열 때 화면 이름으로 되돌립니다. */
export function scheduleStatusLabel(stage?: ScheduleStatus): string {
  if (!stage) return DEFAULT_SCHEDULE_STATUS
  return SCHEDULE_STATUSES.find((s) => s.stage === stage)?.label ?? DEFAULT_SCHEDULE_STATUS
}

export type TaskGroup = '견적' | '계약' | '발주'

/**
 * 업무 탭의 상태. 견적·계약·발주 세 갈래를 고르면 그 안의 단계가 열립니다.
 * 서버에 대응하는 값이 아직 없어 화면에서만 씁니다.
 */
export const TASK_GROUPS: readonly { group: TaskGroup; items: readonly string[] }[] = [
  { group: '견적', items: ['견적작성', '견적검토', '고객발송', '조건협의', '견적완료'] },
  { group: '계약', items: ['초안작성', '계약검토', '고객협의', '고객서명', '계약완료'] },
  {
    group: '발주',
    items: ['발주 접수', '출고 의뢰서 완료', '생산중', '입고 완료', '납품 완료', '발주취소'],
  },
]

/**
 * 등록하자마자 문서를 쓰러 가게 되는 단계들. 각 갈래의 첫 단계입니다.
 * 값은 이동을 물어볼 때 쓸 문서 이름입니다.
 */
export const DOCUMENT_BY_TASK_STATUS: Record<string, '견적서' | '계약서' | '발주'> = {
  견적작성: '견적서',
  초안작성: '계약서',
  '발주 접수': '발주',
}
