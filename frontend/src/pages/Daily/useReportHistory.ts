// 작성 리스트가 보는 조회입니다.
//
// 예전에는 일일·주간·월간과 미팅보고서를 통째로 받아 두고 검색·필터·달력을 전부
// 화면에서 계산했습니다. 한 쪽만 받는 지금 그렇게 하면 첫 쪽에 없는 일치 항목이
// 통째로 빠집니다. 그래서 조건은 서버가 걸고 화면은 받은 것만 그립니다.
//
// 조회는 셋으로 나뉩니다. 목록은 조건을 다 걸고 더보기로 잇고, 달력은 조건 없이
// 보이는 구간만 보고, 필터 선택지는 목록에 실제로 있는 값만 따로 묻습니다.
import { useEffect, useMemo, useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import useSearchPaging from '@/hooks/useSearchPaging'
import { toMeetingReport } from '@/pages/Meetings/useMeetingReports'
import { fetchReportPage } from '@/shared/reportQuery'
import { useScopeOwnerIds } from '@/shared/scope'
import type { ApiReportKind, ReportResponse } from '@/types'
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
const API_STATUS: Record<string, string> = {
  작성중: 'draft',
  '검토 대기': 'submitted',
  확정: 'approved',
  반려: 'rejected',
}

const some = (values: string[]) => (values.length > 0 ? values : undefined)

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
  const params = useMemo(
    () => ({
      report_kind: kindsOf(period),
      author_member_id: authorIds,
      // 빈 배열을 보내면 "아무것도 아닌 것" 을 고른 조건이 됩니다. 아예 뺍니다.
      status_code: some(filters.status.map((value) => API_STATUS[value])),
      approver: some(filters.approver),
      hospital: some(filters.hospital),
      start_date: rangeStartISO(filters.range) ?? undefined,
    }),
    [period, authorIds, filters],
  )

  const paging = useSearchPaging<ReportResponse>('/reports', query, {
    open: true,
    params,
    fallback: '보고서를 불러오지 못했습니다.',
  })

  const rows = useMemo(() => paging.matches.map(toRow).sort(byDateDesc), [paging.matches])
  // 한 번이라도 답을 받았는지. 화면 전체를 덮는 자리표시자는 첫 진입에만 서야 합니다.
  // 조건을 고칠 때마다 덮으면 "0건" 이 자리표시자로 보입니다.
  const ready = useRef(false)
  if (!paging.loading) ready.current = true

  return { ...paging, rows, ready: ready.current }
}

/**
 * 달력에 찍을 점. 검색어·필터를 걸지 않습니다. 그 달에 무엇이 있었는지가 목적입니다.
 *
 * ponytail: 보이는 구간이 한 달을 넘지 않아 한 쪽으로 끊습니다. 하루에 여러 건이
 * 쌓여 한 달이 30 건을 넘으면 뒤쪽 날의 점이 빠집니다. 그때는 날짜별로 접어 주는
 * 요약 API 를 서버에 두는 편이 맞습니다.
 */
export function useReportMarks(period: Period, fromISO: string, toISO: string) {
  const authorIds = useScopeOwnerIds()
  const [rows, setRows] = useState<ListRow[]>([])
  const key = JSON.stringify([kindsOf(period), authorIds, fromISO, toISO])

  useEffect(() => {
    const [kinds, ids, start, end] = JSON.parse(key) as [
      ApiReportKind[],
      string[] | undefined,
      string,
      string,
    ]
    const controller = new AbortController()

    void fetchReportPage(
      { report_kind: kinds, author_member_id: ids, start_date: start, end_date: end },
      controller.signal,
    )
      .then((items) => {
        if (!controller.signal.aborted) setRows(items.map(toRow))
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
