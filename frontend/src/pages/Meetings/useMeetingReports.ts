import { useCallback, useMemo, useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage, reportGenerationMessage } from '@/api/errorMessage'
import { finalizeReport, idempotencyAttemptFor, type IdempotencyAttempt } from '@/api/reportAgent'
import { meetingFreeformTemplate } from '@/shared/meetings'
import { canRecoverReportGeneration, isAuthorEditableReportStatus } from '@/shared/reports'
import { useReportQuery } from '@/shared/reportQuery'
import type {
  AgentRunResponse,
  MeetingDealSection,
  MeetingDealRef,
  MeetingReport,
  MeetingReportBody,
  PageResponse,
  ReportAttachment,
  ReportResponse,
  ReportFinalizeRequest,
  ReportGenerationInput,
  ReportGenerationRequest,
  ReportWriteRequest,
  MeetingReportStatus,
} from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import { reviewOf } from './reviewStatus'
import { readMeetingAnalysis } from './generatedDraft'

const DAY = 86_400_000

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/** 저장 당시 딜 이름표. 손상된 이름표도 딜 ID 자체로 구분할 수 있게 복구합니다. */
function dealOf(value: unknown, salesDealId: string): MeetingDealRef {
  const row = record(value)
  return {
    id: typeof row.id === 'string' ? row.id : salesDealId,
    label: typeof row.label === 'string' ? row.label : salesDealId,
    ...(typeof row.note === 'string' ? { note: row.note } : {}),
  }
}

function statusOf(code: ReportResponse['status_code']): MeetingReportStatus {
  if (code === 'draft') return '수정중'
  if (code === 'rejected' || code === 'changes_requested') return '반려'
  return code === 'approved' ? '확정' : '검토 대기'
}

function dealSectionOf(
  salesDealId: string,
  dealSnapshot: unknown,
  value: unknown,
  aiEvidence: unknown,
  explicitTitle?: string | null,
  explicitBody?: string | null,
): MeetingDealSection {
  const content = record(value)
  const analysisEvidence = aiEvidence == null ? null : record(aiEvidence)
  const analysis = readMeetingAnalysis(analysisEvidence ?? {})
  return {
    salesDealId,
    salesDeal: dealOf(dealSnapshot, salesDealId),
    product: text(content.product),
    title: explicitTitle || text(content.title),
    values: { body: explicitBody ?? '' },
    evidence: text(content.evidence) || undefined,
    ...analysis,
    reportError: analysis.reportError ? reportGenerationMessage(analysis.reportError) : undefined,
  }
}

export function toMeetingReport(item: ReportResponse): MeetingReport {
  const content = record(item.content)
  const common: MeetingReportBody | null = item.common_body
    ? { body: item.common_body, evidence_ids: [] }
    : null
  const unassigned: MeetingReportBody | null = item.unassigned_body
    ? { body: item.unassigned_body, evidence_ids: [] }
    : null
  const dealSections = (item.deal_sections ?? []).map((section) =>
    dealSectionOf(
      section.sales_deal_id,
      section.deal_snapshot,
      section.content,
      section.ai_evidence,
      section.title,
      section.body,
    ),
  )
  return {
    id: item.id,
    owner: item.author_display_name,
    ownerMemberId: item.author_member_id,
    agendaId: item.source_activity_id ?? '',
    off: Math.round((parseISO(item.report_date).getTime() - TODAY.getTime()) / DAY),
    date: item.report_date,
    time: text(content.time),
    template: meetingFreeformTemplate,
    hospital: text(content.hospital),
    dept: text(content.dept),
    contact: text(content.contact),
    place: text(content.place),
    title: item.title || text(content.title),
    status: statusOf(item.status_code),
    review: reviewOf(item.status_code, content.on_hold === true),
    apiStatus: item.status_code,
    transcript: item.transcript ?? '',
    attachments: Array.isArray(content.attachments)
      ? (content.attachments as ReportAttachment[])
      : [],
    dealSections,
    version: item.version,
    currentSubmissionId: item.current_submission_id,
    updatedAt: item.updated_at,
    meetingShared:
      common || unassigned ? { common_report: common, unassigned_report: unassigned } : undefined,
  }
}

export interface MeetingDealDraftPayload {
  salesDealId: string
  salesDeal: MeetingDealRef
  product: string
  title: string
  values: Record<string, string>
  evidence?: string
}

export interface MeetingDraftPayload {
  reportId?: string
  version?: number
  statusCode?: ReportResponse['status_code']
  agendaId: string
  date: string
  time: string
  hospital: string
  dept: string
  contact: string
  place: string
  title: string
  transcript: string
  attachments: ReportAttachment[]
  dealSections: MeetingDealDraftPayload[]
  commonBody?: string | null
  unassignedBody?: string | null
}

export function meetingBodyOf(values: Record<string, string>): string {
  return values.body?.trim() || ''
}

export function meetingGenerationSeedOf(input: ReportGenerationInput) {
  const content = record(input.content)
  return {
    salesDealIds: input.sales_deal_ids,
    transcript: input.transcript ?? '',
    attachments: Array.isArray(content.attachments)
      ? (content.attachments as ReportAttachment[])
      : [],
  }
}

export function canRecoverMeetingGeneration(
  run: Pick<AgentRunResponse, 'created_at' | 'generation_input' | 'status_code'>,
  savedReport: MeetingReport | undefined,
  memberId: string,
): boolean {
  if (!savedReport) return true
  if (!canRecoverReportGeneration(run, savedReport, memberId)) return false
  const selectedDealIds = new Set(run.generation_input?.sales_deal_ids ?? [])
  return savedReport.dealSections.every((section) => selectedDealIds.has(section.salesDealId))
}

/** 이 일정에서 사용자가 이미 확정했거나 반려받은 보고서 한 건을 찾습니다. */
export async function savedForAgenda(
  agendaId: string,
  signal?: AbortSignal,
): Promise<ReportResponse | undefined> {
  const { data } = await client.get<PageResponse<ReportResponse>>('/reports', {
    params: { report_kind: 'meeting', source_activity_id: agendaId, limit: 1 },
    signal,
  })
  return data.items[0]
}

export function meetingRequestOf(draft: MeetingDraftPayload): ReportWriteRequest {
  return {
    report_kind: 'meeting',
    report_date: draft.date,
    period_start: null,
    period_end: null,
    source_activity_id: draft.agendaId,
    sales_deal_id: null,
    recipient_member_id: null,
    template_snapshot: meetingFreeformTemplate,
    content: {
      time: draft.time,
      hospital: draft.hospital,
      dept: draft.dept,
      contact: draft.contact,
      place: draft.place,
      title: draft.title,
      attachments: draft.attachments,
    },
    title: draft.title,
    body: null,
    common_body: draft.commonBody?.trim() || null,
    unassigned_body: draft.unassignedBody?.trim() || null,
    structured_values: {},
    transcript: draft.transcript || null,
    note: null,
    // 미팅의 기준 일정은 source_activity_id 한 곳이 진실 원본입니다.
    activity_ids: [],
    deal_sections: draft.dealSections.map((section, position) => ({
      sales_deal_id: section.salesDealId,
      deal_snapshot: section.salesDeal,
      position,
      title: section.title || null,
      body: meetingBodyOf(section.values),
      structured_values: {},
      content: {
        product: section.product,
        title: section.title,
        values: { body: section.values.body ?? '' },
        evidence: section.evidence ?? null,
      },
    })),
  }
}

export function meetingGenerationRequestOf(
  draft: MeetingDraftPayload,
  idempotencyKey: string,
): ReportGenerationRequest {
  const request = meetingRequestOf(draft)
  return {
    idempotency_key: idempotencyKey,
    report_kind: 'meeting',
    report_date: draft.date,
    source_activity_id: draft.agendaId,
    sales_deal_ids: draft.dealSections.map((section) => section.salesDealId),
    template_snapshot: request.template_snapshot,
    content: request.content,
    transcript: draft.transcript,
  }
}

export function meetingFinalizeRequestOf(
  draft: MeetingDraftPayload,
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
    ...meetingRequestOf(draft),
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

interface MeetingReportsOnOptions {
  enabled?: boolean
  /** 일정/대시보드에서 수정중 초안의 '계속 작성' 경로를 보여 줄 때만 켭니다. */
  includeDrafts?: boolean
}

/** 그 날 확정한 업무보고서들. 하루치라 한 쪽에 다 들어옵니다. */
export function useMeetingReportsOn(
  dateISO: string,
  { enabled = true, includeDrafts = false }: MeetingReportsOnOptions = {},
) {
  const { items, loading, error, reload } = useReportQuery(
    enabled
      ? {
          report_kind: 'meeting',
          start_date: dateISO,
          end_date: dateISO,
          ...(includeDrafts
            ? {}
            : { status_code: ['submitted', 'approved', 'rejected', 'changes_requested'] }),
        }
      : null,
    '업무보고서를 불러오지 못했습니다.',
  )
  const reports = useMemo(() => items.map(toMeetingReport), [items])
  return { reports, loading, error, reload }
}

/** 그 일정으로 쓴 업무보고서 한 건. 딜별 내용은 report.dealSections에 있습니다. */
export function useMeetingReportOfAgenda(agendaId: string) {
  const { items, loading, error, reload } = useReportQuery(
    agendaId === '' ? null : { report_kind: 'meeting', source_activity_id: agendaId, limit: 1 },
    '업무보고서를 불러오지 못했습니다.',
  )
  const report = useMemo(() => (items[0] ? toMeetingReport(items[0]) : undefined), [items])
  return { report, loading, error, reload }
}

export default function useMeetingReports() {
  const [error, setError] = useState<string | null>(null)
  const [pendingCount, setPendingCount] = useState(0)
  const finalizeAttempt = useRef<IdempotencyAttempt | undefined>(undefined)

  const finalize = useCallback(
    async (draft: MeetingDraftPayload, agentRunId?: string, signal?: AbortSignal) => {
      setPendingCount((count) => count + 1)
      setError(null)
      const attempt = idempotencyAttemptFor(finalizeAttempt.current, { draft, agentRunId })
      finalizeAttempt.current = attempt
      try {
        const response = await finalizeReport(
          meetingFinalizeRequestOf(draft, attempt.key, agentRunId),
          signal,
        )
        finalizeAttempt.current = undefined
        return toMeetingReport(response)
      } catch (reason: unknown) {
        if (!signal?.aborted) {
          setError(errorMessage(reason, '미팅 보고서 작성을 완료하지 못했습니다.'))
        }
        throw reason
      } finally {
        setPendingCount((count) => count - 1)
      }
    },
    [],
  )

  return {
    error,
    pending: pendingCount > 0,
    finalizeReport: (draft: MeetingDraftPayload, agentRunId?: string, signal?: AbortSignal) =>
      finalize(draft, agentRunId, signal),
  }
}
