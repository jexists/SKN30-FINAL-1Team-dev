import type { DailyReport, ReportKind, ReportTemplate } from '@/types'
import { addDays, iso, TODAY } from '@/utils/date'

export const APPROVERS: readonly string[] = []

export const dailyTemplate: ReportTemplate = {
  id: 'builtin-daily-freeform',
  name: '일일보고서',
  owner: '',
  updated: '',
  fields: [
    {
      id: 'body',
      label: '보고서 본문',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '하루 동안 진행한 업무와 미팅 내용을 자유롭게 작성하세요.',
    },
  ],
}

export const weeklyTemplate: ReportTemplate = {
  id: 'builtin-weekly-freeform',
  name: '주간보고서',
  owner: '',
  updated: '',
  fields: [
    {
      id: 'body',
      label: '보고서 본문',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '한 주 동안의 성과와 다음 계획을 자유롭게 작성하세요.',
    },
  ],
}

export const monthlyTemplate: ReportTemplate = {
  id: 'builtin-monthly-freeform',
  name: '월간보고서',
  owner: '',
  updated: '',
  fields: [
    {
      id: 'body',
      label: '보고서 본문',
      type: 'textarea',
      required: true,
      aiFilled: true,
      placeholder: '한 달 동안의 실적과 다음 계획을 자유롭게 작성하세요.',
    },
  ],
}

export function templateFor(kind: ReportKind): ReportTemplate {
  if (kind === '주간') return weeklyTemplate
  if (kind === '월간') return monthlyTemplate
  return dailyTemplate
}

export function missingReportDates(reports: DailyReport[], days = 7): string[] {
  const written = new Set(
    reports.filter((report) => report.kind === '일일').map((report) => report.date),
  )
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
