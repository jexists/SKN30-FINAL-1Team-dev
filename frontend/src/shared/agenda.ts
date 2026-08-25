import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type {
  ActivityActionTagCode,
  ActivityCategoryCode,
  ActivityCreateRequest,
  ActivityRead,
  AgendaItem,
  AgendaKind,
  CalendarEvent,
  ExternalStatus,
  InternalStatus,
  PageResponse,
  ScheduleStatus,
} from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import { getOwnMemberIds, getScopeKey, getScopeOwnerIds, useScopeKey } from './scope'

export const KIND_LABEL: Record<AgendaKind, string> = {
  visit: '방문',
  demo: '데모',
  edu: '교육',
  call: '전화',
  delivery: '납품',
  booth: '학회',
  internal: '내부',
}

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

export const INTERNAL_STATUSES: readonly InternalStatus[] = [
  '내부회의',
  '주간점검',
  '월간점검',
  '분기점검',
  '컨퍼런스',
  'OJT',
]

export function statusScope(status: ScheduleStatus): '내부' | '외부' {
  return (INTERNAL_STATUSES as readonly ScheduleStatus[]).includes(status) ? '내부' : '외부'
}

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

export function activityToAgenda(activity: ActivityRead): AgendaItem {
  const start = kstParts(activity.starts_at)
  return {
    id: activity.id,
    owner: activity.owner_display_name,
    off: Math.round((parseISO(start.date).getTime() - TODAY.getTime()) / DAY),
    date: start.date,
    time: start.time,
    dur: activity.all_day
      ? '종일'
      : activity.ends_at
        ? durationLabel(activity.starts_at, activity.ends_at)
        : '',
    kind: KIND_BY_CATEGORY[activity.category_code],
    hospital: activity.customer_company_name ?? '',
    dept: activity.customer_contact_department ?? '',
    contact: [activity.customer_contact_name, activity.customer_contact_job_title]
      .filter(Boolean)
      .join(' '),
    product: activity.product_name ?? '',
    stage: activity.action_tag ? STATUS_BY_ACTION_TAG[activity.action_tag] : undefined,
    place: activity.location ?? '',
    title: activity.title,
    brief: activity.note ?? '',
    history: [],
    tags: [],
    done: activity.completed_at !== null,
    reported: false,
    activityType: activity.activity_type,
    customerContactId: activity.customer_contact_id,
    customerContactName: activity.customer_contact_name ?? '',
    salesDealId: activity.sales_deal_id,
    productId: activity.product_id,
    ownerMemberId: activity.owner_member_id,
    startsAt: kstIso(new Date(activity.starts_at)),
    endsAt: activity.ends_at ? kstIso(new Date(activity.ends_at)) : null,
    allDay: activity.all_day,
  }
}

function nullableText(value?: string): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed === '' ? null : trimmed
}

export function agendaToActivity(event: CalendarEvent): ActivityCreateRequest {
  const start = new Date(`${event.date}T${event.time}:00+09:00`)
  if (Number.isNaN(start.getTime())) throw new Error('invalid_activity_start')
  const allDay = event.allDay ?? false
  const minutes = durationMinutes(event.dur)
  return {
    customer_contact_id: event.customerContactId ?? null,
    sales_deal_id: event.salesDealId ?? null,
    product_id: event.productId ?? null,
    activity_type: event.activityType ?? (event.kind === 'internal' ? 'task' : 'meeting'),
    category_code: CATEGORY_BY_KIND[event.kind],
    title: event.title.trim(),
    starts_at: kstIso(start),
    ends_at: allDay || minutes === null ? null : kstIso(start.getTime() + minutes * MINUTE),
    all_day: allDay,
    location: nullableText(event.place),
    action_tag: event.stage ? ACTION_TAG_BY_STATUS[event.stage] : null,
    note: nullableText(event.brief),
  }
}

let items: AgendaItem[] = []
let loading = true
let loadError: string | null = null
let loadedKey: string | null = null
let loadPromise: Promise<void> | null = null
let revision = 0
const listeners = new Set<() => void>()

function notify() {
  revision += 1
  for (const listener of listeners) listener()
}

function commit(next: AgendaItem[]) {
  items = next
  byDate = null
  notify()
}

export function subscribeAgenda(notifyListener: () => void) {
  listeners.add(notifyListener)
  return () => listeners.delete(notifyListener)
}

export function agendaSnapshot(): AgendaItem[] {
  return items
}

/**
 * 보기 범위를 좁혀 둔 채로 자기 일정을 만들면 필터 밖인데도 목록에 붙습니다.
 * 범위 밖 날짜에서 이미 같은 일이 일어나므로 그대로 둡니다. 다시 불러오면 정리됩니다.
 */
export function addAgenda(item: AgendaItem) {
  commit([...items, item])
}

export function updateAgenda(next: AgendaItem) {
  commit(items.map((item) => (item.id === next.id ? next : item)))
}

export function removeAgenda(id: string) {
  commit(items.filter((item) => item.id !== id))
}

/**
 * 대시보드가 첫 응답으로 받아 온 하루치를 스토어에 그대로 심습니다.
 *
 * 심어 두지 않으면 하루 목록을 보는 쪽이 같은 날을 한 번 더 받아 옵니다. 조회한 것과
 * 같은 자리에 같은 키로 넣어야 그 재조회가 캐시에 걸립니다.
 */
export function seedAgenda(dateISO: string, seeded: AgendaItem[]) {
  const key = `${getScopeKey()}|${dateISO}:${dateISO}`
  // 다른 날을 펼쳐 둔 채로 대시보드를 새로 고칠 수 있습니다. 그때 오늘치로 덮으면
  // 보고 있던 목록이 통째로 바뀝니다. 그 날짜는 자기 조회가 채우게 둡니다.
  if (loadedKey !== null && loadedKey !== key) return
  loadedKey = key
  loadError = null
  commit(seeded)
}

async function fetchAgenda(
  startDate: string,
  endDate: string,
  ownerIds?: readonly string[],
): Promise<AgendaItem[]> {
  // ponytail: 현재 소비 화면은 전건 집계가 필요합니다. 커지면 서버 요약 API로 바꿉니다.
  const result: AgendaItem[] = []
  let skip = 0
  while (true) {
    const { data } = await client.get<PageResponse<ActivityRead>>('/activities', {
      params: {
        start_date: startDate,
        end_date: endDate,
        owner_member_id: ownerIds,
        skip,
        limit: PAGE_LIMIT,
      },
    })
    result.push(...data.items.map(activityToAgenda))
    if (!data.has_more || data.next_skip === null) return result
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }
}

export function loadAgenda(
  startDate: string,
  endDate: string,
  force = false,
  ownScopeOnly = false,
): Promise<void> {
  // 범위를 매번 여기서 읽습니다. 아래 재진입 가드가 자기를 다시 부르므로, 요청이
  // 날아가는 사이에 범위가 바뀌면 그 재귀 호출이 새 범위를 봐야 합니다.
  const ownerIds = ownScopeOnly ? getOwnMemberIds() : getScopeOwnerIds()
  const key = `${ownScopeOnly ? 'own' : getScopeKey()}|${startDate}:${endDate}`
  if (loadPromise) {
    return loadPromise.then(() => loadAgenda(startDate, endDate, force, ownScopeOnly))
  }
  if (loadedKey === key && !force) return Promise.resolve()
  commit([])
  loading = true
  loadError = null
  notify()
  loadPromise = fetchAgenda(startDate, endDate, ownerIds)
    .then((next) => {
      loadedKey = key
      commit(next)
    })
    .catch((error: unknown) => {
      loadError = errorMessage(error, '일정 목록을 불러오지 못했습니다.')
    })
    .finally(() => {
      loading = false
      loadPromise = null
      notify()
    })
  return loadPromise
}

let byDate: Map<string, AgendaItem[]> | null = null
const NONE: AgendaItem[] = []

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

export function agendaFor(dateISO: string): AgendaItem[] {
  return agendaByDate().get(dateISO) ?? NONE
}

export function endTime(time: string, dur: string): string {
  const hours = /(\d+)\s*시간/.exec(dur)
  const mins = /(\d+)\s*분/.exec(dur)
  const total = (hours ? Number(hours[1]) * 60 : 0) + (mins ? Number(mins[1]) : 0)
  if (total <= 0) return ''
  const [h, m] = time.split(':').map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return ''
  const end = h * 60 + m + total
  if (end >= 24 * 60) return ''
  return `${String(Math.floor(end / 60)).padStart(2, '0')}:${String(end % 60).padStart(2, '0')}`
}

export function agendaById(id: string): AgendaItem | undefined {
  return items.find((item) => item.id === id)
}

const DEFAULT_START_DATE = '2000-01-01'
const DEFAULT_END_DATE = '2099-12-31'

/**
 * `ownScopeOnly` 는 보기 범위를 무시하고 본인 일정만 봅니다.
 *
 * 보고서를 쓰는 화면이 씁니다. 보고는 "내가 한 일" 을 적는 일이라 팀 전체를 보고 있어도
 * 후보에 남의 일정이 섞이면 안 됩니다. 조회하는 화면과 성격이 다릅니다.
 */
export function useAgendaState(
  startDate = DEFAULT_START_DATE,
  endDate = DEFAULT_END_DATE,
  ownScopeOnly = false,
) {
  const scopeKey = useScopeKey()
  useEffect(() => {
    void loadAgenda(startDate, endDate, false, ownScopeOnly)
  }, [endDate, startDate, ownScopeOnly, scopeKey])
  useSyncExternalStore(
    subscribeAgenda,
    () => revision,
    () => revision,
  )
  return {
    items,
    loading,
    error: loadError,
    reload: () => loadAgenda(startDate, endDate, true, ownScopeOnly),
  }
}

/**
 * 활동 하나만 받아 옵니다. 보고서 작성 화면이 주소의 활동 번호로 바로 들어올 때 씁니다.
 *
 * 목록에서 찾으면 그 활동이 언제 것인지 모르는 채로 전 기간을 받아야 합니다. 번호를 아는
 * 조회이므로 단건으로 받습니다.
 */
export function useAgendaItem(id: string) {
  const [item, setItem] = useState<AgendaItem | undefined>(undefined)
  const [loading, setLoading] = useState(id !== '')
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const scopeKey = useScopeKey()

  useEffect(() => {
    if (id === '') {
      setItem(undefined)
      setLoading(false)
      setError(null)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    client
      .get<ActivityRead>(`/activities/${id}`, { signal: controller.signal })
      .then(({ data }) => {
        const next = activityToAgenda(data)
        // 보고는 본인이 한 일을 적습니다. 주소를 직접 고쳐 남의 일정으로 들어오면 비웁니다.
        // 팀장이 아니면 서버가 이미 본인 것만 주므로 그대로 받습니다.
        const own = getOwnMemberIds()
        const mine =
          own === undefined ||
          (next.ownerMemberId !== undefined && own.includes(next.ownerMemberId))
        setItem(mine ? next : undefined)
        setLoading(false)
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setError(errorMessage(cause, '일정을 불러오지 못했습니다.'))
        setLoading(false)
      })
    return () => controller.abort()
  }, [id, reloadKey, scopeKey])

  return { item, loading, error, reload: () => setReloadKey((key) => key + 1) }
}

/**
 * 하루치만 받아 옵니다. 대시보드가 첫 응답으로 심어 둔 날은 캐시에 걸려 다시 받지 않습니다.
 */
export function useAgendaFor(dateISO: string): AgendaItem[] {
  useAgendaState(dateISO, dateISO)
  const snapshot = useCallback(() => agendaFor(dateISO), [dateISO])
  return useSyncExternalStore(subscribeAgenda, snapshot, snapshot)
}
