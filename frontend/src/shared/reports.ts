import type {
  AgentRunResponse,
  ApiReportStatus,
  DailyReport,
  ReportFinalizeRequest,
  ReportGenerationRequest,
  ReportKind,
  ReportTemplate,
} from '@/types'
import { meetingAttachmentPurposeOf } from '@/utils/attachment'
import { addDays, iso, TODAY } from '@/utils/date'

export const APPROVERS: readonly string[] = []

export const REPORT_TEXT_LIMIT = 50_000
export const REPORT_ATTACHMENT_LIMIT = 10
const REPORT_JSON_LIMIT = 256 * 1024

// Pydantic은 Unicode White_Space, content 검사는 Python strip의 C0 공백도 제거합니다.
const reportTrim = (value: string, pythonWhitespace = false) =>
  value.replace(
    pythonWhitespace
      ? // oxlint-disable-next-line no-control-regex -- Python strip()도 이 네 C0 공백을 제거합니다.
        /^[\p{White_Space}\u001c-\u001f]+|[\p{White_Space}\u001c-\u001f]+$/gu
      : /^\p{White_Space}+|\p{White_Space}+$/gu,
    '',
  )

/** 서버와 같이 이모지도 한 글자로 셉니다. 입력값은 바꾸지 않습니다. */
export const reportTextLength = (value: string, pythonWhitespace = false) =>
  [...reportTrim(value, pythonWhitespace)].length

/** 생성·복구·사람이 편집한 최종본 모두 POST 전에 같은 서버 크기 경계를 확인합니다. */
export function reportInputError(
  request: Partial<ReportGenerationRequest> | Partial<ReportFinalizeRequest>,
): string | null {
  const attachments = request.attachments ?? []
  if (attachments.length > REPORT_ATTACHMENT_LIMIT) return 'report_attachment_limit_exceeded'
  if (attachments.some((item) => reportTextLength(item.extract) > REPORT_TEXT_LIMIT))
    return 'report_attachment_text_too_large'
  if (reportTextLength(request.transcript ?? '') > REPORT_TEXT_LIMIT) return 'transcript_too_large'
  if (request.report_kind === 'meeting') {
    const parts = [
      request.transcript ?? '',
      ...attachments
        .filter((item) => meetingAttachmentPurposeOf(item) === 'meeting_source')
        .map((item) => item.extract),
    ]
      .map((value) => reportTrim(value))
      .filter(Boolean)
    if ([...parts.join('\n\n')].length > REPORT_TEXT_LIMIT) return 'meeting_transcript_too_large'
  }
  if ('guidance' in request && reportTextLength(request.guidance ?? '') > 2_000)
    return 'guidance_too_large'

  const write = request as Partial<ReportFinalizeRequest>
  for (const section of [write, ...(write.deal_sections ?? [])]) {
    const values = section.content?.values as Record<string, unknown> | undefined
    const bodies = [section.body]
    if (section === write) bodies.push(write.common_body, write.unassigned_body)
    if (
      bodies.some((body) => typeof body === 'string' && reportTextLength(body) > REPORT_TEXT_LIMIT)
    )
      return 'report_body_too_large'
    if (typeof values?.body === 'string' && reportTextLength(values.body, true) > REPORT_TEXT_LIMIT)
      return 'report_body_too_large'
    if (
      reportTextLength(section.title ?? '') > 254 ||
      (typeof section.content?.title === 'string' &&
        reportTextLength(section.content.title, true) > 254)
    )
      return 'report_title_invalid'
    if (new TextEncoder().encode(JSON.stringify(section.content ?? {})).length > REPORT_JSON_LIMIT)
      return 'content_too_large'
  }
  if (
    new TextEncoder().encode(JSON.stringify(request.template_snapshot ?? {})).length >
    REPORT_JSON_LIMIT
  )
    return 'template_snapshot_too_large'
  // Pydantic가 먼저 정규화하는 첨부 문자열과 같은 값으로 JSON 크기를 셉니다.
  const normalizedAttachments = attachments.map((item) => ({
    ...item,
    name: reportTrim(item.name),
    extract: reportTrim(item.extract),
  }))
  if (new TextEncoder().encode(JSON.stringify(normalizedAttachments)).length > REPORT_JSON_LIMIT)
    return 'attachments_too_large'
  const activities = request.content?.activities
  if (
    Array.isArray(activities) &&
    activities.filter(
      (item) =>
        item?.included === true &&
        ['캘린더', '업무보고서', '일일보고서', '주간보고서'].includes(item.source),
    ).length > 100
  )
    return 'report_source_limit_exceeded'
  return null
}

/** 작성자는 제출 후에도 팀장 승인 전까지 보고서를 고칠 수 있습니다. */
export function isAuthorEditableReportStatus(
  status: ApiReportStatus | undefined,
): status is 'draft' | 'submitted' | 'changes_requested' {
  return status === 'draft' || status === 'submitted' || status === 'changes_requested'
}

export function canRecoverReportGeneration(
  run: Pick<AgentRunResponse, 'created_at' | 'status_code'>,
  savedReport:
    { ownerMemberId: string; apiStatus?: ApiReportStatus; updatedAt?: string } | undefined,
  memberId: string,
): boolean {
  if (!savedReport) return true
  if (!run.created_at || !savedReport.updatedAt) return false
  return (
    savedReport.ownerMemberId === memberId &&
    isAuthorEditableReportStatus(savedReport.apiStatus) &&
    run.status_code !== 'failed' &&
    run.status_code !== 'cancelled' &&
    Date.parse(run.created_at) > Date.parse(savedReport.updatedAt)
  )
}

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
