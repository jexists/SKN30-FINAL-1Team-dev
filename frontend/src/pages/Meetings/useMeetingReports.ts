import { useCallback, useMemo, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { reportTemplateFromSnapshot } from '@/shared/reports'
import { useReportQuery } from '@/shared/reportQuery'
import type {
  MeetingDealRef,
  MeetingEvidenceLedger,
  MeetingReport,
  MeetingReportBody,
  PageResponse,
  ReportAttachment,
  ReportResponse,
  ReportTemplate,
  ReportStatus,
  ReportWriteRequest,
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

/** 저장해 둔 딜 이름표. 모양이 어긋난 항목은 버립니다. */
function dealsOf(value: unknown): MeetingDealRef[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((one) => {
    const row = record(one)
    if (typeof row.id !== 'string' || typeof row.label !== 'string') return []
    return [
      { id: row.id, label: row.label, ...(typeof row.note === 'string' ? { note: row.note } : {}) },
    ]
  })
}

function statusOf(code: ReportResponse['status_code']): ReportStatus {
  if (code === 'draft') return '작성중'
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

export function toMeetingReport(item: ReportResponse): MeetingReport {
  const content = record(item.content)
  const storedDeals = dealsOf(content.sales_deals)
  const storedDeal = dealsOf([content.sales_deal])[0]
  const salesDealId = item.sales_deal_id
  const source = record(item.source_snapshot)
  const shared = record(content.meeting_shared)
  const analysis = record(item.ai_evidence)
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
    product: text(content.product),
    place: text(content.place),
    title: text(content.title),
    status: statusOf(item.status_code),
    review: reviewOf(item.status_code, content.on_hold === true),
    apiStatus: item.status_code,
    transcript: item.transcript ?? '',
    values: valuesOf(content.values ?? item.content),
    attachments: Array.isArray(content.attachments)
      ? (content.attachments as ReportAttachment[])
      : [],
    salesDealId,
    salesDeal: [storedDeal, ...storedDeals].find((deal) => deal?.id === salesDealId),
    evidence: text(content.evidence) || undefined,
    aiValues: valuesOf(content.ai_values),
    aiEvidence: text(content.ai_evidence) || undefined,
    aiGeneratedAt: text(content.ai_generated_at) || undefined,
    updatedAt: item.updated_at,
    meetingRunId: text(source.meeting_run_id) || text(shared.run_id) || undefined,
    meetingShared:
      typeof shared.run_id === 'string'
        ? {
            run_id: shared.run_id,
            revision: text(shared.revision),
            common_report: bodyOf(shared.common_report),
            unassigned_report: bodyOf(shared.unassigned_report),
          }
        : undefined,
    evidenceLedger: evidenceOf(source.evidence),
    ...readMeetingAnalysis(analysis),
  }
}

export interface MeetingDraftPayload {
  reportId?: string
  statusCode?: ReportResponse['status_code']
  agendaId: string
  salesDealId: string
  salesDeal: MeetingDealRef
  date: string
  template: ReportTemplate
  time: string
  hospital: string
  dept: string
  contact: string
  product: string
  place: string
  title: string
  transcript: string
  values: Record<string, string>
  attachments: ReportAttachment[]
  evidence?: string
  /** AI 원본. 최종본(values)과 나란히 저장해 두 벌을 다 복원합니다. */
  aiValues: Record<string, string>
  aiEvidence?: string
  aiGeneratedAt?: string
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

function requestOf(draft: MeetingDraftPayload): ReportWriteRequest {
  return {
    report_kind: 'meeting',
    report_date: draft.date,
    period_start: null,
    period_end: null,
    source_activity_id: draft.agendaId,
    sales_deal_id: draft.salesDealId,
    recipient_member_id: null,
    template_snapshot: draft.template,
    content: {
      time: draft.time,
      hospital: draft.hospital,
      dept: draft.dept,
      contact: draft.contact,
      product: draft.product,
      place: draft.place,
      title: draft.title,
      values: draft.values,
      attachments: draft.attachments,
      // 작성 당시 이름표도 남깁니다. 정규 관계와 권한 검증은 최상위 sales_deal_id 가 맡습니다.
      sales_deal: draft.salesDeal,
      evidence: draft.evidence ?? null,
      ai_values: draft.aiValues,
      ai_evidence: draft.aiEvidence ?? null,
      ai_generated_at: draft.aiGeneratedAt ?? null,
    },
    transcript: draft.transcript || null,
    note: null,
    activity_ids: [draft.agendaId],
  }
}

/** 그 날 쓴 업무보고서들. 하루치라 한 쪽에 다 들어옵니다. */
export function useMeetingReportsOn(dateISO: string, enabled = true) {
  const { items, loading, error, reload } = useReportQuery(
    enabled ? { report_kind: 'meeting', start_date: dateISO, end_date: dateISO } : null,
    '업무보고서를 불러오지 못했습니다.',
  )
  const reports = useMemo(() => items.map(toMeetingReport), [items])
  return { reports, loading, error, reload }
}

/** 그 일정에서 선택한 딜마다 쓴 업무보고서들입니다. */
export function useMeetingReportsOfAgenda(agendaId: string) {
  const { items, loading, error, reload } = useReportQuery(
    agendaId === '' ? null : { report_kind: 'meeting', source_activity_id: agendaId },
    '업무보고서를 불러오지 못했습니다.',
  )
  const reports = useMemo(() => items.map(toMeetingReport), [items])
  return { reports, loading, error, reload }
}

export default function useMeetingReports() {
  const [error, setError] = useState<string | null>(null)
  const [pendingCount, setPendingCount] = useState(0)

  const save = useCallback(
    async (draft: MeetingDraftPayload, submit: boolean, signal?: AbortSignal) => {
      setPendingCount((count) => count + 1)
      setError(null)
      try {
        const request = requestOf(draft)
        const {
          report_kind: _kind,
          source_activity_id: _source,
          sales_deal_id: _deal,
          ...patch
        } = request
        const saved = draft.reportId
          ? await client.patch<ReportResponse>(`/reports/${draft.reportId}`, patch, { signal })
          : await client.post<ReportResponse>('/reports', request, { signal })
        // 이미 제출한 보고서를 고쳐 저장하는 길입니다. 그때는 내용만 갈아 끼우고 상태는
        // 그대로 둡니다. 다시 submit 하면 기대 상태가 어긋나 거절당합니다.
        const from = draft.statusCode ?? 'draft'
        const response =
          submit && (from === 'draft' || from === 'changes_requested')
            ? await client.post<ReportResponse>(
                `/reports/${saved.data.id}/submit`,
                {
                  expected_status_code: from,
                },
                { signal },
              )
            : saved
        return toMeetingReport(response.data)
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
