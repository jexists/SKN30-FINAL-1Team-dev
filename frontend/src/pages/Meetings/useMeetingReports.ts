import { useCallback, useMemo, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { reportTemplateFromSnapshot } from '@/shared/reports'
import { useReportQuery } from '@/shared/reportQuery'
import type {
  MeetingDealSection,
  MeetingDealRef,
  MeetingEvidenceLedger,
  MeetingReport,
  MeetingReportBody,
  PageResponse,
  ReportAttachment,
  ReportResponse,
  ReportTemplate,
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

function valuesOf(value: unknown): Record<string, string> {
  return Object.fromEntries(
    Object.entries(record(value)).filter(
      (entry): entry is [string, string] => typeof entry[1] === 'string',
    ),
  )
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

function bodyOf(value: unknown): MeetingReportBody | null {
  const body = record(value)
  return typeof body.body === 'string' && Array.isArray(body.evidence_ids)
    ? {
        body: body.body,
        evidence_ids: body.evidence_ids.filter((id): id is string => typeof id === 'string'),
        ai_body: typeof body.ai_body === 'string' ? body.ai_body : undefined,
        edited: body.edited === true,
      }
    : null
}

/** 저장 근거는 일부가 손상되어도 배정에 쓰지 않도록 전체를 확인합니다. */
function evidenceOf(value: unknown): MeetingEvidenceLedger | undefined {
  const ledger = record(value)
  if (
    ledger.schema_version !== 'meeting_content.v1' ||
    !/^[a-f0-9]{64}$/.test(text(ledger.transcript_sha256)) ||
    !Array.isArray(ledger.selected_deal_ids) ||
    ledger.selected_deal_ids.length < 1 ||
    ledger.selected_deal_ids.length > 100 ||
    !ledger.selected_deal_ids.every((id) => typeof id === 'string' && id.trim()) ||
    !Array.isArray(ledger.items) ||
    ledger.items.length < 1 ||
    ledger.items.length > 5_000
  )
    return undefined

  const selected = new Set(ledger.selected_deal_ids)
  if (selected.size !== ledger.selected_deal_ids.length) return undefined
  const segmentIds = new Set<string>()
  const scopes = [
    'meeting_context',
    'company_context',
    'all_selected_deals',
    'deal',
    'unresolved',
    'out_of_scope',
  ]
  for (const item of ledger.items) {
    const row = record(item)
    const segment = record(row.segment)
    const applicability = record(row.applicability)
    if (
      !/^S\d{4,6}$/.test(text(segment.segment_id)) ||
      segmentIds.has(text(segment.segment_id)) ||
      typeof segment.start !== 'number' ||
      !Number.isSafeInteger(segment.start) ||
      segment.start < 0 ||
      typeof segment.end !== 'number' ||
      !Number.isSafeInteger(segment.end) ||
      segment.end <= segment.start ||
      !text(segment.text) ||
      !scopes.includes(text(applicability.scope)) ||
      !Array.isArray(applicability.deal_ids) ||
      !applicability.deal_ids.every((id) => typeof id === 'string' && selected.has(id)) ||
      new Set(applicability.deal_ids).size !== applicability.deal_ids.length ||
      (applicability.scope === 'deal'
        ? applicability.deal_ids.length === 0
        : applicability.deal_ids.length !== 0)
    )
      return undefined
    segmentIds.add(text(segment.segment_id))
  }
  return ledger as unknown as MeetingEvidenceLedger
}

function dealSectionOf(
  salesDealId: string,
  dealSnapshot: unknown,
  value: unknown,
  aiEvidence: unknown,
  explicitTitle?: string | null,
  explicitBody?: string | null,
  structuredValues?: Record<string, unknown>,
): MeetingDealSection {
  const content = record(value)
  const analysisEvidence = aiEvidence == null ? null : record(aiEvidence)
  const values = {
    ...valuesOf(content.values ?? content),
    ...valuesOf(structuredValues),
    ...(explicitBody ? { body: explicitBody } : {}),
  }
  return {
    salesDealId,
    salesDeal: dealOf(dealSnapshot, salesDealId),
    product: text(content.product),
    title: explicitTitle || text(content.title),
    values,
    evidence: text(content.evidence) || undefined,
    aiValues: valuesOf(content.ai_values),
    aiEvidence: text(content.ai_evidence) || undefined,
    aiGeneratedAt: text(content.ai_generated_at) || undefined,
    analysisEvidence,
    ...readMeetingAnalysis(analysisEvidence ?? {}),
  }
}

export function toMeetingReport(item: ReportResponse): MeetingReport {
  const content = record(item.content)
  const source = record(item.source_snapshot)
  const shared = record(content.meeting_shared)
  const dealSections = (item.deal_sections ?? []).map((section) =>
    dealSectionOf(
      section.sales_deal_id,
      section.deal_snapshot,
      section.content,
      section.ai_evidence,
      section.title,
      section.body,
      section.structured_values,
    ),
  )
  // 배포 중 기존 딜별 응답도 한 섹션으로 읽습니다. 새 저장은 항상 deal_sections만 씁니다.
  if (dealSections.length === 0 && item.sales_deal_id) {
    dealSections.push(
      dealSectionOf(item.sales_deal_id, content.sales_deal, content, item.ai_evidence),
    )
  }
  return {
    id: item.id,
    owner: item.author_display_name,
    ownerMemberId: item.author_member_id,
    agendaId: item.source_activity_id ?? '',
    off: Math.round((parseISO(item.report_date).getTime() - TODAY.getTime()) / DAY),
    date: item.report_date,
    time: text(content.time),
    template: reportTemplateFromSnapshot(item.template_snapshot, '미팅 보고 양식'),
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
    meetingRunId:
      item.last_applied_agent_run_id ||
      text(source.meeting_run_id) ||
      text(shared.run_id) ||
      undefined,
    meetingShared:
      typeof shared.run_id === 'string'
        ? {
            run_id: shared.run_id,
            revision: text(shared.revision),
            common_report: item.common_body
              ? {
                  ...(bodyOf(shared.common_report) ?? { evidence_ids: [] }),
                  body: item.common_body,
                }
              : bodyOf(shared.common_report),
            unassigned_report: item.unassigned_body
              ? {
                  ...(bodyOf(shared.unassigned_report) ?? { evidence_ids: [] }),
                  body: item.unassigned_body,
                }
              : bodyOf(shared.unassigned_report),
          }
        : undefined,
    evidenceLedger: evidenceOf(source.evidence),
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
  template: ReportTemplate
  time: string
  hospital: string
  dept: string
  contact: string
  place: string
  title: string
  transcript: string
  attachments: ReportAttachment[]
  dealSections: MeetingDealDraftPayload[]
}

/**
 * 이 일정으로 이미 쓴 보고서의 번호. 저장할 때 새로 만들지 고칠지를 이걸로 가릅니다.
 *
 * 목록에서 찾으면 그 보고서가 현재 페이지 밖일 때 못 찾고 같은 일정에 보고서를 하나 더
 * 만듭니다. 서버에 직접 물어야 합니다.
 */
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
    template_snapshot: draft.template,
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
    common_body: null,
    unassigned_body: null,
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
      body: section.values.body?.trim() || null,
      structured_values: Object.fromEntries(
        Object.entries(section.values).filter(([key]) => key !== 'body'),
      ),
      content: {
        product: section.product,
        title: section.title,
        values: section.values,
        evidence: section.evidence ?? null,
      },
    })),
  }
}

async function persistMeetingReport(
  draft: MeetingDraftPayload,
  submit: boolean,
  signal?: AbortSignal,
) {
  const request = meetingRequestOf(draft)
  const {
    report_kind: _kind,
    source_activity_id: _source,
    sales_deal_id: _deal,
    common_body: _commonBody,
    unassigned_body: _unassignedBody,
    ...patch
  } = request
  const saved = draft.reportId
    ? await client.patch<ReportResponse>(
        `/reports/${draft.reportId}`,
        { ...patch, expected_version: draft.version ?? 1 },
        { signal },
      )
    : await client.post<ReportResponse>('/reports', request, { signal })
  // 이미 제출한 보고서를 고쳐 저장하는 길입니다. 그때는 내용만 갈아 끼우고 상태는
  // 그대로 둡니다. 다시 submit 하면 기대 상태가 어긋나 거절당합니다.
  const from = draft.statusCode ?? 'draft'
  const response =
    submit && (from === 'draft' || from === 'changes_requested')
      ? await client.post<ReportResponse>(
          `/reports/${saved.data.id}/submit`,
          { expected_status_code: from, expected_version: saved.data.version },
          { signal },
        )
      : saved
  return toMeetingReport(response.data)
}

/** 페이지가 사라져도 전역 미팅 실행이 사전저장을 끝낼 수 있는 상태 없는 저장 함수입니다. */
export const saveMeetingDraft = (draft: MeetingDraftPayload) => persistMeetingReport(draft, false)

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

  const save = useCallback(
    async (draft: MeetingDraftPayload, submit: boolean, signal?: AbortSignal) => {
      setPendingCount((count) => count + 1)
      setError(null)
      try {
        return await persistMeetingReport(draft, submit, signal)
      } catch (reason: unknown) {
        if (!signal?.aborted) {
          setError(
            errorMessage(
              reason,
              submit ? '미팅 기록을 확정하지 못했습니다.' : '임시저장하지 못했습니다.',
            ),
          )
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
    saveReport: (draft: MeetingDraftPayload, signal?: AbortSignal) => save(draft, true, signal),
    saveDraft: (draft: MeetingDraftPayload, signal?: AbortSignal) => save(draft, false, signal),
  }
}
