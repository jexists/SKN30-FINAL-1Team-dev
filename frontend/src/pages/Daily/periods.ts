// 업무 보고의 기간 탭. ?tab= 값과 화면 문구를 한 곳에서 봅니다.
import type { DailyReport, ReportKind } from '@/types'
import { addDays, fmtDay, fmtMonth, parseISO, startOfWeek, weekRangeLabel } from '@/utils/date'

export const PERIODS = ['all', 'meeting', 'daily', 'weekly', 'monthly'] as const

export type Period = (typeof PERIODS)[number]

export const PERIOD_LABEL: Record<Period, string> = {
  all: '전체',
  meeting: '미팅보고서',
  daily: '일일업무',
  weekly: '주간업무',
  monthly: '월간업무',
}

/**
 * 탭이 보는 업무 보고 종류. 'all' 과 'meeting' 은 여기서 거를 것이 없어 null 입니다.
 * 둘을 가르는 것은 아래 showsDaily·showsMeetings 입니다.
 */
export const PERIOD_KIND: Record<Period, ReportKind | null> = {
  all: null,
  meeting: null,
  daily: '일일',
  weekly: '주간',
  monthly: '월간',
}

/** 업무 보고(일일·주간·월간)를 목록에 넣는 탭인지 */
export const showsDaily = (period: Period) => period !== 'meeting'

/** 미팅보고서를 목록에 넣는 탭인지. '전체' 는 둘 다 봅니다. */
export const showsMeetings = (period: Period) => period === 'all' || period === 'meeting'

export function toPeriod(value: string | null): Period {
  return PERIODS.includes(value as Period) ? (value as Period) : 'all'
}

export function kindToPeriod(kind: ReportKind): Period {
  if (kind === '주간') return 'weekly'
  if (kind === '월간') return 'monthly'
  return 'daily'
}

/**
 * 주간·월간 보고가 덮는 기간 라벨. 일일은 날짜 자체가 기간이라 비워 둡니다.
 * DailyReport.period 를 채우는 자리입니다.
 */
export function periodLabelFor(kind: ReportKind, dateISO: string): string | undefined {
  const date = parseISO(dateISO)
  if (kind === '주간') {
    const first = startOfWeek(date)
    return weekRangeLabel(Array.from({ length: 7 }, (_, i) => addDays(first, i)))
  }
  if (kind === '월간') return fmtMonth(date)
  return undefined
}

/** 이력과 drawer 에 뜨는 제목. 주간·월간은 덮는 기간을, 일일은 그날을 씁니다. */
export function reportTitle(report: DailyReport): string {
  return report.period
    ? `${report.period} ${report.kind}업무보고`
    : `${fmtDay(parseISO(report.date))} 일일업무보고`
}
