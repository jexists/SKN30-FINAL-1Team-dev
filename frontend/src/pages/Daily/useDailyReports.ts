import { useCallback, useEffect, useMemo, useState } from 'react'

import { client } from '@/api/client'
import { useScopeOwnerIds } from '@/shared/scope'
import { errorMessage } from '@/api/errorMessage'
import { fallbackDailyReports } from '@/mocks/reports'
import { reportTemplateFromSnapshot } from '@/shared/reports'
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
import { parseISO, TODAY } from '@/utils/date'

import { periodLabelFor, periodRange, periodStart } from './periods'

const PAGE_LIMIT = 100
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

function toReport(item: ReportResponse): DailyReport {
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
    note: item.note ?? '',
  }
}

async function fetchReports(
  signal: AbortSignal,
  authorIds?: readonly string[],
): Promise<ReportResponse[]> {
  const result: ReportResponse[] = []
  let skip = 0
  while (!signal.aborted) {
    const { data } = await client.get<PageResponse<ReportResponse>>('/reports', {
      params: {
        report_kind: ['daily', 'weekly', 'monthly'],
        author_member_id: authorIds,
        skip,
        limit: PAGE_LIMIT,
      },
      signal,
    })
    result.push(...data.items)
    if (!data.has_more || data.next_skip === null) return result
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }
  return result
}

export interface DraftPayload {
  date: string
  kind: ReportKind
  approver: string
  template: ReportTemplate
  values: Record<string, string>
  activities: DailyReport['activities']
  attachments: DailyReport['attachments']
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
    transcript: null,
    note:
      draft.attachments.length > 0
        ? `활동 ${included.length}건 · 첨부 ${draft.attachments.length}건`
        : `활동 ${included.length}건`,
    activity_ids: included
      .filter((activity) => activity.source === '캘린더' && activity.refId)
      .map((activity) => activity.refId as string),
  }
}

export default function useDailyReports() {
  const [reports, setReports] = useState<DailyReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const authorIds = useScopeOwnerIds()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void fetchReports(controller.signal, authorIds)
      .then((items) => {
        if (!controller.signal.aborted) setReports(items.map(toReport))
      })
      // 목록을 못 받아 오면 화면을 에러로 덮지 않고 시연 데이터로 채웁니다.
      // 저장·제출 실패는 아래 save 에서 그대로 알립니다.
      // 이 시연 데이터는 보기 범위를 따르지 않습니다. 원래도 서버 없이 화면을 띄우기
      // 위한 것이라 그대로 둡니다.
      .catch(() => {
        if (!controller.signal.aborted) setReports(fallbackDailyReports)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [reloadKey, authorIds])

  const byDate = useMemo(() => {
    const map = new Map<string, DailyReport[]>()
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
  const findByDate = useCallback(
    (dateISO: string, kind: ReportKind) =>
      byDate.get(dateISO)?.find((report) => report.kind === kind),
    [byDate],
  )
  const findByPeriod = useCallback(
    (kind: ReportKind, dateISO: string) => {
      const key = periodStart(kind, dateISO)
      return reports.find(
        (report) => report.kind === kind && periodStart(report.kind, report.date) === key,
      )
    },
    [reports],
  )

  const save = useCallback(
    async (draft: DraftPayload, submit: boolean) => {
      setPending(true)
      setError(null)
      try {
        const existing = findByPeriod(draft.kind, draft.date)
        const request = requestOf(draft)
        const { report_kind: _kind, source_activity_id: _source, ...patch } = request
        const saved = existing
          ? await client.patch<ReportResponse>(`/reports/${existing.id}`, patch)
          : await client.post<ReportResponse>('/reports', request)
        const response = submit
          ? await client.post<ReportResponse>(`/reports/${saved.data.id}/submit`, {
              expected_status_code: 'draft',
            })
          : saved
        const report = toReport(response.data)
        setReports((current) => [report, ...current.filter((item) => item.id !== report.id)])
        return report
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
    },
    [findByPeriod],
  )

  return {
    reports,
    byDate,
    findReport,
    findByDate,
    findByPeriod,
    loading,
    error,
    pending,
    reload: () => setReloadKey((value) => value + 1),
    submitReport: (draft: DraftPayload) => save(draft, true),
    saveDraft: (draft: DraftPayload) => save(draft, false),
  }
}
