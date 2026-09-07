// 작성 리스트가 보는 조회입니다.
//
// 예전에는 일일·주간·월간과 업무보고서를 통째로 받아 두고 검색·필터·달력을 전부
// 화면에서 계산했습니다. 한 쪽만 받는 지금 그렇게 하면 첫 쪽에 없는 일치 항목이
// 통째로 빠집니다. 그래서 조건은 서버가 걸고 화면은 받은 것만 그립니다.
//
// 조회는 셋으로 나뉩니다. 목록은 조건을 다 걸고 더보기로 잇고, 달력은 조건 없이
// 보이는 구간만 보고, 필터 선택지는 목록에 실제로 있는 값만 따로 묻습니다.
import { useEffect, useMemo, useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { PAGE_SIZE } from '@/constants/pagination'
import useSearchPaging from '@/hooks/useSearchPaging'
import { toMeetingReport } from '@/pages/Meetings/useMeetingReports'
import { useScopeOwnerIds } from '@/shared/scope'
import type { ApiReportKind, ApiReportStatus, PageResponse, ReportResponse } from '@/types'
import { addMonths, iso, startOfMonth, startOfWeek, TODAY } from '@/utils/date'

import { type HistoryFilters } from './historyFilters'
import { PERIOD_KIND, showsDaily, showsMeetings, type Period } from './periods'
import { byDateDesc, fromDailyReport, fromMeetingReport, type ListRow } from './rows'
import { toReport } from './useDailyReports'

const API_KIND: Record<string, ApiReportKind> = {
  일일: 'daily',
  주간: 'weekly',
  월간: 'monthly',
}
const API_STATUS: Record<string, ApiReportStatus[]> = {
  작성중: ['draft'],
  '검토 대기': ['submitted'],
  확정: ['approved'],
  반려: ['rejected', 'changes_requested'],
}
const MEETING_HISTORY_STATUS: ApiReportStatus[] = [
  'submitted',
  'approved',
  'rejected',
  'changes_requested',
]

interface HistoryQueryScope {
  report_kind: ApiReportKind[]
  status_code?: ApiReportStatus[]
}

const some = <T>(values: T[]) => (values.length > 0 ? values : undefined)

/** 달력과 드로어가 현재 보이는 기간의 보고서를 끝까지 받습니다. */
export async function fetchAllReportPages(
  params: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<ReportResponse[]> {
  const items: ReportResponse[] = []
  let skip = 0
  while (true) {
    const { data } = await client.get<PageResponse<ReportResponse>>('/reports', {
      params: { ...params, skip, limit: PAGE_SIZE },
      signal,
    })
    items.push(...data.items)
    if (!data.has_more || data.next_skip === null) return items
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }
}

/** 이 탭이 보는 보고서 종류. 서버가 이 목록으로 좁힙니다. */
function kindsOf(period: Period): ApiReportKind[] {
  const kind = PERIOD_KIND[period]
  const kinds: ApiReportKind[] = []
  // 'all' 과 'meeting' 은 PERIOD_KIND 가 null 이라 종류를 가르는 것은 아래 둘입니다.
  if (showsDaily(period)) {
    kinds.push(...(kind ? [API_KIND[kind]] : (['daily', 'weekly', 'monthly'] as ApiReportKind[])))
  }
  if (showsMeetings(period)) kinds.push('meeting')
  return kinds
}

/**
 * 일반 보고서의 draft는 목록에 남기되, 미팅 draft는 일정의 `계속 작성`에서만 보입니다.
 * 두 조건을 한 API 요청으로 AND 처리할 수 없어 전체 탭은 종류별 조회로 나눕니다.
 */
export function historyQueryScopes(
  period: Period,
  selectedStatuses?: ApiReportStatus[],
): HistoryQueryScope[] {
  const scopes: HistoryQueryScope[] = []
  const dailyKinds = kindsOf(period).filter((kind) => kind !== 'meeting')
  if (dailyKinds.length > 0) {
    scopes.push({
      report_kind: dailyKinds,
      ...(selectedStatuses === undefined ? {} : { status_code: selectedStatuses }),
    })
  }

  if (showsMeetings(period)) {
    const meetingStatuses =
      selectedStatuses === undefined
        ? MEETING_HISTORY_STATUS
        : selectedStatuses.filter((status) => status !== 'draft')
    if (meetingStatuses.length > 0) {
      scopes.push({ report_kind: ['meeting'], status_code: meetingStatuses })
    }
  }
  return scopes
}

/** 받은 한 줄을 종류에 맞는 모양으로 폅니다. 목록에는 두 종류가 섞입니다. */
export function toRow(item: ReportResponse): ListRow {
  return item.report_kind === 'meeting'
    ? fromMeetingReport(toMeetingReport(item))
    : fromDailyReport(toReport(item))
}

/**
 * 작성 리스트. 검색어·상태·보고 대상·고객사·기간을 모두 서버가 겁니다.
 *
 * 상태는 화면 말('확정')과 서버 코드('approved')가 달라 여기서 옮깁니다. 서버가 모르는
 * 말을 그대로 보내면 422 로 돌아옵니다.
 */
export function useReportList(period: Period, query: string, filters: HistoryFilters) {
  const authorIds = useScopeOwnerIds()
  const paramsByScope = useMemo(() => {
    const selectedStatuses = some(filters.status.flatMap((value) => API_STATUS[value]))
    return historyQueryScopes(period, selectedStatuses).map((scope) => ({
      ...scope,
      author_member_id: authorIds,
      // 빈 배열을 보내면 "아무것도 아닌 것" 을 고른 조건이 됩니다. 아예 뺍니다.
      approver: some(filters.approver),
      hospital: some(filters.hospital),
      start_date: rangeStartISO(filters.range) ?? undefined,
    }))
  }, [period, authorIds, filters])

  // 조회 개수는 탭이 바뀐 때도 고정해 React Hook 순서를 유지합니다.
  const first = useSearchPaging<ReportResponse>('/reports', query, {
    open: true,
    params: paramsByScope[0],
    enabled: paramsByScope[0] !== undefined,
    fallback: '보고서를 불러오지 못했습니다.',
  })
  const second = useSearchPaging<ReportResponse>('/reports', query, {
    open: true,
    params: paramsByScope[1],
    enabled: paramsByScope[1] !== undefined,
    fallback: '보고서를 불러오지 못했습니다.',
  })

  const rows = useMemo(
    () =>
      [...(paramsByScope[0] ? first.matches : []), ...(paramsByScope[1] ? second.matches : [])]
        .map(toRow)
        .sort(byDateDesc),
    [paramsByScope, first.matches, second.matches],
  )
  const loading =
    (paramsByScope[0] !== undefined && first.loading) ||
    (paramsByScope[1] !== undefined && second.loading)
  // 한 번이라도 답을 받았는지. 화면 전체를 덮는 자리표시자는 첫 진입에만 서야 합니다.
  // 조건을 고칠 때마다 덮으면 "0건" 이 자리표시자로 보입니다.
  const ready = useRef(false)
  if (!loading) ready.current = true

  return {
    rows,
    total: (paramsByScope[0] ? first.total : 0) + (paramsByScope[1] ? second.total : 0),
    loading,
    loadingMore:
      (paramsByScope[0] !== undefined && first.loadingMore) ||
      (paramsByScope[1] !== undefined && second.loadingMore),
    loadError:
      (paramsByScope[0] ? first.loadError : null) ?? (paramsByScope[1] ? second.loadError : null),
    hasMore:
      (paramsByScope[0] !== undefined && first.hasMore) ||
      (paramsByScope[1] !== undefined && second.hasMore),
    loadMore: () => {
      if (paramsByScope[0]) first.loadMore()
      if (paramsByScope[1]) second.loadMore()
    },
    reload: () => {
      if (paramsByScope[0]) first.reload()
      if (paramsByScope[1]) second.reload()
    },
    ready: ready.current,
  }
}

/** 달력에 찍을 점. 검색어·필터를 걸지 않습니다. 그 달에 무엇이 있었는지가 목적입니다. */
export function useReportMarks(period: Period, fromISO: string, toISO: string) {
  const authorIds = useScopeOwnerIds()
  const [rows, setRows] = useState<ListRow[]>([])
  const key = JSON.stringify([historyQueryScopes(period), authorIds, fromISO, toISO])

  useEffect(() => {
    const [scopes, ids, start, end] = JSON.parse(key) as [
      HistoryQueryScope[],
      string[] | undefined,
      string,
      string,
    ]
    const controller = new AbortController()

    void Promise.all(
      scopes.map((scope) =>
        fetchAllReportPages(
          {
            ...scope,
            author_member_id: ids,
            start_date: start,
            end_date: end,
          },
          controller.signal,
        ),
      ),
    )
      .then((pages) => {
        if (!controller.signal.aborted) setRows(pages.flat().map(toRow))
      })
      // 점이 안 찍히는 것으로 충분합니다. 목록이 이미 같은 실패를 알립니다.
      .catch(() => {
        if (!controller.signal.aborted) setRows([])
      })

    return () => controller.abort()
  }, [key])

  return useMemo(() => {
    const map = new Map<string, ListRow[]>()
    for (const row of rows) {
      const found = map.get(row.date)
      if (found) found.push(row)
      else map.set(row.date, [row])
    }
    return map
  }, [rows])
}

/** 필터의 선택지. 화면이 못 본 값까지 서버가 셉니다. */
export function useReportFilterOptions() {
  const authorIds = useScopeOwnerIds()
  const [options, setOptions] = useState<{ approvers: string[]; hospitals: string[] }>({
    approvers: [],
    hospitals: [],
  })
  const [error, setError] = useState<string | null>(null)
  const key = JSON.stringify(authorIds ?? null)

  useEffect(() => {
    const ids = JSON.parse(key) as string[] | null
    const controller = new AbortController()

    void client
      .get<{ approvers: string[]; hospitals: string[] }>('/report-filter-options', {
        params: { author_member_id: ids ?? undefined },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (!controller.signal.aborted) setOptions(data)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setOptions({ approvers: [], hospitals: [] })
        setError(errorMessage(reason, '필터 선택지를 불러오지 못했습니다.'))
      })

    return () => controller.abort()
  }, [key])

  return { ...options, error }
}

/** 기간 필터의 시작일. 'all' 이면 자르지 않습니다. */
export function rangeStartISO(range: HistoryFilters['range']): string | null {
  if (range === 'week') return iso(startOfWeek(TODAY))
  if (range === 'month') return iso(startOfMonth(TODAY))
  if (range === 'quarter') return iso(addMonths(TODAY, -3))
  return null
}
