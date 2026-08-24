import { useCallback, useEffect, useSyncExternalStore } from 'react'

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

export function useAgenda(): AgendaItem[] {
  const scopeKey = useScopeKey()
  useEffect(() => {
    void loadAgenda(DEFAULT_START_DATE, DEFAULT_END_DATE)
  }, [scopeKey])
  return useSyncExternalStore(subscribeAgenda, agendaSnapshot, agendaSnapshot)
}

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

export function useAgendaFor(dateISO: string): AgendaItem[] {
  useAgenda()
  const snapshot = useCallback(() => agendaFor(dateISO), [dateISO])
  return useSyncExternalStore(subscribeAgenda, snapshot, snapshot)
}
