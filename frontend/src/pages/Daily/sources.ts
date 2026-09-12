// 기간별 하위 보고서 목록. 생성 시 이 참조로 서버가 제출본을 동결합니다.
import { dailyReportPath, meetingComposePath, meetingReportPath } from '@/constants/routes'
import { meetingStatusLabel, type MeetingStatusLabel } from '@/pages/Meetings/reviewStatus'
import { isAuthorEditableReportStatus } from '@/shared/reports'
import type {
  DailyReport,
  MeetingReport,
  MeetingReportStatus,
  ReportActivity,
  ReportKind,
  ReportStatus,
} from '@/types'
import { iso, parseISO, startOfWeek } from '@/utils/date'

import { periodRange, periodStart, reportTitle } from './periods'

/** 관련 보고서의 상태와 일반 상세/작성 화면 바로가기입니다. */
export interface SourceMeta {
  /** 미팅 원본은 '작성완료'로만 섭니다. 팀장 검토를 받는 문서가 아닙니다. */
  status: ReportStatus | MeetingReportStatus | MeetingStatusLabel | null
  tracked?: boolean
  to?: string
  label?: string
}

export interface DraftSources {
  /** 생성 후보와 상세 탐색에 쓰는 하위 보고서 참조입니다. */
  activities: ReportActivity[]
  meta: Map<string, SourceMeta>
}

/** 관련 목록에 표시하는 기존 제출 상태입니다. */
const ROLLED_UP: readonly ReportStatus[] = ['검토 대기', '확정']

/** 상태별로 원본에서 할 수 있는 일. 미팅 일정과 상위 보고서가 같은 어휘를 씁니다. */
function actionFor(status: SourceMeta['status']): string {
  if (status === null) return '작성'
  if (status === '작성중' || status === '수정중') return '이어서 작성'
  if (status === '검토 대기' || status === '반려') return '수정하기'
  return '보고서 열기'
}

/**
 * 서버 쪽 말 그대로입니다. 화면에 그대로 서지 않습니다 — 미팅 보고서는 팀장 검토를
 * 받지 않으므로 이 값을 보는 쪽이 작성중·작성완료로 접어 씁니다(MeetingPick.filterOf).
 */
function meetingStatus(reports: MeetingReport[]): MeetingReportStatus | null {
  if (reports.length === 0) return null
  if (reports.every((report) => report.status === '확정')) return '확정'
  if (reports.some((report) => report.status === '반려')) return '반려'
  if (reports.some((report) => report.status === '수정중')) return '수정중'
  return '검토 대기'
}

/** 승인 전 보고서는 작성 화면으로, 승인한 미팅 보고서는 단일 상세로 갑니다. */
export function meetingLinkFor(agendaId: string, reports: MeetingReport[] = []): SourceMeta {
  const status = meetingStatus(reports)
  const editable = reports.find((report) => isAuthorEditableReportStatus(report.apiStatus))
  const saved = editable ?? reports[0]
  return {
    status,
    tracked: true,
    to: !saved || editable ? meetingComposePath(agendaId) : meetingReportPath(saved.id),
    label: status === null ? '보고서 작성' : editable ? actionFor(status) : '보고서 열기',
  }
}

/** 일일은 미팅일이 같은 제출된 미팅 보고서만 연결합니다. */
function dailySources(dateISO: string, meetings: MeetingReport[]): DraftSources {
  const activities: ReportActivity[] = []
  const meta = new Map<string, SourceMeta>()
  for (const report of meetings) {
    if (report.date !== dateISO || !['검토 대기', '확정'].includes(report.status)) continue
    const id = `meet-${report.id}`
    activities.push({
      id,
      source: '업무보고서',
      title: report.title,
      desc: [report.hospital, report.owner].filter(Boolean).join(' · '),
      included: true,
      refId: report.id,
      sourceSubmissionId: report.currentSubmissionId ?? undefined,
    })
    meta.set(id, {
      // 위 filter 를 지난 것은 모두 다 쓴 미팅 기록입니다. 검토 어휘 대신 그렇게 세웁니다.
      status: meetingStatusLabel(report.apiStatus ?? 'draft'),
      tracked: true,
      to: meetingReportPath(report.id),
      label: '보고서 열기',
    })
  }
  return { activities, meta }
}

/** 주간은 그 주의 일일, 월간은 그 달에 걸친 주간 보고서를 연결합니다. */
function rollupSources(kind: ReportKind, dateISO: string, reports: DailyReport[]): DraftSources {
  const childKind: ReportKind = kind === '월간' ? '주간' : '일일'
  const source = childKind === '주간' ? '주간보고서' : '일일보고서'
  const [from, to] = periodRange(kind, dateISO)
  const first = kind === '월간' ? iso(startOfWeek(parseISO(from))) : from
  const related = reports
    .filter((report) => {
      const date = periodStart(childKind, report.date)
      return (
        report.kind === childKind &&
        ROLLED_UP.includes(report.status) &&
        date >= first &&
        date <= to
      )
    })
    .sort((a, b) => a.date.localeCompare(b.date))
  const activities: ReportActivity[] = []
  const meta = new Map<string, SourceMeta>()
  for (const report of related) {
    const id = `rep-${report.id}`
    activities.push({
      id,
      source,
      title: reportTitle(report),
      desc: report.owner,
      included: true,
      refId: report.id,
      sourceSubmissionId: report.currentSubmissionId ?? undefined,
    })
    meta.set(id, {
      status: report.status,
      tracked: true,
      to: dailyReportPath(report.id),
      label: '보고서 열기',
    })
  }
  return { activities, meta }
}

/** 일일→미팅, 주간→일일, 월간→주간의 생성 출처와 탐색 링크입니다. */
export function sourcesFor(
  kind: ReportKind,
  dateISO: string,
  meetings: MeetingReport[],
  reports: DailyReport[],
): DraftSources {
  return kind === '일일' ? dailySources(dateISO, meetings) : rollupSources(kind, dateISO, reports)
}

/** 과거 저장 목록에서도 이 기간 종류의 보고서 링크만 표시합니다. */
export function relatedActivities(
  kind: ReportKind,
  activities: ReportActivity[],
): ReportActivity[] {
  const source = kind === '일일' ? '업무보고서' : kind === '주간' ? '일일보고서' : '주간보고서'
  return activities.filter(
    (activity) => activity.included && activity.source === source && activity.refId,
  )
}

/** 관련 보고서의 일반 상세를 엽니다. 생성에 사용한 제출본을 뜻하지 않습니다. */
export function activityLink(activity: ReportActivity): string | null {
  if (!activity.refId) return null
  if (activity.source === '업무보고서') return meetingReportPath(activity.refId)
  if (activity.source === '일일보고서' || activity.source === '주간보고서')
    return dailyReportPath(activity.refId)
  return null
}
