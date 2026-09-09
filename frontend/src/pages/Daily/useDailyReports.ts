import { useCallback, useMemo, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { finalizeReport, idempotencyAttemptFor, type IdempotencyAttempt } from '@/api/reportAgent'
import { useMeetingReportsOn } from '@/pages/Meetings/useMeetingReports'
import { isAuthorEditableReportStatus, templateFor } from '@/shared/reports'
import { useReportQuery } from '@/shared/reportQuery'
import { getOwnMemberIds, useScopeOwnerIds } from '@/shared/scope'
import type {
  ApiReportKind,
  ApiReportStatus,
  DailyReport,
  ReportActivity,
  ReportKind,
  ReportResponse,
  ReportFinalizeRequest,
  ReportGenerationInput,
  ReportGenerationRequest,
  ReportStatus,
  ReportWriteRequest,
} from '@/types'
import { attachmentPayloadsOf, attachmentsFromPayload } from '@/utils/attachment'
import { iso, parseISO, startOfWeek, TODAY } from '@/utils/date'

import { periodLabelFor, periodRange, periodStart } from './periods'
import { relatedActivities, sourcesFor } from './sources'

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
  return report.ownerMemberId === memberId && isAuthorEditableReportStatus(report.apiStatus)
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
    updatedAt: item.updated_at,
    values: { body: item.body ?? '' },
    activities: relatedActivities(
      kind,
      Array.isArray(content.activities) ? (content.activities as ReportActivity[]) : [],
    ),
    attachments: attachmentsFromPayload(item.attachments ?? []),
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
  /** 구버전 보고서와 복구 입력에 있던 사용자 텍스트를 최종 저장 시 보존합니다. */
  transcript: string
}

export function periodGenerationSeedOf(input: ReportGenerationInput) {
  const content = record(input.content)
  const values = valuesOf(content.values)
  return {
    approver: typeof content.approver === 'string' ? content.approver : '',
    values: { body: values.body ?? '' },
    activities: Array.isArray(content.activities) ? (content.activities as ReportActivity[]) : [],
    attachments: attachmentsFromPayload(input.attachments),
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
    },
    title: periodLabelFor(draft.kind, draft.date),
    body: body.trim() || null,
    common_body: null,
    unassigned_body: null,
    structured_values: {},
    transcript: draft.transcript.trim() || null,
    note: `관련 보고서 ${included.length}건`,
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
    attachments: attachmentPayloadsOf(draft.attachments).map((attachment) => ({
      ...attachment,
      purpose: 'reference',
    })),
    template_snapshot: request.template_snapshot,
    content: request.content,
  }
}

export function periodFinalizeRequestOf(
  draft: DraftPayload,
  idempotencyKey: string,
  agentRunId?: string,
): ReportFinalizeRequest {
  const revisionStatus = isAuthorEditableReportStatus(draft.statusCode)
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
    attachments: attachmentPayloadsOf(draft.attachments),
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

/** 관련 하위 보고서 조회. 월 경계에 걸친 첫 주도 포함합니다. */
export function childReportQuery(kind: ReportKind, dateISO: string) {
  const [from, to] = periodRange(kind, dateISO)
  return {
    report_kind: kind === '월간' ? 'weekly' : 'daily',
    start_date: kind === '월간' ? iso(startOfWeek(parseISO(from))) : from,
    end_date: to,
    status_code: ['submitted', 'approved'],
  }
}

export function useChildReports(kind: ReportKind, dateISO: string, enabled: boolean) {
  const authorIds = useScopeOwnerIds()
  const { items, loading, error, reload } = useReportQuery(
    enabled ? { ...childReportQuery(kind, dateISO), author_member_id: authorIds } : null,
    '관련 보고서를 불러오지 못했습니다.',
    true,
  )
  const reports = useMemo(() => items.map(toReport), [items])
  return { reports, loading, error, reload }
}

/** 작성은 현재 하위 보고서를 생성 후보로, 상세는 같은 목록을 탐색용으로 씁니다. */
export function useRelatedReports(kind: ReportKind, dateISO: string, enabled = true) {
  const meetings = useMeetingReportsOn(dateISO, { enabled: enabled && kind === '일일' })
  const children = useChildReports(kind, dateISO, enabled && kind !== '일일')
  const related = useMemo(
    () => sourcesFor(kind, dateISO, meetings.reports, children.reports),
    [kind, dateISO, meetings.reports, children.reports],
  )
  return {
    ...related,
    loading: meetings.loading || children.loading,
    error: meetings.error ?? children.error,
    reload: () => {
      meetings.reload()
      children.reload()
    },
  }
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
