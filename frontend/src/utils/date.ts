// demo/layout_v3.html 의 날짜 유틸을 옮긴 것입니다.
//
// 날짜 키는 toISOString() 대신 아래 iso() 로 만듭니다. toISOString() 은 UTC 로
// 옮기면서 KST 자정 이전 시각을 하루 앞으로 밀어 버립니다.

export const WD = ['일', '월', '화', '수', '목', '금', '토'] as const

export function startOfDay(d: Date): Date {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}

export function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

/** 일요일이 주의 시작입니다. WD 배열의 순서와 같습니다. */
export function startOfWeek(d: Date): Date {
  return addDays(startOfDay(d), -d.getDay())
}

// 말일이 다른 달로 넘치지 않게 1일로 옮겨 놓고 달을 더합니다.
// (예: 1월 31일에 +1 을 하면 setMonth 만으로는 3월 3일이 됩니다.)
export function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

/**
 * 날짜를 지키면서 달을 더합니다. 견적 유효기간처럼 "그날로부터 N개월" 을 셀 때 씁니다.
 * 달을 옮기고 나면 없는 날짜가 되는 경우가 있어(1/31 + 1개월) 그 달 말일로 깎습니다.
 *
 * 달력을 넘기는 addMonths 와 다릅니다. 그쪽은 늘 그 달 1일을 돌려줍니다.
 */
export function addMonthsKeepingDay(d: Date, n: number): Date {
  const day = d.getDate()
  const moved = new Date(d.getFullYear(), d.getMonth() + n, 1)
  const lastDay = new Date(moved.getFullYear(), moved.getMonth() + 1, 0).getDate()
  return new Date(moved.getFullYear(), moved.getMonth(), Math.min(day, lastDay))
}

/**
 * `from` 에서 `to` 까지가 정확히 몇 개월인지. 딱 떨어지지 않으면 null 입니다.
 * 저장된 유효기한을 다시 열 때 기간 선택으로 되돌릴 수 있는지 가리는 데 씁니다.
 */
export function wholeMonthsBetween(from: Date, to: Date): number | null {
  const months = (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth())
  if (months <= 0) return null
  return iso(addMonthsKeepingDay(from, months)) === iso(to) ? months : null
}

/**
 * 그 달을 덮는 6주 × 7일 = 42칸. 앞뒤 달의 날짜가 앞뒤에 섞여 들어옵니다.
 * 칸 수를 항상 42로 고정해야 달을 넘길 때 그리드 높이가 출렁이지 않습니다.
 */
export function monthMatrix(d: Date): Date[] {
  const first = startOfWeek(startOfMonth(d))
  return Array.from({ length: 42 }, (_, i) => addDays(first, i))
}

/** 그 분기의 첫날. 1·4·7·10월 1일입니다. */
export function startOfQuarter(d: Date): Date {
  return new Date(d.getFullYear(), Math.floor(d.getMonth() / 3) * 3, 1)
}

// 다음 달 0일은 이번 달 말일입니다. 달마다 다른 일수를 직접 세지 않아도 됩니다.
export function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0)
}

const pad = (n: number) => String(n).padStart(2, '0')

/** 로컬 기준 YYYY-MM-DD. 날짜별 데이터를 묶는 키로 씁니다. */
export function iso(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function parseISO(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** 2026.08.11 — 표처럼 자리가 좁은 곳에서 씁니다. */
export function fmtDotShort(d: Date): string {
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`
}

/** 2026.08.11 (화) */
export function fmtDot(d: Date): string {
  return `${fmtDotShort(d)} (${WD[d.getDay()]})`
}

/** 8월 11일 (화) */
export function fmtDay(d: Date): string {
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WD[d.getDay()]})`
}

/** 2026년 8월 */
export function fmtMonth(d: Date): string {
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월`
}

/** 2026년 3분기 */
export function fmtQuarter(d: Date): string {
  return `${d.getFullYear()}년 ${Math.floor(d.getMonth() / 3) + 1}분기`
}

/** 2026년 하반기 */
export function fmtHalf(d: Date): string {
  return `${d.getFullYear()}년 ${d.getMonth() < 6 ? '상반기' : '하반기'}`
}

/** 오늘 기준 offset 을 남은 기한으로 읽습니다. 0 → 오늘, 3 → D-3, -2 → 2일 지남 */
export function ddayLabel(off: number): string {
  if (off === 0) return '오늘'
  return off > 0 ? `D-${off}` : `${-off}일 지남`
}

/** 8월 9일 – 15일. 달을 넘으면 7월 30일 – 8월 5일 처럼 양쪽에 달을 붙입니다. */
export function weekRangeLabel(days: Date[]): string {
  const first = days[0]
  const last = days[days.length - 1]
  return first.getMonth() === last.getMonth()
    ? `${first.getMonth() + 1}월 ${first.getDate()}일 – ${last.getDate()}일`
    : `${first.getMonth() + 1}월 ${first.getDate()}일 – ${last.getMonth() + 1}월 ${last.getDate()}일`
}

// 모듈 로드 시 한 번만 정합니다. 데모 데이터의 offset 이 모두 이 기준입니다.
export const TODAY = startOfDay(new Date())
export const TODAY_ISO = iso(TODAY)
