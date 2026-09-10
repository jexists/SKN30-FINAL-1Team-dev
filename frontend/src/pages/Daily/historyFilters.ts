// 작성 리스트의 필터 값과 판정. 화면과 도구 줄이 같은 정의를 봅니다.
// (보고서 종류는 기간 탭이 정하므로 여기서 다루지 않습니다.)
//
// 조건은 주소에 둡니다. 걸러 둔 목록을 링크로 건네면 받는 쪽도 같은 화면을 봅니다.
// 계약·발주·자료실 화면과 같은 방식입니다.
import type { ColumnTone, ReportStatus } from '@/types'
import { addDays, addMonths, endOfMonth, iso, startOfMonth, startOfWeek, TODAY } from '@/utils/date'

import type { Period } from './periods'

export interface HistoryFilters {
  /** 빈 문자열이면 전체입니다. */
  status: ReportStatus | ''
  /** 기간의 시작·끝. 빈 문자열이면 그쪽을 자르지 않습니다. */
  start: string
  end: string
}

export const NO_FILTERS: HistoryFilters = { status: '', start: '', end: '' }

export const FILTER_STATUSES: ReportStatus[] = ['작성중', '검토 대기', '확정', '반려']

/** 상태 탭 앞에 붙는 점. 보고서 배지와 같은 색이지만 그쪽은 StatusTone 이라 표가 다릅니다. */
export const STATUS_TONE: Record<ReportStatus, ColumnTone> = {
  작성중: 'blue',
  '검토 대기': 'orange',
  확정: 'green',
  반려: 'red',
}

/** 기간 빠른 선택. 누르면 시작·끝을 함께 갈아 끼웁니다. */
export const RANGE_PRESETS: { value: string; label: string }[] = [
  { value: 'all', label: '전체' },
  { value: 'week', label: '이번 주' },
  { value: 'month', label: '이번 달' },
  { value: 'quarter', label: '최근 3개월' },
]

/**
 * 빠른 선택이 채우는 구간. 시작·끝을 모두 채웁니다. 눌렀는데 종료일 칸이 비어 있으면
 * 고장으로 보입니다.
 *
 * 끝은 오늘이 아니라 그 구간의 마지막 날입니다. 오늘로 자르면 앞으로 잡힌 미팅
 * 보고서가 빠져 '이번 달' 이 이번 달을 다 보여 주지 못합니다.
 */
export function presetRange(value: string): { start: string; end: string } {
  if (value === 'week') {
    const first = startOfWeek(TODAY)
    return { start: iso(first), end: iso(addDays(first, 6)) }
  }
  if (value === 'month') return { start: iso(startOfMonth(TODAY)), end: iso(endOfMonth(TODAY)) }
  if (value === 'quarter') return { start: iso(addMonths(TODAY, -3)), end: iso(endOfMonth(TODAY)) }
  return { start: '', end: '' }
}

/**
 * 지금 구간과 똑같은 빠른 선택. 없으면 null 이라 아무 칸도 켜지지 않습니다.
 * 날짜를 직접 고치면 그 순간 어느 것과도 맞지 않게 됩니다.
 */
export function activePreset(filters: HistoryFilters): string | null {
  const found = RANGE_PRESETS.find((preset) => {
    const range = presetRange(preset.value)
    return range.start === filters.start && range.end === filters.end
  })
  return found?.value ?? null
}

/** 켜져 있는 필터 개수. 초기화 버튼이 이 값을 봅니다. */
export function countFilters(filters: HistoryFilters): number {
  return (
    (filters.status === '' ? 0 : 1) + (filters.start === '' ? 0 : 1) + (filters.end === '' ? 0 : 1)
  )
}

/** 주소에 적힌 조건을 필터로. 모르는 값은 무시하고 기본값으로 둡니다. */
export function parseFilters(params: URLSearchParams): HistoryFilters {
  const status = params.get('status')
  return {
    status: FILTER_STATUSES.includes(status as ReportStatus) ? (status as ReportStatus) : '',
    start: params.get('start') ?? '',
    end: params.get('end') ?? '',
  }
}

/**
 * 필터를 주소에 씁니다. 기본값인 키는 지워서 주소를 짧게 둡니다.
 * 미팅 탭에는 작성중이 없으므로 그 값도 함께 지웁니다. 보이지 않는 조건이 목록을
 * 걸러 버리면 왜 비었는지 알 길이 없습니다.
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

  put('status', period === 'meeting' && filters.status === '작성중' ? '' : filters.status)
  put('start', filters.start)
  put('end', filters.end)
  return next
}
