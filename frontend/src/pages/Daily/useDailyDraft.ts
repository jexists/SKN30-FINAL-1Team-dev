// 작성 화면의 상태를 전부 담습니다. 화면은 배치만 하고 규칙은 여기 있습니다.
//
// 자료를 어디서 모으는지는 종류마다 다릅니다(sources.ts). 일일은 그날 일정과
// 업무보고서를, 주간은 그 주의 일일보고서를, 월간은 그 달의 주간보고서를 씁니다.
//
// 초안은 임시저장된 보고서를 백엔드 agent-runs API에 전달해 받습니다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { errorMessage } from '@/api/errorMessage'
import { generateReportDraft } from '@/api/reportAgent'
import { useAgendaState } from '@/shared/agenda'
import { APPROVERS, templateFor } from '@/shared/reports'
import type {
  DailyReport,
  ReportActivity,
  ReportAttachment,
  ReportKind,
  ReportTemplate,
} from '@/types'
import { useMeetingReportsOn } from '@/pages/Meetings/useMeetingReports'

import { sourcesFor } from './sources'
import { useChildReports, useReportOfPeriod } from './useDailyReports'

export type DraftPhase = 'idle' | 'generating' | 'ready' | 'submitted'

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((f) => [f.id, '']))

interface DraftOptions {
  /** 미리 켜 둘 자료의 원본 id. 특정 일정에서 넘어올 때 씁니다. */
  pickId?: string
}

export default function useDailyDraft(
  dateISO: string,
  kind: ReportKind,
  options: DraftOptions = {},
) {
  const { pickId } = options

  const {
    items: agendaItems,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaState(dateISO, dateISO, true)
  // 일일은 그날 업무보고서를, 주간·월간은 아래 기간의 보고서를 자료로 씁니다.
  // 쓰지 않는 쪽은 부르지도 않습니다.
  const {
    reports: meetings,
    loading: meetingLoading,
    error: meetingError,
    reload: reloadMeetings,
  } = useMeetingReportsOn(dateISO, kind === '일일')
  const {
    reports,
    loading: reportLoading,
    error: reportError,
    reload: reloadReports,
  } = useChildReports(kind, dateISO, kind !== '일일')
  // 이 기간에 쓰다 만 보고서. 목록을 뒤지지 않고 그 기간만 서버에 묻습니다.
  const {
    report: existing,
    loading: existingLoading,
    error: existingError,
    reload: reloadExisting,
  } = useReportOfPeriod(kind, dateISO)
  const sources = useMemo(
    () => sourcesFor(kind, dateISO, meetings, reports, agendaItems),
    [kind, dateISO, meetings, reports, agendaItems],
  )

  /**
   * 자료를 다시 모으는 것은 기간·종류가 바뀔 때와 사람이 "초안 다시 불러오기"를
   * 누를 때뿐입니다. 임시저장이 스토어를 건드릴 때마다 목록을 새로 깔면 쓰던 선택이
   * 사라집니다. 그래서 원본 목록은 ref 로만 들고 갑니다.
   */
  const live = useRef({ meetings, reports, agendaItems })
  live.current = { meetings, reports, agendaItems }

  /**
   * 이어 쓸 원본은 기간이 바뀔 때만 다시 읽습니다. 임시저장이 스토어를 건드릴 때마다
   * 다시 읽으면 방금 쓰던 내용이 저장 시점으로 되감깁니다.
   */
  const seedKey = `${kind}:${dateISO}`
  const seed = useRef<{ key: string; report?: DailyReport }>({ key: seedKey, report: existing })
  if (seed.current.key !== seedKey || (!seed.current.report && existing)) {
    seed.current = { key: seedKey, report: existing }
  }
  const template = seed.current.report?.template ?? templateFor(kind)

  const [phase, setPhase] = useState<DraftPhase>('idle')
  const [activities, setActivities] = useState<ReportActivity[]>(() => sources.activities)
  const [attachments, setAttachments] = useState<ReportAttachment[]>([])
  const [values, setValues] = useState<Record<string, string>>(() => emptyValues(template))
  const [approver, setApprover] = useState<string>(APPROVERS[0] ?? '')
  const [aiFilledIds, setAiFilledIds] = useState<ReadonlySet<string>>(new Set())
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(new Set())
  const [generationError, setGenerationError] = useState<string | null>(null)

  // 기간이나 종류가 바뀌면 자료를 다시 모으고 처음 상태로 돌아갑니다.
  // 쓰던 내용을 지워도 되는지는 화면이 먼저 묻습니다.
  const reset = useCallback(() => {
    // 쓰다 만 보고서의 선택을 그대로 살립니다. 자료 목록은 지금 것을 쓰되
    // 무엇을 골랐는지만 이어받습니다. 그 사이 새로 생긴 자료도 함께 보여야 합니다.
    const saved = seed.current.report
    const collected = sourcesFor(
      kind,
      dateISO,
      live.current.meetings,
      live.current.reports,
      live.current.agendaItems,
    )
    const picked = saved && new Map(saved.activities.map((a) => [a.id, a.included]))
    setActivities(
      collected.activities.map((activity) => ({
        ...activity,
        included:
          picked?.get(activity.id) ??
          (pickId && activity.refId === pickId ? true : activity.included),
      })),
    )
    setAttachments(saved?.attachments ?? [])
    setValues(saved ? { ...emptyValues(template), ...saved.values } : emptyValues(template))
    setApprover(saved?.approver ?? APPROVERS[0] ?? '')
    setAiFilledIds(new Set())
    setDirtyIds(new Set())
    setGenerationError(null)
    // 이어 쓰는 보고서는 이미 쓴 내용이 있으므로 입력칸을 바로 펴 줍니다.
    setPhase(saved ? 'ready' : 'idle')
  }, [kind, dateISO, template, pickId])

  useEffect(() => {
    reset()
  }, [reset])

  const toggleActivity = useCallback((id: string) => {
    setActivities((prev) => prev.map((a) => (a.id === id ? { ...a, included: !a.included } : a)))
  }, [])

  const addManual = useCallback((title: string) => {
    setActivities((prev) => [
      ...prev,
      {
        id: `manual-${Date.now()}`,
        source: '수기',
        title,
        desc: '직접 입력한 항목',
        included: true,
      },
    ])
  }, [])

  const removeActivity = useCallback((id: string) => {
    setActivities((prev) => prev.filter((a) => a.id !== id))
  }, [])

  const setValue = useCallback((id: string, value: string) => {
    setValues((prev) => ({ ...prev, [id]: value }))
    setDirtyIds((prev) => new Set(prev).add(id))
  }, [])

  const included = useMemo(() => activities.filter((a) => a.included), [activities])

  /** AI 가 채우는 항목이 있는 양식에서만 초안 생성이 의미가 있습니다. */
  const hasAiFields = useMemo(() => template.fields.some((f) => f.aiFilled), [template])

  /** 자료를 1건이라도 골라야 합니다. 첨부는 조건이 아닙니다. */
  const canGenerate = hasAiFields && included.length > 0

  const generate = useCallback(
    async (reportId: string) => {
      if (!canGenerate) return
      setPhase('generating')
      setGenerationError(null)

      try {
        const drafted = (await generateReportDraft(reportId)).values

        // 사람이 손댄 항목은 덮지 않습니다. 덮어도 되는지는 화면이 먼저 묻습니다.
        setValues((prev) => {
          const next = { ...prev }
          for (const field of template.fields) {
            if (!field.aiFilled) continue
            if (dirtyIds.has(field.id)) continue
            next[field.id] = drafted[field.id] ?? ''
          }
          return next
        })
        setAiFilledIds(
          new Set(
            template.fields
              .filter((f) => f.aiFilled && !dirtyIds.has(f.id) && drafted[f.id])
              .map((f) => f.id),
          ),
        )
        setPhase('ready')
      } catch (reason: unknown) {
        setGenerationError(errorMessage(reason, 'AI 보고서 초안을 만들지 못했습니다.'))
        setPhase('ready')
      }
    },
    [canGenerate, dirtyIds, template],
  )

  /** 제출을 막는 이유들. 버튼 비활성과 안내 문구가 같은 값을 씁니다. */
  const missing = useMemo(() => {
    const reasons: string[] = []
    if (included.length === 0) reasons.push('자료 1건 이상')
    if (approver.trim() === '') reasons.push('보고 대상')
    for (const field of template.fields) {
      if (field.required && !values[field.id]?.trim()) reasons.push(field.label)
    }
    return reasons
  }, [approver, included, values, template])

  return {
    phase,
    setPhase,
    template,
    hasAiFields,
    activities,
    /** activity.id → 원본 상태와 바로가기 */
    meta: sources.meta,
    /** 아직 고를 수 없는 자료들. 목록 아래에 상태로 보여 줍니다. */
    pending: sources.pending,
    includedCount: included.length,
    toggleActivity,
    addManual,
    removeActivity,
    attachments,
    values,
    setValue,
    approver,
    setApprover,
    aiFilledIds,
    dirtyIds,
    canGenerate,
    generate,
    generationError,
    missing,
    reset,
    /** 이 기간에 이미 있는 보고서. 이어 쓰는 중인지 화면이 이 값으로 안내합니다. */
    existing,
    loading: agendaLoading || meetingLoading || reportLoading || existingLoading,
    error: agendaError ?? meetingError ?? reportError ?? existingError,
    reload: () => {
      void reloadAgenda()
      reloadMeetings()
      reloadReports()
      reloadExisting()
    },
  }
}
