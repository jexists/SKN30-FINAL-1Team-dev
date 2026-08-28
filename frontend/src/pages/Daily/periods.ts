// 업무 보고의 기간 탭. ?tab= 값과 화면 문구를 한 곳에서 봅니다.
import { ROUTES } from '@/constants/routes'
import type { DailyReport, ReportKind } from '@/types'
import {
  addDays,
  endOfMonth,
  fmtDay,
  fmtMonth,
  iso,
  parseISO,
  startOfMonth,
  startOfWeek,
  weekRangeLabel,
} from '@/utils/date'

export const PERIODS = ['all', 'meeting', 'daily', 'weekly', 'monthly'] as const

export type Period = (typeof PERIODS)[number]

export const PERIOD_LABEL: Record<Period, string> = {
  all: '전체',
  meeting: '업무보고서',
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

/** 업무보고서를 목록에 넣는 탭인지. '전체' 는 둘 다 봅니다. */
export const showsMeetings = (period: Period) => period === 'all' || period === 'meeting'

export function toPeriod(value: string | null): Period {
  return PERIODS.includes(value as Period) ? (value as Period) : 'all'
}

/**
 * 업무보고 목록으로 가는 길. 탭을 주면 그 탭이 열린 채로 갑니다.
 *
 * 어디서 눌렀는지가 어느 탭을 볼지를 정합니다. 미팅 기록에서 왔으면 업무보고서 탭이
 * 열려야 방금 보던 것이 목록 어디에 있는지 바로 보입니다.
 * 'all' 은 기본값이라 주소에 붙이지 않습니다.
 */
export const dailyListPath = (tab?: Period) =>
  tab && tab !== 'all' ? `${ROUTES.DAILY}?tab=${tab}` : ROUTES.DAILY

export function kindToPeriod(kind: ReportKind): Period {
  if (kind === '주간') return 'weekly'
  if (kind === '월간') return 'monthly'
  return 'daily'
}

/**
 * 그 종류가 기간을 세는 단위로 맞춘 기준일. 같은 주·같은 달이면 언제를 찍든 같은 값이
 * 나오므로 이 값이 곧 중복 방지 키입니다. 보고서의 date 도 이 값으로 저장합니다.
 *
 * 주는 일요일에 시작합니다. 화면의 주간 달력과 같은 기준이어야 표시와 저장이 어긋나지 않습니다.
 */
export function periodStart(kind: ReportKind, dateISO: string): string {
  if (kind === '주간') return iso(startOfWeek(parseISO(dateISO)))
  if (kind === '월간') return iso(startOfMonth(parseISO(dateISO)))
  return dateISO
}

/** 기간이 덮는 날짜 범위 [시작, 끝]. 자료를 모을 때 이 범위로 자릅니다. */
export function periodRange(kind: ReportKind, dateISO: string): [string, string] {
  const start = periodStart(kind, dateISO)
  if (kind === '주간') return [start, iso(addDays(parseISO(start), 6))]
  if (kind === '월간') return [start, iso(endOfMonth(parseISO(start)))]
  return [start, start]
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
