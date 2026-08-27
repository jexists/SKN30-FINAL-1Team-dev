// 보고서 종류마다 "무엇을 자료로 쓰는지"를 정하는 곳입니다.
//
// 보고는 아래에서 위로 쌓입니다.
//   일정/업무보고서 → 일일업무보고 → 주간업무보고 → 월간업무보고
// 그래서 일일은 그날 일정과 업무보고서를, 주간은 그 주의 일일보고서를, 월간은
// 그 달의 주간보고서를 모읍니다. 작성 화면은 여기서 나온 목록만 그립니다.
import {
  dailyComposePath,
  dailyReportPath,
  meetingComposePath,
  meetingReportPath,
} from '@/constants/routes'
import type {
  AgendaItem,
  DailyReport,
  MeetingReport,
  ReportActivity,
  ReportKind,
  ReportStatus,
} from '@/types'
import {
  addDays,
  fmtDay,
  iso,
  parseISO,
  startOfWeek,
  TODAY_ISO,
  weekRangeLabel,
} from '@/utils/date'

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

/**
 * 고를 수 없는 자료 한 줄. 아직 안 썼거나 작성중·반려라 집계에 넣을 수 없는 것들입니다.
 * 빈 자리를 감추면 왜 주간보고가 3건뿐인지 알 수 없어 목록 아래에 함께 보여 줍니다.
 */
export interface PendingSource {
  key: string
  title: string
  status: ReportStatus | null
  to: string
  action: string
}

export interface DraftSources {
  /** 체크해서 고르는 자료 */
  activities: ReportActivity[]
  /** activity.id → 원본 상태와 바로가기 */
  meta: Map<string, SourceMeta>
  /** activity.id → 원본 보고서의 입력값. 상위 보고서 초안이 이 값만 씁니다. */
  values: Map<string, Record<string, string>>
  /** 고를 수 없는 자료들 */
  pending: PendingSource[]
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

/** 이 일정에서 갈 곳. 이미 쓴 업무보고서가 있으면 그 보고서로, 없으면 작성 화면으로 갑니다. */
export function meetingLinkFor(agendaId: string, report: MeetingReport | undefined): SourceMeta {
  const status = report?.status ?? null
  const opens = status === '검토 대기' || status === '확정'
  return {
    status,
    tracked: true,
    to: opens && report ? meetingReportPath(report.id) : meetingComposePath(agendaId),
    label: status === null ? '업무보고서 작성' : actionFor(status),
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

  const byAgenda = new Map(meetings.map((report) => [report.agendaId, report]))
  const used = new Set<string>()

  for (const item of agendaItems.filter((entry) => entry.date === dateISO)) {
    const report = byAgenda.get(item.id)

    if (report?.status === '확정') {
      used.add(report.id)
      activities.push({
        id: `meet-${report.id}`,
        source: '업무보고서',
        title: `${report.hospital} ${report.title}`,
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
    meta.set(`cal-${item.id}`, meetingLinkFor(item.id, report))
  }

  // 일정이 지워졌거나 옮겨 간 미팅 기록. 확정한 것은 그날 있었던 일이므로 남깁니다.
  for (const report of meetings) {
    if (report.status !== '확정' || used.has(report.id)) continue
    activities.push({
      id: `meet-${report.id}`,
      source: '업무보고서',
      title: `${report.hospital} ${report.title}`,
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
  }

  return { activities, meta, values, pending: [] }
}

/**
 * 상위 보고서의 자료. 주간은 그 주의 일일보고서를, 월간은 그 달의 주간보고서를 모읍니다.
 *
 * 검토 대기·확정만 고를 수 있습니다. 아직 쓰는 중인 보고서를 위로 올리면 나중에
 * 내용이 바뀌어도 상위 보고서는 그대로 남아 둘이 어긋납니다.
 */
function rollupSources(kind: ReportKind, dateISO: string, reports: DailyReport[]): DraftSources {
  const childKind: ReportKind = kind === '월간' ? '주간' : '일일'
  const source = childKind === '주간' ? '주간보고서' : '일일보고서'
  const [from, to] = periodRange(kind, dateISO)

  // 자리(그 주의 날짜들 / 그 달의 주들)를 먼저 세우고 보고서를 끼웁니다.
  // 비어 있는 자리도 보여야 무엇이 빠졌는지 알 수 있습니다.
  const slots = slotsOf(kind, from, to)
  const keys = new Set(slots.map((slot) => slot.key))

  const found = new Map<string, DailyReport>()
  for (const report of reports) {
    if (report.kind !== childKind) continue
    // 주간보고서는 주의 첫날로 맞춰 봅니다. 주 중 어느 날에 제출했든 그 주의 자리입니다.
    const key = periodStart(childKind, report.date)
    if (!keys.has(key)) continue
    found.set(key, report)
  }

  const activities: ReportActivity[] = []
  const meta = new Map<string, SourceMeta>()
  const values = new Map<string, Record<string, string>>()
  const pending: PendingSource[] = []

  for (const slot of slots) {
    const report = found.get(slot.key)
    const status = report?.status ?? null

    if (report && (ROLLED_UP as readonly ReportStatus[]).includes(report.status)) {
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
      continue
    }

    // 아직 오지 않은 기간은 빈 자리로 셀 것이 아닙니다.
    if (slot.key > TODAY_ISO) continue
    // 주말은 보고 대상이 아닙니다. 쓴 보고서가 있으면 위에서 이미 실었습니다.
    if (slot.weekend) continue

    // 아직 못 고르는 자리는 그 보고서를 마저 쓰러 가는 길만 답니다.
    pending.push({
      key: slot.key,
      title: slot.label,
      status,
      to: dailyComposePath(slot.key, childKind),
      action: actionFor(status),
    })
  }

  return { activities, meta, values, pending }
}

interface Slot {
  key: string
  label: string
  /** 평일이 아닌 자리. 쓴 보고서가 없으면 빈 자리로도 세지 않습니다. */
  weekend?: boolean
}

/** 상위 보고서가 채워야 할 자리. 주간은 하루씩, 월간은 한 주씩입니다. */
function slotsOf(kind: ReportKind, from: string, to: string): Slot[] {
  const slots: Slot[] = []

  if (kind === '주간') {
    for (let day = parseISO(from); iso(day) <= to; day = addDays(day, 1)) {
      const weekend = day.getDay() === 0 || day.getDay() === 6
      slots.push({ key: iso(day), label: fmtDay(day), weekend })
    }
    return slots
  }

  // 월간은 그 달에 걸친 주들입니다. 주의 첫날(일요일)이 곧 주간보고서의 날짜입니다.
  for (let week = startOfWeek(parseISO(from)); iso(week) <= to; week = addDays(week, 7)) {
    slots.push({
      key: iso(week),
      label: weekRangeLabel(Array.from({ length: 7 }, (_, i) => addDays(week, i))),
    })
  }
  return slots
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
