import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { useCurrentUser } from '@/auth/sessionContext'
import { addAgenda, agendaById, removeAgenda, updateAgenda } from '@/shared/agenda'
import type {
  ActivityActionTagCode,
  ActivityCategoryCode,
  ActivityCreateRequest,
  ActivityPatchRequest,
  ActivityRead,
  AgendaItem,
  AgendaKind,
  CalendarEvent,
  PageResponse,
  ScheduleStatus,
} from '@/types'
import { iso, monthMatrix } from '@/utils/date'

/** 새 일정의 기본값. 인라인 추가는 제목만 받고 나머지는 여기서 채웁니다. */
export const DEFAULTS = { time: '09:00', dur: '1시간', kind: 'internal', done: false } as const

const CATEGORY_BY_KIND: Record<AgendaKind, ActivityCategoryCode> = {
  visit: 'visit',
  demo: 'demo',
  edu: 'education',
  call: 'call',
  delivery: 'delivery',
  booth: 'conference',
  internal: 'internal',
}

const KIND_BY_CATEGORY: Record<ActivityCategoryCode, AgendaKind> = {
  visit: 'visit',
  demo: 'demo',
  education: 'edu',
  call: 'call',
  delivery: 'delivery',
  conference: 'booth',
  internal: 'internal',
}

const ACTION_TAG_BY_STATUS: Record<ScheduleStatus, ActivityActionTagCode> = {
  '첫 전화': 'first_call',
  미팅: 'meeting',
  '데모 요청': 'demo_requested',
  '데모 진행': 'demo_in_progress',
  '데모 완료': 'demo_completed',
  견적완료: 'quote_completed',
  계약완료: 'contract_completed',
  제품교육: 'product_training',
  납품완료: 'delivery_completed',
  내부회의: 'internal_meeting',
  주간점검: 'weekly_review',
  월간점검: 'monthly_review',
  분기점검: 'quarterly_review',
  컨퍼런스: 'conference',
  OJT: 'ojt',
}

const STATUS_BY_ACTION_TAG = Object.fromEntries(
  Object.entries(ACTION_TAG_BY_STATUS).map(([label, code]) => [code, label]),
) as Record<ActivityActionTagCode, ScheduleStatus>

const MINUTE = 60_000
const DAY = 86_400_000
const KST_OFFSET = 9 * 60 * MINUTE
const PAGE_LIMIT = 100

function kstIso(value: number | Date): string {
  const time = typeof value === 'number' ? value : value.getTime()
  return `${new Date(time + KST_OFFSET).toISOString().slice(0, 19)}+09:00`
}

function kstParts(value: string): { date: string; time: string } {
  const shifted = new Date(new Date(value).getTime() + KST_OFFSET).toISOString()
  return { date: shifted.slice(0, 10), time: shifted.slice(11, 16) }
}

function durationMinutes(label: string): number | null {
  const hours = /(\d+)\s*시간/.exec(label)
  const minutes = /(\d+)\s*분/.exec(label)
  const total = (hours ? Number(hours[1]) * 60 : 0) + (minutes ? Number(minutes[1]) : 0)
  return total > 0 ? total : null
}

function durationLabel(start: string, end: string): string {
  const minutes = Math.round((new Date(end).getTime() - new Date(start).getTime()) / MINUTE)
  if (minutes <= 0) return ''
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest}분`
  return rest === 0 ? `${hours}시간` : `${hours}시간 ${rest}분`
}

function contactLabel(activity: ActivityRead): string {
  return [activity.customer_contact_name, activity.customer_contact_job_title]
    .filter(Boolean)
    .join(' ')
}

function toCalendarEvent(activity: ActivityRead): CalendarEvent {
  const start = kstParts(activity.starts_at)
  return {
    id: activity.id,
    date: start.date,
    time: start.time,
    dur: activity.all_day
      ? '종일'
      : activity.ends_at
        ? durationLabel(activity.starts_at, activity.ends_at)
        : '',
    kind: KIND_BY_CATEGORY[activity.category_code],
    stage: activity.action_tag ? STATUS_BY_ACTION_TAG[activity.action_tag] : undefined,
    title: activity.title,
    hospital: activity.customer_company_name ?? '',
    dept: activity.customer_contact_department ?? '',
    contact: contactLabel(activity),
    place: activity.location ?? '',
    brief: activity.note ?? '',
    done: activity.completed_at !== null,
    activityType: activity.activity_type,
    customerContactId: activity.customer_contact_id,
    customerContactName: activity.customer_contact_name ?? '',
    productId: activity.product_id,
    product: activity.product_name ?? '',
    owner: activity.owner_display_name,
    startsAt: kstIso(new Date(activity.starts_at)),
    endsAt: activity.ends_at ? kstIso(new Date(activity.ends_at)) : null,
    allDay: activity.all_day,
  }
}

function nullableText(value?: string): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

function eventTimes(
  event: CalendarEvent,
): Pick<ActivityCreateRequest, 'starts_at' | 'ends_at' | 'all_day'> {
  const start = new Date(`${event.date}T${event.time}:00+09:00`)
  if (Number.isNaN(start.getTime())) throw new Error('invalid_activity_start')

  const allDay = event.allDay ?? false
  const minutes = durationMinutes(event.dur)
  return {
    starts_at: kstIso(start),
    ends_at: allDay || minutes === null ? null : kstIso(start.getTime() + minutes * MINUTE),
    all_day: allDay,
  }
}

function toActivityPayload(event: CalendarEvent): ActivityCreateRequest {
  return {
    customer_contact_id: event.customerContactId ?? null,
    product_id: event.productId ?? null,
    activity_type: event.activityType ?? (event.kind === 'internal' ? 'task' : 'meeting'),
    category_code: CATEGORY_BY_KIND[event.kind],
    title: event.title.trim(),
    ...eventTimes(event),
    location: nullableText(event.place),
    action_tag: event.stage ? ACTION_TAG_BY_STATUS[event.stage] : null,
    note: nullableText(event.brief),
  }
}

function shiftDateTime(value: string, days: number): string {
  return kstIso(new Date(value).getTime() + days * DAY)
}

function requestError(error: unknown, fallback: string): string {
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return '이 일정을 변경할 권한이 없습니다.'
  if (error.response?.status === 404) return '일정을 찾을 수 없습니다. 목록을 다시 불러오세요.'
  if (error.response?.status === 422) return '일정 정보를 확인해 주세요.'
  return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

type NewEvent = Partial<Omit<CalendarEvent, 'id'>> & { date: string; title: string }

const BLANK = () => ({
  off: 0,
  hospital: '',
  dept: '',
  contact: '',
  product: '',
  place: '',
  brief: '',
  history: [],
  tags: [],
  reported: true,
})

let seq = 0

interface ApiCalendarEvents {
  events: CalendarEvent[]
  eventsByDate: Map<string, CalendarEvent[]>
  loading: boolean
  error: string | null
  reload: () => void
  addEvent: (draft: NewEvent) => Promise<CalendarEvent>
  updateEvent: (next: CalendarEvent) => Promise<CalendarEvent>
  moveEvent: (id: string, date: string) => Promise<CalendarEvent | undefined>
  removeEvent: (id: string) => Promise<void>
}

interface LegacyCalendarEvents {
  addEvent: (draft: NewEvent) => AgendaItem
  updateEvent: (next: CalendarEvent) => void
  removeEvent: (id: string) => void
}

function useCalendarEvents(cursor: Date): ApiCalendarEvents
function useCalendarEvents(): LegacyCalendarEvents
function useCalendarEvents(cursor?: Date): ApiCalendarEvents | LegacyCalendarEvents {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const mutationRevision = useRef(0)
  const { profile } = useCurrentUser()

  const range = useMemo(() => {
    if (!cursor) return null
    const days = monthMatrix(cursor)
    return { startDate: iso(days[0]), endDate: iso(days[days.length - 1]) }
  }, [cursor])

  useEffect(() => {
    if (!range) return
    const controller = new AbortController()
    const revision = mutationRevision.current

    setLoading(true)
    setError(null)

    void (async () => {
      try {
        const items: ActivityRead[] = []
        let skip = 0

        while (!controller.signal.aborted && revision === mutationRevision.current) {
          const { data } = await client.get<PageResponse<ActivityRead>>('/activities', {
            params: {
              start_date: range.startDate,
              end_date: range.endDate,
              skip,
              limit: PAGE_LIMIT,
            },
            signal: controller.signal,
          })
          items.push(...data.items)
          if (!data.has_more || data.next_skip === null) break
          skip = data.next_skip
        }

        if (!controller.signal.aborted) {
          if (revision === mutationRevision.current) setEvents(items.map(toCalendarEvent))
          else setReloadKey((value) => value + 1)
        }
      } catch (reason: unknown) {
        if (!controller.signal.aborted) {
          if (revision === mutationRevision.current) {
            setError(requestError(reason, '일정 목록을 불러오지 못했습니다.'))
          } else {
            setReloadKey((value) => value + 1)
          }
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()

    return () => controller.abort()
  }, [range, reloadKey])

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

  const addApiEvent = useCallback(async (draft: NewEvent) => {
    const event: CalendarEvent = { ...DEFAULTS, ...draft, id: '' }
    setError(null)
    try {
      const { data } = await client.post<ActivityRead>('/activities', toActivityPayload(event))
      const added = toCalendarEvent(data)
      mutationRevision.current += 1
      setEvents((current) => [...current, added])
      return added
    } catch (reason: unknown) {
      setError(requestError(reason, '일정을 등록하지 못했습니다.'))
      throw reason
    }
  }, [])

  const updateApiEvent = useCallback(async (next: CalendarEvent) => {
    setError(null)
    try {
      const payload: ActivityPatchRequest = toActivityPayload(next)
      const { data } = await client.patch<ActivityRead>(`/activities/${next.id}`, payload)
      const updated = toCalendarEvent(data)
      mutationRevision.current += 1
      setEvents((current) => current.map((event) => (event.id === updated.id ? updated : event)))
      return updated
    } catch (reason: unknown) {
      setError(requestError(reason, '일정을 수정하지 못했습니다.'))
      throw reason
    }
  }, [])

  const moveApiEvent = useCallback(
    async (id: string, date: string) => {
      const current = events.find((event) => event.id === id)
      if (!current || current.date === date) return current

      const startsAt = current.startsAt ?? eventTimes(current).starts_at
      const endsAt = current.endsAt ?? eventTimes(current).ends_at ?? null
      const days = Math.round(
        (new Date(`${date}T00:00:00+09:00`).getTime() -
          new Date(`${current.date}T00:00:00+09:00`).getTime()) /
          DAY,
      )
      const payload: ActivityPatchRequest = {
        starts_at: shiftDateTime(startsAt, days),
        ends_at: endsAt ? shiftDateTime(endsAt, days) : null,
      }

      setError(null)
      try {
        const { data } = await client.patch<ActivityRead>(`/activities/${id}`, payload)
        const moved = toCalendarEvent(data)
        mutationRevision.current += 1
        setEvents((list) => list.map((event) => (event.id === moved.id ? moved : event)))
        return moved
      } catch (reason: unknown) {
        setError(requestError(reason, '일정을 옮기지 못했습니다.'))
        throw reason
      }
    },
    [events],
  )

  const removeApiEvent = useCallback(async (id: string) => {
    setError(null)
    try {
      await client.delete(`/activities/${id}`)
      mutationRevision.current += 1
      setEvents((current) => current.filter((event) => event.id !== id))
    } catch (reason: unknown) {
      setError(requestError(reason, '일정을 삭제하지 못했습니다.'))
      throw reason
    }
  }, [])

  const reload = useCallback(() => setReloadKey((value) => value + 1), [])

  const addLegacyEvent = useCallback(
    (draft: NewEvent) => {
      const item: AgendaItem = {
        ...BLANK(),
        ...DEFAULTS,
        owner: profile.name,
        ...draft,
        id: `ce-${++seq}`,
      }
      addAgenda(item)
      return item
    },
    [profile.name],
  )

  const updateLegacyEvent = useCallback((next: CalendarEvent) => {
    const current = agendaById(next.id)
    if (current) updateAgenda({ ...current, ...next })
  }, [])

  const removeLegacyEvent = useCallback((id: string) => removeAgenda(id), [])

  if (!cursor) {
    return {
      addEvent: addLegacyEvent,
      updateEvent: updateLegacyEvent,
      removeEvent: removeLegacyEvent,
    }
  }

  return {
    events,
    eventsByDate,
    loading,
    error,
    reload,
    addEvent: addApiEvent,
    updateEvent: updateApiEvent,
    moveEvent: moveApiEvent,
    removeEvent: removeApiEvent,
  }
}

export default useCalendarEvents
