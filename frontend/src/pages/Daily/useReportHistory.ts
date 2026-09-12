// 작성 리스트가 보는 조회입니다.
//
// 예전에는 일일·주간·월간과 업무보고서를 통째로 받아 두고 검색·필터·달력을 전부
// 화면에서 계산했습니다. 한 쪽만 받는 지금 그렇게 하면 첫 쪽에 없는 일치 항목이
// 통째로 빠집니다. 그래서 조건은 서버가 걸고 화면은 받은 것만 그립니다.
//
// 조회는 둘로 나뉩니다. 목록은 조건을 다 걸고 더보기로 잇고, 달력은 조건 없이
// 보이는 구간만 봅니다.
import { useEffect, useMemo, useRef, useState } from 'react'

import useSearchPaging from '@/hooks/useSearchPaging'
import { toMeetingReport } from '@/pages/Meetings/useMeetingReports'
import { fetchAllReportPages } from '@/shared/reportQuery'
import { useScopeOwnerIds } from '@/shared/scope'
import type { ApiReportKind, ApiReportStatus, ReportResponse } from '@/types'
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
  // 미팅 보고서는 팀장 검토를 받지 않아 draft 가 아닌 것이 모두 '작성완료'입니다.
  작성완료: ['submitted', 'approved', 'rejected', 'changes_requested'],
}
const MEETING_HISTORY_STATUS: ApiReportStatus[] = API_STATUS['작성완료']

interface HistoryQueryScope {
  report_kind: ApiReportKind[]
  status_code?: ApiReportStatus[]
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
 * 미팅 탭은 초안까지 통째로 봅니다. 상태 칩이 '작성중'을 고를 수 있어야 하기 때문입니다.
 *
 * '전체' 탭에서만 미팅 draft 를 뺍니다. 거기서는 일정의 `계속 작성`으로 이어 쓰는
 * 초안이 남의 확정 보고서와 한 줄에 섞여 보입니다. 일반 보고서의 draft 는 그대로 둡니다.
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
    if (period === 'meeting') {
      scopes.push({
        report_kind: ['meeting'],
        ...(selectedStatuses === undefined ? {} : { status_code: selectedStatuses }),
      })
      return scopes
    }
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
 * 작성 리스트. 검색어·상태·기간을 모두 서버가 겁니다.
 *
 * 상태는 화면 말('확정')과 서버 코드('approved')가 달라 여기서 옮깁니다. 서버가 모르는
 * 말을 그대로 보내면 422 로 돌아옵니다.
 */
export function useReportList(period: Period, query: string, filters: HistoryFilters) {
  const authorIds = useScopeOwnerIds()
  const paramsByScope = useMemo(() => {
    const selectedStatuses = filters.status === '' ? undefined : API_STATUS[filters.status]
    return historyQueryScopes(period, selectedStatuses).map((scope) => ({
      ...scope,
      author_member_id: authorIds,
      // 빈 문자열은 조건 없음입니다. 그대로 보내면 "빈 날짜" 를 고른 것이 됩니다.
      start_date: filters.start || undefined,
      end_date: filters.end || undefined,
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
