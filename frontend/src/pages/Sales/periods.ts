// 매출 분석의 기간 탭과 그룹 탭. 화면·표·차트가 모두 이 정의 하나를 봅니다.
//
// 상반기·하반기를 분기와 나란히 독립 탭으로 둡니다. "반기" 탭 하나에 상·하를 다시
// 고르게 하면 클릭이 두 번이 되고, 영업 보고에서는 상반기와 하반기를 아예 다른
// 단위로 말하기 때문입니다.
import {
  addDays,
  addMonths,
  endOfMonth,
  fmtDotShort,
  fmtHalf,
  fmtMonth,
  fmtQuarter,
  iso,
  startOfMonth,
  startOfQuarter,
  startOfWeek,
  TODAY,
  weekRangeLabel,
} from '@/utils/date'

export type PeriodType = 'week' | 'month' | 'quarter' | 'h1' | 'h2' | 'year'

export const PERIODS: PeriodType[] = ['week', 'month', 'quarter', 'h1', 'h2', 'year']

export const PERIOD_LABEL: Record<PeriodType, string> = {
  week: '주간',
  month: '월',
  quarter: '분기',
  h1: '상반기',
  h2: '하반기',
  year: '년',
}

/** 현재 기간으로 되돌아가는 버튼의 문구 */
export const PERIOD_RESET: Record<PeriodType, string> = {
  week: '이번 주',
  month: '이번 달',
  quarter: '이번 분기',
  h1: '올해',
  h2: '올해',
  year: '올해',
}

/** 계약을 무엇으로 묶을지. 왼쪽 표와 오른쪽 매출 패널이 함께 이 값을 따릅니다. */
export type GroupBy = 'org' | 'region' | 'product'

export const GROUP_BYS: GroupBy[] = ['org', 'region', 'product']

export const GROUP_LABEL: Record<GroupBy, string> = {
  org: '회사별',
  region: '지역별',
  product: '상품별',
}

/** 표의 첫 열 제목 */
export const GROUP_HEADER: Record<GroupBy, string> = {
  org: '회사',
  region: '지역',
  product: '상품',
}

/** 매출 목표를 가진 축인지. 상품에는 목표가 없어 달성률을 말할 수 없습니다. */
export const hasTarget = (by: GroupBy) => by !== 'product'

export interface Range {
  /** 시작일 YYYY-MM-DD (포함) */
  fromISO: string
  /** 종료일 YYYY-MM-DD (포함) */
  toISO: string
  /** "2026년 하반기" 처럼 기간 네비에 뜨는 이름 */
  label: string
  /** "7.1 – 12.31" 처럼 라벨 옆에 붙는 실제 날짜 */
  sub: string
}

/** 상·하반기 탭은 반년을 이미 고정하고 있어 이동 단위가 1년입니다. */
const isHalf = (type: PeriodType) => type === 'h1' || type === 'h2'

/** 기준 날짜에서 offset 만큼 이동한 기간의 시작일 */
function startFor(type: PeriodType, offset: number): Date {
  const year = TODAY.getFullYear() + (isHalf(type) || type === 'year' ? offset : 0)

  switch (type) {
    case 'week':
      return addDays(startOfWeek(TODAY), offset * 7)
    case 'month':
      return addMonths(startOfMonth(TODAY), offset)
    case 'quarter':
      return addMonths(startOfQuarter(TODAY), offset * 3)
    case 'h1':
    case 'year':
      return new Date(year, 0, 1)
    case 'h2':
      return new Date(year, 6, 1)
  }
}

/** 시작일로부터 그 기간의 마지막 날 */
function endFor(type: PeriodType, start: Date): Date {
  switch (type) {
    case 'week':
      return addDays(start, 6)
    case 'month':
      return endOfMonth(start)
    case 'quarter':
      return endOfMonth(addMonths(start, 2))
    case 'h1':
    case 'h2':
      return endOfMonth(addMonths(start, 5))
    case 'year':
      return new Date(start.getFullYear(), 11, 31)
  }
}

function labelFor(type: PeriodType, start: Date): string {
  switch (type) {
    case 'week':
      return weekRangeLabel(Array.from({ length: 7 }, (_, i) => addDays(start, i)))
    case 'month':
      return fmtMonth(start)
    case 'quarter':
      return fmtQuarter(start)
    case 'h1':
    case 'h2':
      return fmtHalf(start)
    case 'year':
      return `${start.getFullYear()}년`
  }
}

/**
 * offset 0 이 현재 기간, -1 이 직전 기간입니다.
 * 상·하반기와 년 탭에서는 offset 이 연도 단위로 움직입니다.
 */
export function resolveRange(type: PeriodType, offset: number): Range {
  const start = startFor(type, offset)
  const end = endFor(type, start)

  return {
    fromISO: iso(start),
    toISO: iso(end),
    label: labelFor(type, start),
    // 주간 라벨은 이미 날짜라서 같은 말을 두 번 하지 않습니다.
    sub: type === 'week' ? '' : `${fmtDotShort(start)} – ${fmtDotShort(end)}`,
  }
}

/** 전기간 대비를 계산할 직전 구간 */
export function prevRange(type: PeriodType, offset: number): Range {
  return resolveRange(type, offset - 1)
}

export function toPeriodType(param: string | null): PeriodType {
  return PERIODS.includes(param as PeriodType) ? (param as PeriodType) : 'month'
}

export function toGroupBy(param: string | null): GroupBy {
  return GROUP_BYS.includes(param as GroupBy) ? (param as GroupBy) : 'org'
}

/** 쿼리의 이동량. 숫자가 아니면 현재 기간으로 봅니다. */
export function toOffset(param: string | null): number {
  const n = Number(param)
  return Number.isInteger(n) ? n : 0
}
