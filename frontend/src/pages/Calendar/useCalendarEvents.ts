import { useCallback, useMemo, useState } from 'react'

import { agendaByDate } from '@/content/agenda'
import type { CalendarEvent } from '@/content/types'

// 백엔드가 붙는 지점은 이 파일 하나입니다. 화면은 아래 반환값만 알면 되므로
// seed 를 API 응답으로, 각 mutator 를 요청으로 바꾸면 나머지는 그대로 둘 수 있습니다.
//
// 저장은 메모리에만 합니다. 새로고침하면 목업 초기 상태로 돌아갑니다.
const seedEvents: CalendarEvent[] = Object.values(agendaByDate).flat()

/** 새 일정의 기본값. 인라인 추가는 제목만 받고 나머지는 여기서 채웁니다. */
const DEFAULTS = { time: '09:00', dur: '1시간', kind: 'internal', done: false } as const

// Date.now() 는 같은 밀리초 안에 두 번 부르면 같은 값이 나옵니다. id 가 겹치면
// 드래그가 엉뚱한 일정을 옮기고 React 키도 중복되므로 증가하는 번호를 씁니다.
let seq = 0

type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }

export default function useCalendarEvents() {
  const [events, setEvents] = useState<CalendarEvent[]>(seedEvents)

  /** 날짜 키 → 그날의 일정(시간순). 셀이 매번 전체 목록을 훑지 않게 한 번만 만듭니다. */
  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const event of events) {
      const list = map.get(event.date)
      if (list) list.push(event)
      else map.set(event.date, [event])
    }
    for (const list of map.values()) list.sort((a, b) => a.time.localeCompare(b.time))
    return map
  }, [events])

  const addEvent = useCallback((draft: NewEvent) => {
    // 목업이라 서버가 id 를 주지 않습니다. 화면 안에서만 겹치지 않으면 됩니다.
    const event: CalendarEvent = { ...DEFAULTS, ...draft, id: `ce-${++seq}` }
    setEvents((prev) => [...prev, event])
    return event
  }, [])

  const updateEvent = useCallback((next: CalendarEvent) => {
    setEvents((prev) => prev.map((e) => (e.id === next.id ? next : e)))
  }, [])

  /** 날짜만 옮깁니다. 시간은 그대로 두어 그날 안에서의 순서가 유지됩니다. */
  const moveEvent = useCallback((id: string, date: string) => {
    setEvents((prev) => prev.map((e) => (e.id === id && e.date !== date ? { ...e, date } : e)))
  }, [])

  const removeEvent = useCallback((id: string) => {
    setEvents((prev) => prev.filter((e) => e.id !== id))
  }, [])

  const toggleDone = useCallback((id: string) => {
    setEvents((prev) => prev.map((e) => (e.id === id ? { ...e, done: !e.done } : e)))
  }, [])

  return { eventsByDate, addEvent, updateEvent, moveEvent, removeEvent, toggleDone }
}
