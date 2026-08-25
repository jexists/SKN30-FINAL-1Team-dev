import { useCallback, useEffect, useMemo, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { fallbackMeetingReports } from '@/mocks/meetings'
import { reportTemplateFromSnapshot } from '@/shared/reports'
import type {
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

const PAGE_LIMIT = 100
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

function statusOf(code: ReportResponse['status_code']): ReportStatus {
  if (code === 'draft') return '작성중'
  if (code === 'rejected') return '반려'
  return '확정'
}

function toReport(item: ReportResponse): MeetingReport {
  const content = record(item.content)
  return {
    id: item.id,
    owner: item.author_display_name,
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
    evidence: text(content.evidence) || undefined,
    aiValues: valuesOf(content.ai_values),
    aiEvidence: text(content.ai_evidence) || undefined,
    aiGeneratedAt: text(content.ai_generated_at) || undefined,
  }
}

async function fetchReports(signal: AbortSignal): Promise<ReportResponse[]> {
  const result: ReportResponse[] = []
  let skip = 0
  while (!signal.aborted) {
    const { data } = await client.get<PageResponse<ReportResponse>>('/reports', {
      params: { report_kind: 'meeting', skip, limit: PAGE_LIMIT },
      signal,
    })
    result.push(...data.items)
    if (!data.has_more || data.next_skip === null) return result
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }
  return result
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
async function savedForAgenda(agendaId: string): Promise<ReportResponse | undefined> {
  const { data } = await client.get<PageResponse<ReportResponse>>('/reports', {
    params: { report_kind: 'meeting', source_activity_id: agendaId, limit: 1 },
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

export default function useMeetingReports() {
  const [reports, setReports] = useState<MeetingReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void fetchReports(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setReports(items.map(toReport))
      })
      // 목록을 못 받아 오면 화면을 에러로 덮지 않고 시연 데이터로 채웁니다.
      // 저장 실패는 아래 save 에서 그대로 알립니다.
      .catch(() => {
        if (!controller.signal.aborted) setReports(fallbackMeetingReports)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [reloadKey])

  const byDate = useMemo(() => {
    const map = new Map<string, MeetingReport[]>()
    for (const report of reports) {
      const found = map.get(report.date)
      if (found) found.push(report)
      else map.set(report.date, [report])
    }
    return map
  }, [reports])

  const findReport = useCallback(
    (id: string) => reports.find((report) => report.id === id),
    [reports],
  )
  const findByAgenda = useCallback(
    (agendaId: string) => reports.find((report) => report.agendaId === agendaId),
    [reports],
  )

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
      const report = toReport(response.data)
      setReports((current) => [report, ...current.filter((item) => item.id !== report.id)])
      return report
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
    reports,
    byDate,
    findReport,
    findByAgenda,
    loading,
    error,
    pending,
    reload: () => setReloadKey((value) => value + 1),
    saveReport: (draft: MeetingDraftPayload) => save(draft, true),
    saveDraft: (draft: MeetingDraftPayload) => save(draft, false),
  }
}
