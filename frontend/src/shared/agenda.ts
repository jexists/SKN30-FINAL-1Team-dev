// 일정 도메인. 시드는 mocks/ 에서 받고 여기서는 상수·로직·파생만 둡니다.
import { agendaSeed } from '@/mocks'
import type {
  AgendaItem,
  AgendaKind,
  ExternalStatus,
  InternalStatus,
  ScheduleStatus,
} from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

export const KIND_LABEL: Record<AgendaKind, string> = {
  visit: '방문',
  demo: '데모',
  edu: '교육',
  call: '전화',
  delivery: '납품',
  booth: '학회',
  internal: '내부',
}

/** 고객 대상 활동 */
export const EXTERNAL_STATUSES: readonly ExternalStatus[] = [
  '첫 전화',
  '미팅',
  '데모 요청',
  '데모 진행',
  '데모 완료',
  '견적완료',
  '계약완료',
  '제품교육',
  '납품완료',
]

/** 사내 활동 */
export const INTERNAL_STATUSES: readonly InternalStatus[] = [
  '내부회의',
  '주간점검',
  '월간점검',
  '분기점검',
  '컨퍼런스',
  'OJT',
]

/** 상태가 어느 계열인지. 태그 색이 여기서 갈립니다. */
export function statusScope(status: ScheduleStatus): '내부' | '외부' {
  return (INTERNAL_STATUSES as readonly ScheduleStatus[]).includes(status) ? '내부' : '외부'
}

/** 날짜 키 → 그날의 일정(시간순). offset 을 실제 날짜로 편 결과입니다. */
export const agendaByDate: Record<string, AgendaItem[]> = {}

for (const seed of agendaSeed) {
  const date = iso(addDays(TODAY, seed.off))
  ;(agendaByDate[date] ??= []).push({ ...seed, date })
}

for (const list of Object.values(agendaByDate)) {
  list.sort((a, b) => a.time.localeCompare(b.time))
}

export function agendaFor(dateISO: string): AgendaItem[] {
  return agendaByDate[dateISO] ?? []
}

/** 일정 하나를 id 로 찾습니다. 미팅보고서 작성 화면이 ?agenda= 로 받은 값을 폅니다. */
export function agendaById(id: string): AgendaItem | undefined {
  for (const list of Object.values(agendaByDate)) {
    const found = list.find((item) => item.id === id)
    if (found) return found
  }
  return undefined
}
