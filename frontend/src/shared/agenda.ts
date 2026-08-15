// 일정 도메인. 시드는 mocks/ 에서 받고 여기서는 상수·로직·파생만 둡니다.
//
// 일정은 대시보드에서 등록하고 캘린더에서 옮기고 지웁니다. 두 화면이 각자
// 복사본을 들면 한쪽에서 만든 일정이 다른 쪽에 없습니다. 그래서 목록을 이
// 모듈 하나에 두고, 화면은 아래 훅으로 구독만 합니다.
//
// 백엔드가 붙는 지점은 addAgenda / updateAgenda / removeAgenda 셋입니다.
// 저장은 메모리에만 합니다. 새로고침하면 목업 초기 상태로 돌아갑니다.
import { useCallback, useSyncExternalStore } from 'react'

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

// ── 스토어 ────────────────────────────────────────────────────────────────

let items: AgendaItem[] = agendaSeed.map((seed) => ({
  ...seed,
  date: iso(addDays(TODAY, seed.off)),
}))

const listeners = new Set<() => void>()

function commit(next: AgendaItem[]) {
  items = next
  byDate = null
  for (const notify of listeners) notify()
}

export function subscribeAgenda(notify: () => void) {
  listeners.add(notify)
  return () => {
    listeners.delete(notify)
  }
}

export function agendaSnapshot(): AgendaItem[] {
  return items
}

export function addAgenda(item: AgendaItem) {
  commit([...items, item])
}

export function updateAgenda(next: AgendaItem) {
  commit(items.map((item) => (item.id === next.id ? next : item)))
}

export function removeAgenda(id: string) {
  commit(items.filter((item) => item.id !== id))
}

// ── 파생 ──────────────────────────────────────────────────────────────────

// 날짜별 묶음은 훑을 때마다 다시 만들면 비쌉니다. commit 이 무효화합니다.
let byDate: Map<string, AgendaItem[]> | null = null

/** 날짜 키 → 그날의 일정(시간순) */
export function agendaByDate(): Map<string, AgendaItem[]> {
  if (byDate) return byDate

  const map = new Map<string, AgendaItem[]>()
  for (const item of items) {
    const list = map.get(item.date)
    if (list) list.push(item)
    else map.set(item.date, [item])
  }
  for (const list of map.values()) list.sort((a, b) => a.time.localeCompare(b.time))

  byDate = map
  return map
}

// useAgendaFor 가 getSnapshot 으로 부르므로 빈 날에도 같은 배열을 돌려줘야 합니다.
// 매번 새 [] 를 만들면 스냅샷이 늘 달라져 렌더가 멈추지 않습니다.
const NONE: AgendaItem[] = []

export function agendaFor(dateISO: string): AgendaItem[] {
  return agendaByDate().get(dateISO) ?? NONE
}

/**
 * 시작 시각과 소요로 끝나는 시각. '17:00' + '40분' → '17:40'.
 * '종일'처럼 분으로 읽히지 않는 소요는 빈 문자열입니다.
 */
export function endTime(time: string, dur: string): string {
  const hours = /(\d+)\s*시간/.exec(dur)
  const mins = /(\d+)\s*분/.exec(dur)
  const total = (hours ? Number(hours[1]) * 60 : 0) + (mins ? Number(mins[1]) : 0)
  if (total <= 0) return ''

  const [h, m] = time.split(':').map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return ''

  // 자정을 넘기면 그날 안에서 말할 수 있는 시각이 아닙니다. 표시하지 않습니다.
  const end = h * 60 + m + total
  if (end >= 24 * 60) return ''

  return `${String(Math.floor(end / 60)).padStart(2, '0')}:${String(end % 60).padStart(2, '0')}`
}

/** 일정 하나를 id 로 찾습니다. 미팅보고서 작성 화면이 ?agenda= 로 받은 값을 폅니다. */
export function agendaById(id: string): AgendaItem | undefined {
  return items.find((item) => item.id === id)
}

// ── 구독 훅 ───────────────────────────────────────────────────────────────

/** 전체 목록을 보고 스스로 거르는 화면용. 목록이 바뀌면 다시 그립니다. */
export function useAgenda(): AgendaItem[] {
  return useSyncExternalStore(subscribeAgenda, agendaSnapshot)
}

/**
 * 하루치 일정. 그날 목록이 그대로면 같은 배열을 돌려주어 헛렌더를 막습니다.
 * (agendaByDate 가 캐시를 들고 있어 getSnapshot 이 매번 새 배열을 만들지 않습니다.)
 */
export function useAgendaFor(dateISO: string): AgendaItem[] {
  const snapshot = useCallback(() => agendaFor(dateISO), [dateISO])
  return useSyncExternalStore(subscribeAgenda, snapshot)
}
