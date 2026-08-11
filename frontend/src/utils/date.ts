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
 * 그 달을 덮는 6주 × 7일 = 42칸. 앞뒤 달의 날짜가 앞뒤에 섞여 들어옵니다.
 * 칸 수를 항상 42로 고정해야 달을 넘길 때 그리드 높이가 출렁이지 않습니다.
 */
export function monthMatrix(d: Date): Date[] {
  const first = startOfWeek(startOfMonth(d))
  return Array.from({ length: 42 }, (_, i) => addDays(first, i))
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

// 모듈 로드 시 한 번만 정합니다. 데모 데이터의 offset 이 모두 이 기준입니다.
export const TODAY = startOfDay(new Date())
export const TODAY_ISO = iso(TODAY)
