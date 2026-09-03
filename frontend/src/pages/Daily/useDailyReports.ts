import { useCallback, useMemo, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { finalizeReport, idempotencyAttemptFor, type IdempotencyAttempt } from '@/api/reportAgent'
import { templateFor } from '@/shared/reports'
import { useReportQuery } from '@/shared/reportQuery'
import { getOwnMemberIds } from '@/shared/scope'
import type {
  ApiReportKind,
  ApiReportStatus,
  DailyReport,
  ReportActivity,
  ReportAttachment,
  ReportKind,
  ReportResponse,
  ReportFinalizeRequest,
  ReportGenerationInput,
  ReportGenerationRequest,
  ReportStatus,
  ReportWriteRequest,
} from '@/types'
import { iso, parseISO, startOfWeek, TODAY } from '@/utils/date'

import { periodLabelFor, periodRange, periodStart } from './periods'

const DAY = 86_400_000
const API_KIND: Record<ReportKind, ApiReportKind> = {
  일일: 'daily',
  주간: 'weekly',
  월간: 'monthly',
}
const KIND_BY_API: Record<Exclude<ApiReportKind, 'meeting'>, ReportKind> = {
  daily: '일일',
  weekly: '주간',
  monthly: '월간',
}
const STATUS_BY_API: Record<ApiReportStatus, ReportStatus> = {
  draft: '작성중',
  submitted: '검토 대기',
  approved: '확정',
  rejected: '반려',
  changes_requested: '반려',
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function valuesOf(value: unknown): Record<string, string> {
  return Object.fromEntries(
    Object.entries(record(value)).filter(
      (entry): entry is [string, string] => typeof entry[1] === 'string',
    ),
  )
}

/** 작성자 본인의 수정 가능한 초안인지 상세와 테스트가 같은 규칙으로 판단합니다. */
export function canEditPeriodReport(report: DailyReport, memberId: string): boolean {
  return (
    report.ownerMemberId === memberId &&
    (report.apiStatus === 'draft' || report.apiStatus === 'changes_requested')
  )
}

function activitiesOf(item: ReportResponse): ReportActivity[] {
  const content = record(item.content)
  if (Array.isArray(content.activities)) return content.activities as ReportActivity[]
  return item.activities.map((activity) => ({
    id: `cal-${activity.activity_id}`,
    source: '캘린더',
    title: activity.title,
    desc: activity.starts_at,
    included: true,
    refId: activity.activity_id,
  }))
}

function attachmentsOf(value: unknown): ReportAttachment[] {
  return Array.isArray(value) ? (value as ReportAttachment[]) : []
}

export function toReport(item: ReportResponse): DailyReport {
  const kind = KIND_BY_API[item.report_kind as Exclude<ApiReportKind, 'meeting'>]
  const content = record(item.content)
  return {
    id: item.id,
    owner: item.author_display_name,
    ownerMemberId: item.author_member_id,
    off: Math.round((parseISO(item.report_date).getTime() - TODAY.getTime()) / DAY),
    date: item.report_date,
    kind,
    period: periodLabelFor(kind, item.report_date),
    template: templateFor(kind),
    approver:
      item.recipient_display_name ??
      (typeof content.approver === 'string' ? content.approver : '결재자 미지정'),
    status: STATUS_BY_API[item.status_code],
    apiStatus: item.status_code,
    version: item.version,
    currentSubmissionId: item.current_submission_id,
    values: { body: item.body ?? '' },
    activities: activitiesOf(item),
    attachments: attachmentsOf(content.attachments),
    transcript: item.transcript ?? '',
    note: item.note ?? '',
    reviewNote: item.review_note ?? '',
  }
}

export interface DraftPayload {
  reportId?: string
  version?: number
  statusCode?: ApiReportStatus
  date: string
  kind: ReportKind
  approver: string
  values: Record<string, string>
  activities: DailyReport['activities']
  attachments: DailyReport['attachments']
  /** 자료에 없는 것을 직접 적은 내용. 에이전트가 자료와 함께 읽습니다. */
  transcript: string
}

export function periodGenerationSeedOf(input: ReportGenerationInput) {
  const content = record(input.content)
  const values = valuesOf(content.values)
  return {
    approver: typeof content.approver === 'string' ? content.approver : '',
    values: { body: values.body ?? '' },
    activities: Array.isArray(content.activities) ? (content.activities as ReportActivity[]) : [],
    attachments: attachmentsOf(content.attachments),
    transcript: input.guidance ?? '',
  }
}

/** 팀장도 작성 화면에서는 팀 전체가 아니라 자신의 같은 기간 보고서만 찾습니다. */
export function ownPeriodReportQuery(kind: ReportKind, dateISO: string) {
  const [from, to] = periodRange(kind, dateISO)
  const authorIds = getOwnMemberIds()
  return {
    report_kind: API_KIND[kind],
    start_date: from,
    end_date: to,
    limit: 1,
    ...(authorIds === undefined ? {} : { author_member_id: authorIds }),
  }
}

export function reportRequestOf(draft: DraftPayload): ReportWriteRequest {
  const [from, to] = periodRange(draft.kind, draft.date)
  const included = draft.activities.filter((activity) => activity.included)
  const body = draft.values.body ?? ''
  return {
    report_kind: API_KIND[draft.kind],
    report_date: periodStart(draft.kind, draft.date),
    period_start: draft.kind === '일일' ? null : from,
    period_end: draft.kind === '일일' ? null : to,
    source_activity_id: null,
    sales_deal_id: null,
    recipient_member_id: null,
    template_snapshot: templateFor(draft.kind),
    content: {
      approver: draft.approver,
      values: { body },
      activities: draft.activities,
      attachments: draft.attachments,
    },
    title: periodLabelFor(draft.kind, draft.date),
    body: body.trim() || null,
    common_body: null,
    unassigned_body: null,
    structured_values: {},
    transcript: draft.transcript.trim() || null,
    note:
      draft.attachments.length > 0
        ? `활동 ${included.length}건 · 첨부 ${draft.attachments.length}건`
        : `활동 ${included.length}건`,
    activity_ids: included
      .filter((activity) => activity.source === '캘린더' && activity.refId)
      .map((activity) => activity.refId as string),
    deal_sections: [],
  }
}

export function periodGenerationRequestOf(
  draft: DraftPayload,
  idempotencyKey: string,
): ReportGenerationRequest {
  const request = reportRequestOf(draft)
  return {
    idempotency_key: idempotencyKey,
    report_kind: request.report_kind,
    report_date: request.report_date,
    ...(request.period_start ? { period_start: request.period_start } : {}),
    ...(request.period_end ? { period_end: request.period_end } : {}),
    template_snapshot: request.template_snapshot,
    content: request.content,
    ...(draft.transcript.trim() ? { guidance: draft.transcript.trim() } : {}),
  }
}

export function periodFinalizeRequestOf(
  draft: DraftPayload,
  idempotencyKey: string,
  agentRunId?: string,
): ReportFinalizeRequest {
  const revisionStatus =
    draft.statusCode === 'draft' || draft.statusCode === 'changes_requested'
      ? draft.statusCode
      : undefined
  if (
    (draft.statusCode === 'changes_requested' || draft.reportId) &&
    (!draft.reportId || !draft.version || !revisionStatus)
  ) {
    throw new Error('report_revision_required')
  }
  return {
    ...reportRequestOf(draft),
    idempotency_key: idempotencyKey,
    ...(agentRunId ? { agent_run_id: agentRunId } : {}),
    ...(draft.reportId && draft.version && revisionStatus
      ? {
          report_id: draft.reportId,
          expected_version: draft.version,
          expected_status_code: revisionStatus,
        }
      : {}),
  }
}

/**
 * 그 기간에 쓴 보고서 한 건. 없으면 undefined 입니다.
 *
 * 이어서 쓸 원본을 찾는 자리들이 씁니다. 기간 안 어느 날짜를 넣어도 같은 기간으로
 * 접히므로 서버가 그 기간 하나만 돌려줍니다.
 */
export function useReportOfPeriod(kind: ReportKind, dateISO: string) {
  const { items, loading, error, reload } = useReportQuery(
    ownPeriodReportQuery(kind, dateISO),
    '업무보고를 불러오지 못했습니다.',
  )
  const report = useMemo(() => (items[0] ? toReport(items[0]) : undefined), [items])
  return { report, loading, error, reload }
}

/**
 * 상위 보고서가 모아 올릴 아래 보고서들. 주간은 그 주의 일일을, 월간은 그 달의 주간을
 * 봅니다. 자리 수가 정해져 있어(한 주 7 칸, 한 달 5 칸 남짓) 한 쪽에 다 들어옵니다.
 */
export function useChildReports(kind: ReportKind, dateISO: string, enabled: boolean) {
  const childKind: ReportKind = kind === '월간' ? '주간' : '일일'
  const [from, to] = periodRange(kind, dateISO)
  // 월간이 걸친 첫 주는 전달에서 시작할 수 있습니다. 그 주의 주간보고서도 이 달 것이라
  // 조회 시작을 주의 첫날까지 당깁니다. 여기서 안 받아 오면 sources 가 세울 수 없습니다.
  const start = kind === '월간' ? iso(startOfWeek(parseISO(from))) : from
  const { items, loading, error, reload } = useReportQuery(
    enabled ? { report_kind: API_KIND[childKind], start_date: start, end_date: to } : null,
    '업무보고를 불러오지 못했습니다.',
  )
  const reports = useMemo(() => items.map(toReport), [items])
  return { reports, loading, error, reload }
}

export default function useDailyReports() {
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const finalizeAttempt = useRef<IdempotencyAttempt | undefined>(undefined)

  const finalize = useCallback(async (draft: DraftPayload, agentRunId?: string) => {
    setPending(true)
    setError(null)
    const attempt = idempotencyAttemptFor(finalizeAttempt.current, { draft, agentRunId })
    finalizeAttempt.current = attempt
    try {
      const response = await finalizeReport(periodFinalizeRequestOf(draft, attempt.key, agentRunId))
      finalizeAttempt.current = undefined
      return toReport(response)
    } catch (reason: unknown) {
      setError(errorMessage(reason, '업무보고를 제출하지 못했습니다.'))
      throw reason
    } finally {
      setPending(false)
    }
  }, [])

  return {
    error,
    pending,
    submitReport: (draft: DraftPayload, agentRunId?: string) => finalize(draft, agentRunId),
  }
}
