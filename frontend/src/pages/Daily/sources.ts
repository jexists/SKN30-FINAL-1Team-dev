// 보고서 종류마다 "무엇을 자료로 쓰는지"를 정하는 곳입니다.
//
// 보고는 아래에서 위로 쌓입니다.
//   일정/업무보고서 → 일일업무보고 → 주간업무보고 → 월간업무보고
// 그래서 일일은 그날 일정과 업무보고서를, 주간은 그 주의 일일보고서를, 월간은
// 그 달의 주간보고서를 모읍니다. 작성 화면은 여기서 나온 목록만 그립니다.
import { dailyReportPath, meetingComposePath, meetingReportPath } from '@/constants/routes'
import type {
  AgendaItem,
  DailyReport,
  MeetingReport,
  ReportActivity,
  ReportKind,
  ReportStatus,
} from '@/types'
import { iso, parseISO, startOfWeek } from '@/utils/date'

import { periodRange, periodStart, reportTitle } from './periods'

/** 자료 한 줄에 붙는 원본 상태와 바로가기. 목록이 배지·링크를 그릴 때 씁니다. */
export interface SourceMeta {
  /** 원본 보고서의 상태. null 이면 아직 쓰지 않았습니다. */
  status: ReportStatus | null
  /**
   * 보고서가 따로 나는 자료인지. 문서·후속은 그 자체로 보고서가 없어
   * '미작성' 이라고 말할 것이 없습니다. 배지는 이 값이 참일 때만 답니다.
   */
  tracked?: boolean
  to?: string
  label?: string
}

export interface DraftSources {
  /** 체크해서 고르는 자료 */
  activities: ReportActivity[]
  /** activity.id → 원본 상태와 바로가기 */
  meta: Map<string, SourceMeta>
  /** activity.id → 원본 보고서의 입력값. 상위 보고서 초안이 이 값만 씁니다. */
  values: Map<string, Record<string, string>>
}

/** 집계에 넣을 수 있는 상태. 아직 손보는 중인 보고서를 위로 올리지 않습니다. */
const ROLLED_UP: readonly ReportStatus[] = ['검토 대기', '확정']

/** 상태별로 원본에서 할 수 있는 일. 미팅 일정과 상위 보고서가 같은 어휘를 씁니다. */
function actionFor(status: ReportStatus | null): string {
  if (status === null) return '작성'
  if (status === '작성중') return '이어서 작성'
  if (status === '반려') return '수정하기'
  return '보고서 열기'
}

function meetingStatus(reports: MeetingReport[]): ReportStatus | null {
  if (reports.length === 0) return null
  if (reports.every((report) => report.status === '확정')) return '확정'
  if (reports.some((report) => report.status === '반려')) return '반려'
  if (reports.some((report) => report.status === '작성중')) return '작성중'
  return '검토 대기'
}

/** 일정 하나의 딜별 보고서를 모두 볼 수 있는 작성 화면으로 갑니다. */
export function meetingLinkFor(agendaId: string, reports: MeetingReport[] = []): SourceMeta {
  const status = meetingStatus(reports)
  return {
    status,
    tracked: true,
    to: meetingComposePath(agendaId),
    label: status === null ? '보고서 작성' : actionFor(status),
  }
}

/**
 * 일일보고의 자료. 그날 일정과 그날 확정한 업무보고서입니다.
 *
 * 같은 일정이 두 줄이 되지 않게, 확정된 업무보고서가 있으면 일정 원본 대신
 * 업무보고서를 싣습니다. 기록한 내용이 일정 제목보다 정확합니다.
 */
function dailySources(
  dateISO: string,
  meetings: MeetingReport[],
  agendaItems: AgendaItem[],
): DraftSources {
  const activities: ReportActivity[] = []
  const meta = new Map<string, SourceMeta>()
  const values = new Map<string, Record<string, string>>()

  const byAgenda = new Map<string, MeetingReport[]>()
  for (const report of meetings) {
    const group = byAgenda.get(report.agendaId) ?? []
    group.push(report)
    byAgenda.set(report.agendaId, group)
  }
  const used = new Set<string>()

  for (const item of agendaItems.filter((entry) => entry.date === dateISO)) {
    const reports = byAgenda.get(item.id) ?? []
    const approved = reports.filter((report) => report.status === '확정')

    if (approved.length > 0) {
      for (const report of approved) {
        const id = `meet-${report.id}`
        used.add(report.id)
        activities.push({
          id,
          source: '업무보고서',
          title: [report.hospital, report.salesDeal?.label, report.title]
            .filter(Boolean)
            .join(' · '),
          desc: report.values.decision?.split('\n')[0] || '미팅 기록 확정',
          included: true,
          refId: report.id,
        })
        meta.set(id, {
          status: '확정',
          tracked: true,
          to: meetingReportPath(report.id),
          label: '보고서 열기',
        })
        values.set(id, report.values)
      }
      continue
    }

    activities.push({
      id: `cal-${item.id}`,
      source: '캘린더',
      title: `${item.time} ${item.hospital} ${item.title}`,
      desc: [item.contact, item.stage].filter(Boolean).join(' · '),
      // 이미 끝난 일정만 기본으로 켭니다. 안 한 일이 보고서에 실리면 안 됩니다.
      included: item.done,
      refId: item.id,
    })
    meta.set(`cal-${item.id}`, meetingLinkFor(item.id, reports))
  }

  // 일정이 지워졌거나 옮겨 간 미팅 기록. 확정한 것은 그날 있었던 일이므로 남깁니다.
  for (const report of meetings) {
    if (report.status !== '확정' || used.has(report.id)) continue
    activities.push({
      id: `meet-${report.id}`,
      source: '업무보고서',
      title: [report.hospital, report.salesDeal?.label, report.title].filter(Boolean).join(' · '),
      desc: report.values.decision?.split('\n')[0] || '미팅 기록 확정',
      included: true,
      refId: report.id,
    })
    meta.set(`meet-${report.id}`, {
      status: '확정',
      tracked: true,
      to: meetingReportPath(report.id),
      label: '보고서 열기',
    })
    values.set(`meet-${report.id}`, report.values)
  }

  return { activities, meta, values }
}

/**
 * 상위 보고서의 자료. 주간은 그 주(일→토)의 일일보고서를, 월간은 그 달이 걸친 주들의
 * 주간보고서를 모읍니다.
 *
 * 실제로 쓴 것만 섭니다. 여기서는 고를 것이 없어 — 검토 대기·확정이면 그대로 들어갑니다.
 * 아직 쓰는 중인 보고서를 위로 올리면 나중에 내용이 바뀌어도 상위 보고서는 그대로 남아
 * 둘이 어긋나므로 그것만 걸러 냅니다.
 */
function rollupSources(kind: ReportKind, dateISO: string, reports: DailyReport[]): DraftSources {
  const childKind: ReportKind = kind === '월간' ? '주간' : '일일'
  const source = childKind === '주간' ? '주간보고서' : '일일보고서'
  const [from, to] = periodRange(kind, dateISO)
  // 월간은 그 달이 걸친 주 전부입니다. 1일이 속한 주는 전달에서 시작할 수 있습니다.
  const first = kind === '월간' ? iso(startOfWeek(parseISO(from))) : from

  // 같은 기간에 보고서가 둘이면 한 줄로 접습니다. 기간의 첫날이 곧 그 자리의 이름입니다.
  // 주간보고서는 주 중 어느 날에 제출했든 그 주의 첫날로 맞춰 봅니다.
  const found = new Map<string, DailyReport>()
  for (const report of reports) {
    if (report.kind !== childKind) continue
    if (!(ROLLED_UP as readonly ReportStatus[]).includes(report.status)) continue
    const key = periodStart(childKind, report.date)
    if (key < first || key > to) continue
    found.set(key, report)
  }

  const activities: ReportActivity[] = []
  const meta = new Map<string, SourceMeta>()
  const values = new Map<string, Record<string, string>>()

  // 기간 순으로 세웁니다. 키가 ISO 날짜라 글자 순서가 곧 시간 순서입니다.
  for (const key of [...found.keys()].sort()) {
    const report = found.get(key) as DailyReport
    const id = `rep-${report.id}`
    activities.push({
      id,
      source,
      title: reportTitle(report),
      desc: report.note,
      included: true,
      refId: report.id,
    })
    meta.set(id, {
      status: report.status,
      tracked: true,
      to: dailyReportPath(report.id),
      label: '보고서 열기',
    })
    values.set(id, report.values)
  }

  return { activities, meta, values }
}

/** 이 종류가 무엇을 자료로 쓰는지. 작성 화면은 이 함수 하나만 부릅니다. */
export function sourcesFor(
  kind: ReportKind,
  dateISO: string,
  meetings: MeetingReport[],
  reports: DailyReport[],
  agendaItems: AgendaItem[],
): DraftSources {
  if (kind === '일일') return dailySources(dateISO, meetings, agendaItems)
  return rollupSources(kind, dateISO, reports)
}

/** 제출한 뒤 활동에서 원본으로 되돌아가는 길. 근거를 남기지 못한 활동은 null 입니다. */
export function activityLink(activity: ReportActivity): string | null {
  if (!activity.refId) return null
  if (activity.source === '업무보고서') return meetingReportPath(activity.refId)
  if (activity.source === '일일보고서' || activity.source === '주간보고서')
    return dailyReportPath(activity.refId)
  return null
}
