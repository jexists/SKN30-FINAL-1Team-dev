// 업무보고 도메인. 양식·시드는 mocks/ 에서 받고 여기서는 로직·파생만 둡니다.
import {
  APPROVERS,
  dailyTemplate,
  extraActivitySeed,
  monthlyTemplate,
  reportSeed,
  weeklyTemplate,
} from '@/mocks'
import type { DailyReport, ReportActivity, ReportKind, ReportTemplate } from '@/types'
import { addDays, iso, parseISO, TODAY } from '@/utils/date'

import { agendaFor } from './agenda'

export { APPROVERS, dailyTemplate, monthlyTemplate, weeklyTemplate }

export function templateFor(kind: ReportKind): ReportTemplate {
  if (kind === '주간') return weeklyTemplate
  if (kind === '월간') return monthlyTemplate
  return dailyTemplate
}

export function draftActivitiesFor(dateISO: string): ReportActivity[] {
  const fromCalendar: ReportActivity[] = agendaFor(dateISO).map((item) => ({
    id: `cal-${item.id}`,
    source: '캘린더',
    title: `${item.time} ${item.hospital} ${item.title}`,
    desc: [item.contact, item.stage].filter(Boolean).join(' · '),
    // 이미 끝난 일정만 기본으로 켭니다. 안 한 일이 보고서에 실리면 안 됩니다.
    included: item.done,
  }))

  // parseISO 로 로컬 자정을 맞춥니다. Date.parse('YYYY-MM-DD') 는 UTC 로 읽어 하루 밀립니다.
  const offset = Math.round((parseISO(dateISO).getTime() - TODAY.getTime()) / 86_400_000)
  const extras = (extraActivitySeed[offset] ?? []).map((item) => ({ ...item, included: true }))

  return [...fromCalendar, ...extras]
}

export const reportHistory: DailyReport[] = reportSeed
  .map((seed) => ({ ...seed, date: iso(addDays(TODAY, seed.off)) }))
  .sort((a, b) => b.date.localeCompare(a.date))

/**
 * 최근 days 일 중 보고서가 없는 평일. 오늘은 아직 마감 전이라 빼고 셉니다.
 * 화면의 "밀린 보고" 줄이 이 값을 그대로 씁니다.
 */
export function missingReportDates(reports: DailyReport[], days = 7): string[] {
  // 주간·월간이 같은 날에 제출돼 있어도 일일보고를 낸 것은 아닙니다.
  const written = new Set(reports.filter((r) => r.kind === '일일').map((r) => r.date))
  const missing: string[] = []

  for (let back = 1; back <= days; back += 1) {
    const day = addDays(TODAY, -back)
    const weekday = day.getDay()
    if (weekday === 0 || weekday === 6) continue
    const key = iso(day)
    if (!written.has(key)) missing.push(key)
  }

  return missing
}
