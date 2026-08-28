// 작성 리스트의 필터 값과 판정. 화면과 도구 줄이 같은 정의를 봅니다.
// (보고서 종류는 기간 탭이 정하므로 여기서 다루지 않습니다.)
//
// 조건은 주소에 둡니다. 걸러 둔 목록을 링크로 건네면 받는 쪽도 같은 화면을 봅니다.
// 계약·발주·자료실 화면과 같은 방식이고, 여러 개를 고르는 값만 쉼표로 잇습니다.
import type { ReportStatus } from '@/types'

import { showsDaily, type Period } from './periods'

export type RangeFilter = 'all' | 'week' | 'month' | 'quarter'

export interface HistoryFilters {
  status: ReportStatus[]
  approver: string[]
  /** 업무보고서의 고객사. 업무 보고에는 없는 값이라 미팅 탭에서만 씁니다. */
  hospital: string[]
  range: RangeFilter
}

export const NO_FILTERS: HistoryFilters = { status: [], approver: [], hospital: [], range: 'all' }

export const FILTER_STATUSES: ReportStatus[] = ['작성중', '검토 대기', '확정', '반려']
export const FILTER_RANGES: { value: RangeFilter; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'week', label: '이번 주' },
  { value: 'month', label: '이번 달' },
  { value: 'quarter', label: '최근 3개월' },
]

const RANGE_VALUES = FILTER_RANGES.map((item) => item.value)

/** 켜져 있는 필터 개수. 배지와 초기화 버튼이 같은 값을 씁니다. */
export function countFilters(filters: HistoryFilters): number {
  return (
    filters.status.length +
    filters.approver.length +
    filters.hospital.length +
    (filters.range === 'all' ? 0 : 1)
  )
}

const splitList = (value: string | null) =>
  value
    ? value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
    : []

/** 주소에 적힌 조건을 필터로. 모르는 값은 무시하고 기본값으로 둡니다. */
export function parseFilters(params: URLSearchParams): HistoryFilters {
  const range = params.get('range') as RangeFilter | null
  return {
    status: splitList(params.get('status')).filter((value): value is ReportStatus =>
      FILTER_STATUSES.includes(value as ReportStatus),
    ),
    approver: splitList(params.get('approver')),
    hospital: splitList(params.get('hospital')),
    range: range && RANGE_VALUES.includes(range) ? range : 'all',
  }
}

/**
 * 필터를 주소에 씁니다. 기본값인 키는 지워서 주소를 짧게 둡니다.
 * 지금 탭에 없는 필터도 함께 지웁니다. 보이지 않는 조건이 목록을 걸러 버리면
 * 왜 비었는지 알 길이 없습니다.
 */
export function writeFilters(
  params: URLSearchParams,
  filters: HistoryFilters,
  period: Period,
): URLSearchParams {
  const next = new URLSearchParams(params)
  const put = (key: string, value: string) => {
    if (value === '') next.delete(key)
    else next.set(key, value)
  }

  put('status', filters.status.join(','))
  put('approver', showsApprover(period) ? filters.approver.join(',') : '')
  put('hospital', showsHospital(period) ? filters.hospital.join(',') : '')
  put('range', filters.range === 'all' ? '' : filters.range)
  return next
}

/** 보고 대상은 업무 보고에만 있는 값입니다. */
export const showsApprover = (period: Period) => showsDaily(period)

/**
 * 고객사는 미팅 탭에서만 고릅니다. '전체' 탭에서 걸면 고객사가 없는 업무 보고가
 * 전부 빠져 목록이 미팅만 남습니다.
 */
export const showsHospital = (period: Period) => period === 'meeting'
