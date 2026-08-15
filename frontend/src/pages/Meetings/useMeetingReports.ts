// 백엔드가 붙는 지점은 이 파일 하나입니다. 화면은 아래 반환값만 알면 되므로
// seed 를 API 응답으로, 각 mutator 를 요청으로 바꾸면 나머지는 그대로 둘 수 있습니다.
//
// 상태를 모듈 수준에 두는 이유: 작성(/meetings/new)·상세(/meetings/:id)·일일보고
// 작성 화면이 서로 다른 페이지라 훅 인스턴스가 따로 생깁니다. useState 로 두면
// 여기서 확정한 미팅이 일일보고 활동 내역에 나타나지 않습니다.
import { useCallback, useMemo, useSyncExternalStore } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import { meetingReportHistory } from '@/shared/meetings'
import type { MeetingReport, ReportAttachment, ReportStatus } from '@/types'
import { parseISO, TODAY } from '@/utils/date'

let reports: MeetingReport[] = meetingReportHistory
const listeners = new Set<() => void>()

function publish(next: MeetingReport[]) {
  reports = next
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 일정 하나에 기록은 하나뿐입니다. 다시 쓰면 그 자리를 덮어씁니다. */
function upsert(report: MeetingReport) {
  const rest = reports.filter((r) => r.agendaId !== report.agendaId)
  publish([report, ...rest].sort((a, b) => b.date.localeCompare(a.date)))
}

export interface MeetingDraftPayload {
  agendaId: string
  date: string
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
}

function toReport(draft: MeetingDraftPayload, status: ReportStatus, owner: string): MeetingReport {
  return {
    ...draft,
    // 일정 하나에 기록 하나라 id 를 일정에서 그대로 끌어옵니다.
    id: `mt-${draft.agendaId}`,
    owner,
    // 기록은 실제 날짜로 다루지만 타입은 시드와 공유하므로 off 도 채워 둡니다.
    off: Math.round((parseISO(draft.date).getTime() - TODAY.getTime()) / 86_400_000),
    status,
  }
}

export default function useMeetingReports() {
  const { profile } = useCurrentUser()
  const list = useSyncExternalStore(
    subscribe,
    () => reports,
    () => reports,
  )

  const findReport = useCallback((id: string) => list.find((r) => r.id === id), [list])

  const findByAgenda = useCallback(
    (agendaId: string) => list.find((r) => r.agendaId === agendaId),
    [list],
  )

  // 날짜 → 그날 기록한 미팅 전부. 일일보고가 활동을 모을 때 씁니다.
  const byDate = useMemo(() => {
    const map = new Map<string, MeetingReport[]>()
    for (const report of list) {
      const found = map.get(report.date)
      if (found) found.push(report)
      else map.set(report.date, [report])
    }
    return map
  }, [list])

  /** 확정. 이때부터 일일보고 활동 내역에 실립니다. */
  const saveReport = useCallback(
    (draft: MeetingDraftPayload) => {
      const report = toReport(draft, '확정', profile.name)
      upsert(report)
      return report
    },
    [profile.name],
  )

  const saveDraft = useCallback(
    (draft: MeetingDraftPayload) => {
      upsert(toReport(draft, '작성중', profile.name))
    },
    [profile.name],
  )

  return {
    reports: list,
    byDate,
    findReport,
    findByAgenda,
    saveReport,
    saveDraft,
  }
}
