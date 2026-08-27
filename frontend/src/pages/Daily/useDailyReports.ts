import { useCallback, useMemo, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { reportTemplateFromSnapshot } from '@/shared/reports'
import { useReportQuery } from '@/shared/reportQuery'
import type {
  ApiReportKind,
  ApiReportStatus,
  DailyReport,
  PageResponse,
  ReportActivity,
  ReportAttachment,
  ReportKind,
  ReportResponse,
  ReportTemplate,
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
    off: Math.round((parseISO(item.report_date).getTime() - TODAY.getTime()) / DAY),
    date: item.report_date,
    kind,
    period: periodLabelFor(kind, item.report_date),
    template: reportTemplateFromSnapshot(item.template_snapshot, `${kind} 보고 양식`),
    approver:
      item.recipient_display_name ??
      (typeof content.approver === 'string' ? content.approver : '결재자 미지정'),
    status: STATUS_BY_API[item.status_code],
    values: valuesOf(content.values ?? item.content),
    activities: activitiesOf(item),
    attachments: attachmentsOf(content.attachments),
    transcript: item.transcript ?? '',
    note: item.note ?? '',
  }
}

export interface DraftPayload {
  date: string
  kind: ReportKind
  approver: string
  template: ReportTemplate
  values: Record<string, string>
  activities: DailyReport['activities']
  attachments: DailyReport['attachments']
  /** 자료에 없는 것을 직접 적은 내용. 에이전트가 자료와 함께 읽습니다. */
  transcript: string
}

/**
 * 이 기간에 이미 쓴 보고서의 번호. 저장할 때 새로 만들지 고칠지를 이걸로 가릅니다.
 *
 * 목록에서 찾으면 그 보고서가 현재 페이지 밖일 때 못 찾고 같은 기간에 보고서를 하나 더
 * 만듭니다. 기간 전체를 서버에 물어야 합니다. 기간 안 어느 날짜든 같은 기간으로 접힙니다.
 */
export async function savedIdForPeriod(
  kind: ReportKind,
  dateISO: string,
  signal?: AbortSignal,
): Promise<string | undefined> {
  const [from, to] = periodRange(kind, dateISO)
  const { data } = await client.get<PageResponse<ReportResponse>>('/reports', {
    params: { report_kind: API_KIND[kind], start_date: from, end_date: to, limit: 1 },
    signal,
  })
  return data.items[0]?.id
}

function requestOf(draft: DraftPayload): ReportWriteRequest {
  const [from, to] = periodRange(draft.kind, draft.date)
  const included = draft.activities.filter((activity) => activity.included)
  return {
    report_kind: API_KIND[draft.kind],
    report_date: periodStart(draft.kind, draft.date),
    period_start: draft.kind === '일일' ? null : from,
    period_end: draft.kind === '일일' ? null : to,
    source_activity_id: null,
    recipient_member_id: null,
    template_snapshot: draft.template,
    content: {
      approver: draft.approver,
      values: draft.values,
      activities: draft.activities,
      attachments: draft.attachments,
    },
    transcript: draft.transcript.trim() || null,
    note:
      draft.attachments.length > 0
        ? `활동 ${included.length}건 · 첨부 ${draft.attachments.length}건`
        : `활동 ${included.length}건`,
    activity_ids: included
      .filter((activity) => activity.source === '캘린더' && activity.refId)
      .map((activity) => activity.refId as string),
  }
}

/**
 * 그 기간에 쓴 보고서 한 건. 없으면 undefined 입니다.
 *
 * 이어서 쓸 원본을 찾는 자리들이 씁니다. 기간 안 어느 날짜를 넣어도 같은 기간으로
 * 접히므로 서버가 그 기간 하나만 돌려줍니다.
 */
export function useReportOfPeriod(kind: ReportKind, dateISO: string) {
  const [from, to] = periodRange(kind, dateISO)
  const { items, loading, error, reload } = useReportQuery(
    { report_kind: API_KIND[kind], start_date: from, end_date: to, limit: 1 },
    '업무보고를 불러오지 못했습니다.',
  )
  const report = items[0] ? toReport(items[0]) : undefined
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

  const save = useCallback(async (draft: DraftPayload, submit: boolean) => {
    setPending(true)
    setError(null)
    try {
      const existingId = await savedIdForPeriod(draft.kind, draft.date)
      const request = requestOf(draft)
      const { report_kind: _kind, source_activity_id: _source, ...patch } = request
      const saved = existingId
        ? await client.patch<ReportResponse>(`/reports/${existingId}`, patch)
        : await client.post<ReportResponse>('/reports', request)
      const response = submit
        ? await client.post<ReportResponse>(`/reports/${saved.data.id}/submit`, {
            expected_status_code: 'draft',
          })
        : saved
      return toReport(response.data)
    } catch (reason: unknown) {
      setError(
        errorMessage(
          reason,
          submit ? '업무보고를 제출하지 못했습니다.' : '임시저장하지 못했습니다.',
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
    submitReport: (draft: DraftPayload) => save(draft, true),
    saveDraft: (draft: DraftPayload) => save(draft, false),
  }
}
