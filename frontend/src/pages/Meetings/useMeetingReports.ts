import { useCallback, useMemo, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { reportTemplateFromSnapshot } from '@/shared/reports'
import { useReportQuery } from '@/shared/reportQuery'
import type {
  MeetingDealRef,
  MeetingReport,
  PageResponse,
  ReportAttachment,
  ReportResponse,
  ReportTemplate,
  ReportStatus,
  ReportWriteRequest,
} from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import { reviewOf } from './reviewStatus'

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

function textList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((one): one is string => typeof one === 'string') : []
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
  if (code === 'rejected') return '반려'
  return '확정'
}

export function toMeetingReport(item: ReportResponse): MeetingReport {
  const content = record(item.content)
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
    transcript: item.transcript ?? '',
    values: valuesOf(content.values ?? item.content),
    attachments: Array.isArray(content.attachments)
      ? (content.attachments as ReportAttachment[])
      : [],
    salesDealIds: textList(content.sales_deal_ids),
    salesDeals: dealsOf(content.sales_deals),
    evidence: text(content.evidence) || undefined,
    aiValues: valuesOf(content.ai_values),
    aiEvidence: text(content.ai_evidence) || undefined,
    aiGeneratedAt: text(content.ai_generated_at) || undefined,
  }
}

export interface MeetingDraftPayload {
  agendaId: string
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
  /** 이 미팅에 연결한 영업 현황. id 와 이름표를 함께 남깁니다. */
  salesDealIds: string[]
  salesDeals: MeetingDealRef[]
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
      // 에이전트가 content 전체를 프롬프트에 싣습니다. 고른 딜이 그대로 작성 근거가 됩니다.
      sales_deal_ids: draft.salesDealIds,
      sales_deals: draft.salesDeals,
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

/** 그 일정으로 쓴 업무보고서 한 건. 없으면 undefined 입니다. */
export function useMeetingReportOfAgenda(agendaId: string) {
  const { items, loading, error, reload } = useReportQuery(
    agendaId === '' ? null : { report_kind: 'meeting', source_activity_id: agendaId, limit: 1 },
    '업무보고서를 불러오지 못했습니다.',
  )
  // 렌더마다 새 객체를 만들면 이 값을 의존성으로 쓰는 작성 화면의 초기화 effect 가
  // 끝없이 돕니다. 실제로 받아 온 것이 바뀔 때만 새로 만듭니다.
  const report = useMemo(() => (items[0] ? toMeetingReport(items[0]) : undefined), [items])
  return { report, loading, error, reload }
}

export default function useMeetingReports() {
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const save = useCallback(async (draft: MeetingDraftPayload, submit: boolean) => {
    setPending(true)
    setError(null)
    try {
      const existing = await savedForAgenda(draft.agendaId)
      const request = requestOf(draft)
      const { report_kind: _kind, source_activity_id: _source, ...patch } = request
      const saved = existing
        ? await client.patch<ReportResponse>(`/reports/${existing.id}`, patch)
        : await client.post<ReportResponse>('/reports', request)
      // 이미 제출한 보고서를 고쳐 저장하는 길입니다. 그때는 내용만 갈아 끼우고 상태는
      // 그대로 둡니다. 다시 submit 하면 기대 상태가 어긋나 거절당합니다.
      const from = existing?.status_code ?? 'draft'
      const response =
        submit && (from === 'draft' || from === 'rejected')
          ? await client.post<ReportResponse>(`/reports/${saved.data.id}/submit`, {
              expected_status_code: from,
            })
          : saved
      return toMeetingReport(response.data)
    } catch (reason: unknown) {
      setError(
        errorMessage(
          reason,
          submit ? '미팅 기록을 확정하지 못했습니다.' : '임시저장하지 못했습니다.',
        ),
      )
      throw reason
    } finally {
      setPending(false)
    }
  }, [])

  return {
    error,
    pending,
    saveReport: (draft: MeetingDraftPayload) => save(draft, true),
    saveDraft: (draft: MeetingDraftPayload) => save(draft, false),
  }
}
