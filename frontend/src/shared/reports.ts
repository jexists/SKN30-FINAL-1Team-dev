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
  id: 'builtin-weekly',
  name: '기본 주간보고 양식',
  owner: '',
  updated: '',
  fields: [
    { id: 'result', label: '주간 성과', type: 'textarea', required: true, aiFilled: true },
    { id: 'plan', label: '다음 주 계획', type: 'textarea', required: true, aiFilled: true },
    { id: 'risk', label: '리스크', type: 'textarea', required: false, aiFilled: true },
  ],
}

export const monthlyTemplate: ReportTemplate = {
  id: 'builtin-monthly',
  name: '기본 월간보고 양식',
  owner: '',
  updated: '',
  fields: [
    { id: 'perf', label: '월간 실적', type: 'textarea', required: true, aiFilled: true },
    { id: 'gap', label: '목표 대비', type: 'textarea', required: true, aiFilled: false },
    { id: 'focus', label: '다음 달 중점', type: 'textarea', required: false, aiFilled: true },
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

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

export function reportTemplateFromSnapshot(
  snapshot: Record<string, unknown>,
  fallbackName: string,
): ReportTemplate {
  const source = asRecord(snapshot)
  const rawFields = Array.isArray(source.fields) ? source.fields : []
  const fields: ReportTemplate['fields'] = rawFields.flatMap((value) => {
    const field = asRecord(value)
    if (typeof field.id !== 'string' || typeof field.label !== 'string') return []
    const type =
      field.type === 'text' || field.type === 'select' || field.type === 'textarea'
        ? field.type
        : 'textarea'
    const options = Array.isArray(field.options)
      ? field.options.filter((option): option is string => typeof option === 'string')
      : undefined
    return [
      {
        id: field.id,
        label: field.label,
        type,
        required: field.required === true,
        aiFilled: field.aiFilled === true,
        placeholder: typeof field.placeholder === 'string' ? field.placeholder : undefined,
        hint: typeof field.hint === 'string' ? field.hint : undefined,
        options,
      },
    ]
  })

  return {
    id: typeof source.id === 'string' ? source.id : 'snapshot',
    name: typeof source.name === 'string' ? source.name : fallbackName,
    owner: typeof source.owner === 'string' ? source.owner : '',
    updated: typeof source.updated === 'string' ? source.updated : '',
    fields,
  }
}
