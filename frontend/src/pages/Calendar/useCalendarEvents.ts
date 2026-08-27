import { useCallback, useMemo, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import {
  activityToAgenda,
  addAgenda,
  agendaToActivity,
  agendaToActivityPatch,
  removeAgenda,
  updateAgenda,
  useAgendaState,
} from '@/shared/agenda'
import type { ActivityPatchRequest, ActivityRead, CalendarEvent } from '@/types'
import { iso, monthMatrix } from '@/utils/date'

export const DEFAULTS = { time: '09:00', dur: '1시간', kind: 'visit', done: false } as const

const DAY = 86_400_000
const KST_OFFSET = 9 * 60 * 60_000

type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }

function shiftDateTime(value: string, days: number): string {
  return `${new Date(new Date(value).getTime() + days * DAY + KST_OFFSET)
    .toISOString()
    .slice(0, 19)}+09:00`
}

/**
 * 일정을 바꾸는 일만 모읍니다.
 *
 * 대시보드처럼 목록은 다른 곳에서 받아 오면서 등록·수정·삭제만 필요한 화면이 있습니다.
 * 아래 useCalendarEvents 를 통째로 쓰면 쓰지도 않을 전 기간 조회가 함께 딸려옵니다.
 */
export function useAgendaMutations() {
  const [mutationError, setMutationError] = useState<string | null>(null)

  const run = useCallback(async <T>(action: () => Promise<T>, fallback: string): Promise<T> => {
    setMutationError(null)
    try {
      return await action()
    } catch (reason: unknown) {
      setMutationError(errorMessage(reason, fallback))
      throw reason
    }
  }, [])

  const addEvent = useCallback(
    (draft: NewEvent) =>
      run(async () => {
        const event: CalendarEvent = { ...DEFAULTS, ...draft, id: '' }
        const { data } = await client.post<ActivityRead>('/activities', agendaToActivity(event))
        const added = activityToAgenda(data)
        addAgenda(added)
        return added
      }, '일정을 등록하지 못했습니다.'),
    [run],
  )

  const updateEvent = useCallback(
    (next: CalendarEvent) =>
      run(async () => {
        const { data } = await client.patch<ActivityRead>(
          `/activities/${next.id}`,
          agendaToActivityPatch(next),
        )
        const updated = activityToAgenda(data)
        updateAgenda(updated)
        return updated
      }, '일정을 수정하지 못했습니다.'),
    [run],
  )

  const removeEvent = useCallback(
    (id: string) =>
      run(async () => {
        await client.delete(`/activities/${id}`)
        removeAgenda(id)
      }, '일정을 삭제하지 못했습니다.'),
    [run],
  )

  const toggleComplete = useCallback(
    (id: string, done: boolean) =>
      run(
        async () => {
          const action = done ? 'reopen' : 'complete'
          const { data } = await client.post<ActivityRead>(`/activities/${id}/${action}`)
          const updated = activityToAgenda(data)
          updateAgenda(updated)
          return updated
        },
        done ? '일정을 다시 열지 못했습니다.' : '일정을 완료하지 못했습니다.',
      ),
    [run],
  )

  const clearMutationError = useCallback(() => setMutationError(null), [])

  return {
    mutationError,
    clearMutationError,
    run,
    addEvent,
    updateEvent,
    removeEvent,
    toggleComplete,
  }
}

export default function useCalendarEvents(cursor?: Date) {
  const range = useMemo(() => {
    if (!cursor) return { startDate: undefined, endDate: undefined }
    const days = monthMatrix(cursor)
    return { startDate: iso(days[0]), endDate: iso(days[days.length - 1]) }
  }, [cursor])
  const {
    items,
    loading,
    error: loadError,
    reload: reloadAgenda,
  } = useAgendaState(range.startDate, range.endDate)
  const {
    mutationError,
    clearMutationError,
    run,
    addEvent,
    updateEvent,
    removeEvent,
    toggleComplete,
  } = useAgendaMutations()

  const events: CalendarEvent[] = items
  const eventsByDate = useMemo(() => {
    const grouped = new Map<string, CalendarEvent[]>()
    for (const event of events) {
      const list = grouped.get(event.date)
      if (list) list.push(event)
      else grouped.set(event.date, [event])
    }
    for (const list of grouped.values()) list.sort((a, b) => a.time.localeCompare(b.time))
    return grouped
  }, [events])

  const moveEvent = useCallback(
    (id: string, date: string) =>
      run(async () => {
        const current = items.find((event) => event.id === id)
        if (!current || current.date === date) return current
        const days = Math.round(
          (new Date(`${date}T00:00:00+09:00`).getTime() -
            new Date(`${current.date}T00:00:00+09:00`).getTime()) /
            DAY,
        )
        const payload: ActivityPatchRequest = {
          starts_at: shiftDateTime(current.startsAt ?? agendaToActivity(current).starts_at, days),
          ends_at: current.endsAt ? shiftDateTime(current.endsAt, days) : null,
        }
        const { data } = await client.patch<ActivityRead>(`/activities/${id}`, payload)
        const moved = activityToAgenda(data)
        updateAgenda(moved)
        return moved
      }, '일정을 옮기지 못했습니다.'),
    [items, run],
  )

  const reload = useCallback(() => {
    clearMutationError()
    void reloadAgenda()
  }, [clearMutationError, reloadAgenda])

  return {
    events,
    eventsByDate,
    loading,
    error: mutationError ?? loadError,
    reload,
    addEvent,
    updateEvent,
    moveEvent,
    removeEvent,
    toggleComplete,
  }
}
