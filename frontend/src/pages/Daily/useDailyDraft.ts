// 작성 화면의 상태를 전부 담습니다. 화면은 배치만 하고 규칙은 여기 있습니다.
//
// 자료를 어디서 모으는지는 종류마다 다릅니다(sources.ts). 일일은 그날 일정과
// 업무보고서를, 주간은 그 주의 일일보고서를, 월간은 그 달의 주간보고서를 씁니다.
//
// 초안은 canonical 보고서를 만들지 않고 AgentRun 후보로 받습니다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { errorMessage } from '@/api/errorMessage'
import {
  createReportGeneration,
  finishIdempotencyAttempt,
  idempotencyAttemptFor,
  isAgentRunTerminalError,
  latestReportGeneration,
  requiresRecoveryConfirmation,
  waitForReportGeneration,
} from '@/api/reportAgent'
import type { IdempotencyAttempt } from '@/api/reportAgent'
import { useAgendaState } from '@/shared/agenda'
import { APPROVERS, templateFor } from '@/shared/reports'
import useAttachments from '@/shared/useAttachments'
import type {
  AgentRunResponse,
  ReportActivity,
  ReportDraftSnapshot,
  ReportGenerationInput,
  ReportKind,
  ReportTemplate,
} from '@/types'
import { useMeetingReportsOn } from '@/pages/Meetings/useMeetingReports'

import { sourcesFor } from './sources'
import { periodRange, periodStart } from './periods'
import {
  periodGenerationSeedOf,
  periodGenerationRequestOf,
  useChildReports,
  useReportOfPeriod,
} from './useDailyReports'

export type DraftPhase = 'idle' | 'generating' | 'ready' | 'submitted'

const emptyValues = (template: ReportTemplate) =>
  Object.fromEntries(template.fields.map((f) => [f.id, '']))

/** 생성 후보는 AI 작성 필드만 바꾸고 사람이 직접 쓰는 필드는 그대로 둡니다. */
export function mergeGeneratedValues(
  template: ReportTemplate,
  previous: Record<string, string>,
  fields: { field_id: string; value: string }[],
) {
  const drafted = Object.fromEntries(fields.map((field) => [field.field_id, field.value]))
  return {
    ...previous,
    ...Object.fromEntries(
      template.fields
        .filter((field) => field.aiFilled)
        .map((field) => [field.id, drafted[field.id] ?? '']),
    ),
  }
}

/** 늦게 도착한 원본에는 현재 선택만 얹습니다. */
export function mergeSourceActivities(
  collected: ReportActivity[],
  previous: ReportActivity[],
  pickId?: string,
) {
  const picked = new Map(previous.map((activity) => [activity.id, activity.included]))
  return collected.map((activity) => ({
    ...activity,
    included:
      picked.get(activity.id) ?? (pickId && activity.refId === pickId ? true : activity.included),
  }))
}

interface DraftOptions {
  /** 미리 켜 둘 자료의 원본 id. 특정 일정에서 넘어올 때 씁니다. */
  pickId?: string
}

function periodInputOf(
  run: AgentRunResponse<ReportDraftSnapshot>,
  kind: ReportKind,
  dateISO: string,
): ReportGenerationInput {
  const input = run.generation_input
  const [from, to] = periodRange(kind, dateISO)
  const expectedKind = kind === '일일' ? 'daily' : kind === '주간' ? 'weekly' : 'monthly'
  const matchesScope =
    input?.report_kind === expectedKind &&
    (kind === '일일'
      ? input.report_date === dateISO
      : input.period_start === from && input.period_end === to)
  if (!input || !matchesScope) throw new Error('report_generation_input_missing')
  return input
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
  } = useMeetingReportsOn(dateISO, { enabled: kind === '일일' })
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

  /** 자료 조회가 갱신돼도 작성 중 선택이 되감기지 않도록 원본 목록만 ref로 받습니다. */
  const live = useRef({ meetings, reports, agendaItems })
  live.current = { meetings, reports, agendaItems }

  const scopeKey = `${kind}:${dateISO}`
  const matchingExisting =
    existing?.kind === kind && periodStart(kind, existing.date) === dateISO ? existing : undefined
  const canonicalSeed = useRef<{ scopeKey: string; report?: typeof existing }>({
    scopeKey,
    report: matchingExisting,
  })
  if (canonicalSeed.current.scopeKey !== scopeKey) {
    canonicalSeed.current = { scopeKey, report: matchingExisting }
  } else if (!canonicalSeed.current.report && matchingExisting) {
    canonicalSeed.current.report = matchingExisting
  }
  const canonical = canonicalSeed.current.report
  const initialTemplate = canonical?.template ?? templateFor(kind)

  const [phase, setPhase] = useState<DraftPhase>('idle')
  const [template, setTemplate] = useState<ReportTemplate>(initialTemplate)
  const [activities, setActivities] = useState<ReportActivity[]>(() => sources.activities)
  /** 자료에 없는 것을 직접 적는 칸. AI 가 이것도 함께 읽습니다. */
  const [transcript, setTranscript] = useState('')
  // 음성에서 뽑은 글은 사람이 쓴 것을 덮지 않습니다. 있으면 아래에 붙입니다.
  const files = useAttachments((text) =>
    setTranscript((prev) => (prev.trim() ? `${prev.trim()}\n\n${text}` : text)),
  )
  const { setAttachments, setAttachmentError } = files
  const [values, setValues] = useState<Record<string, string>>(() => emptyValues(initialTemplate))
  const [approver, setApprover] = useState<string>(APPROVERS[0] ?? '')
  const [aiFilledIds, setAiFilledIds] = useState<ReadonlySet<string>>(new Set())
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(new Set())
  const [generationError, setGenerationError] = useState<string | null>(null)
  const [generationRunId, setGenerationRunId] = useState<string>()
  const generationAbort = useRef<AbortController | null>(null)
  const generationAttempt = useRef<IdempotencyAttempt | undefined>(undefined)
  const sourceSelectionFrozen = useRef(false)
  const recoveryAbort = useRef<AbortController | null>(null)
  const recoveredScope = useRef('')
  const [recovering, setRecovering] = useState(true)
  const [pendingRecovery, setPendingRecovery] =
    useState<AgentRunResponse<ReportDraftSnapshot> | null>(null)

  // 기간이나 종류가 바뀌면 자료를 다시 모으고 처음 상태로 돌아갑니다.
  // 쓰던 내용을 지워도 되는지는 화면이 먼저 묻습니다.
  const reset = useCallback(() => {
    generationAbort.current?.abort()
    recoveryAbort.current?.abort()
    generationAttempt.current = undefined
    // 쓰다 만 보고서의 선택을 그대로 살립니다. 자료 목록은 지금 것을 쓰되
    // 무엇을 골랐는지만 이어받습니다. 그 사이 새로 생긴 자료도 함께 보여야 합니다.
    const saved = canonical
    const nextTemplate = saved?.template ?? templateFor(kind)
    const collected = sourcesFor(
      kind,
      dateISO,
      live.current.meetings,
      live.current.reports,
      live.current.agendaItems,
    )
    sourceSelectionFrozen.current = false
    setActivities(mergeSourceActivities(collected.activities, saved?.activities ?? [], pickId))
    setAttachments(saved?.attachments ?? [])
    setAttachmentError(null)
    setTranscript(saved?.transcript ?? '')
    setTemplate(nextTemplate)
    setValues(saved ? { ...emptyValues(nextTemplate), ...saved.values } : emptyValues(nextTemplate))
    setApprover(saved?.approver ?? APPROVERS[0] ?? '')
    setAiFilledIds(new Set())
    setDirtyIds(new Set())
    setGenerationError(null)
    setGenerationRunId(undefined)
    setPendingRecovery(null)
    setRecovering(true)
    // 이어 쓰는 보고서는 이미 쓴 내용이 있으므로 입력칸을 바로 펴 줍니다.
    setPhase(saved ? 'ready' : 'idle')
  }, [kind, dateISO, pickId, setAttachments, setAttachmentError, canonical])

  useEffect(() => {
    reset()
  }, [reset])

  // 첫 렌더 뒤 도착한 자료만 초기 초안에 보탭니다. 사용자가 선택했거나 생성에 쓴
  // 스냅샷은 이후 조회 결과로 바꾸지 않습니다.
  useEffect(() => {
    if (sourceSelectionFrozen.current) return
    setActivities((previous) => mergeSourceActivities(sources.activities, previous, pickId))
  }, [sources.activities, pickId])

  const toggleActivity = useCallback((id: string) => {
    sourceSelectionFrozen.current = true
    setActivities((prev) => prev.map((a) => (a.id === id ? { ...a, included: !a.included } : a)))
  }, [])

  const setValue = useCallback((id: string, value: string) => {
    setValues((prev) => ({ ...prev, [id]: value }))
    setDirtyIds((prev) => new Set(prev).add(id))
  }, [])

  const included = useMemo(() => activities.filter((a) => a.included), [activities])

  /** AI 가 채우는 항목이 있는 양식에서만 초안 생성이 의미가 있습니다. */
  const hasAiFields = useMemo(() => template.fields.some((f) => f.aiFilled), [template])

  /**
   * 정리할 것이 하나는 있어야 합니다. 고른 자료든, 직접 적은 내용이든, 첨부든
   * 무엇이든 하나입니다 — 자료가 없는 기간이라도 적어서 쓸 수 있어야 합니다.
   */
  const canGenerate =
    !recovering &&
    hasAiFields &&
    (included.length > 0 || transcript.trim().length > 0 || files.attachments.length > 0)

  const generationPayload = useCallback(
    () => ({
      reportId: canonical?.id,
      version: canonical?.version,
      statusCode: canonical?.apiStatus,
      date: dateISO,
      kind,
      approver,
      values,
      activities,
      template,
      attachments: files.attachments,
      transcript,
    }),
    [
      canonical,
      dateISO,
      kind,
      approver,
      values,
      activities,
      template,
      files.attachments,
      transcript,
    ],
  )

  const acceptGeneration = useCallback(
    (
      runId: string,
      fields: { field_id: string; value: string }[],
      candidateTemplate = template,
    ) => {
      const drafted = Object.fromEntries(fields.map((field) => [field.field_id, field.value]))
      setValues((previous) => mergeGeneratedValues(candidateTemplate, previous, fields))
      setAiFilledIds(
        new Set(
          candidateTemplate.fields
            .filter((field) => field.aiFilled && drafted[field.id])
            .map((field) => field.id),
        ),
      )
      setDirtyIds(
        (previous) =>
          new Set(
            [...previous].filter(
              (id) => !candidateTemplate.fields.some((field) => field.id === id && field.aiFilled),
            ),
          ),
      )
      setGenerationRunId(runId)
      setGenerationError(null)
      setPhase('ready')
    },
    [template],
  )

  const restoreGenerationInput = useCallback(
    (input: ReportGenerationInput) => {
      const restored = periodGenerationSeedOf(input)
      sourceSelectionFrozen.current = true
      setTemplate(restored.template)
      setActivities(restored.activities)
      setAttachments(restored.attachments)
      setAttachmentError(null)
      setTranscript(restored.transcript)
      setValues({ ...emptyValues(restored.template), ...restored.values })
      setApprover(restored.approver || APPROVERS[0] || '')
      setAiFilledIds(new Set())
      setDirtyIds(new Set())
      setGenerationRunId(undefined)
      setGenerationError(null)
      setPhase(
        restored.activities.length > 0 ||
          restored.attachments.length > 0 ||
          restored.transcript.trim() ||
          Object.values(restored.values).some((value) => value.trim())
          ? 'ready'
          : 'idle',
      )
      return restored
    },
    [setAttachments, setAttachmentError],
  )

  const resumeGeneration = useCallback(
    async (run: AgentRunResponse<ReportDraftSnapshot>, controller: AbortController) => {
      const input = periodInputOf(run, kind, dateISO)
      const restored = restoreGenerationInput(input)
      try {
        if (run.status_code === 'failed' || run.status_code === 'cancelled') {
          throw new Error(run.error_code ?? run.error_message ?? 'agent_run_failed')
        }
        if (run.status_code === 'queued' || run.status_code === 'running') setPhase('generating')
        const completed = ['queued', 'running'].includes(run.status_code)
          ? await waitForReportGeneration(run, undefined, controller.signal)
          : run
        if (!completed.output_snapshot) throw new Error('agent_run_failed')
        if (!controller.signal.aborted) {
          acceptGeneration(completed.id, completed.output_snapshot.fields, restored.template)
        }
      } catch (reason: unknown) {
        if (!controller.signal.aborted) {
          setGenerationError(errorMessage(reason, '진행 중인 AI 보고서를 복구하지 못했습니다.'))
          setPhase('ready')
        }
      } finally {
        if (recoveryAbort.current === controller) {
          recoveryAbort.current = null
          setRecovering(false)
        }
      }
    },
    [kind, dateISO, restoreGenerationInput, acceptGeneration],
  )
  const resumeGenerationRef = useRef(resumeGeneration)
  resumeGenerationRef.current = resumeGeneration

  const generate = useCallback(async () => {
    if (!canGenerate || generationAbort.current) return
    sourceSelectionFrozen.current = true
    recoveryAbort.current?.abort()
    const controller = new AbortController()
    generationAbort.current = controller
    setPhase('generating')
    setGenerationError(null)
    const payload = generationPayload()
    const attempt = idempotencyAttemptFor(generationAttempt.current, payload)
    generationAttempt.current = attempt

    try {
      const created = await createReportGeneration<ReportDraftSnapshot>(
        periodGenerationRequestOf(payload, attempt.key),
      )
      const completed = await waitForReportGeneration(created, undefined, controller.signal)
      if (!controller.signal.aborted) {
        acceptGeneration(completed.id, completed.output_snapshot.fields)
        generationAttempt.current = finishIdempotencyAttempt(generationAttempt.current, attempt.key)
      }
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        if (isAgentRunTerminalError(reason)) {
          generationAttempt.current = finishIdempotencyAttempt(
            generationAttempt.current,
            attempt.key,
          )
        }
        setGenerationError(errorMessage(reason, 'AI 보고서 초안을 만들지 못했습니다.'))
        setPhase(
          canonical || Object.values(values).some((value) => value.trim()) ? 'ready' : 'idle',
        )
      }
    } finally {
      if (generationAbort.current === controller) generationAbort.current = null
    }
  }, [canGenerate, generationPayload, acceptGeneration, canonical, values])

  useEffect(() => {
    if (existingLoading || recoveredScope.current === scopeKey) return
    if (canonical?.apiStatus === 'submitted' || canonical?.apiStatus === 'approved') {
      setRecovering(false)
      return
    }
    recoveredScope.current = scopeKey
    const controller = new AbortController()
    recoveryAbort.current = controller
    setRecovering(true)
    const [from, to] = periodRange(kind, dateISO)
    const scope =
      kind === '일일'
        ? { report_kind: 'daily' as const, report_date: dateISO }
        : {
            report_kind: kind === '주간' ? ('weekly' as const) : ('monthly' as const),
            period_start: from,
            period_end: to,
          }

    void latestReportGeneration<ReportDraftSnapshot>(scope, controller.signal)
      .then((run) => {
        if (controller.signal.aborted || generationAbort.current) return
        periodInputOf(run, kind, dateISO)
        if (requiresRecoveryConfirmation(canonical?.id)) {
          setPendingRecovery(run)
          if (recoveryAbort.current === controller) {
            recoveryAbort.current = null
            setRecovering(false)
          }
          return
        }
        return resumeGenerationRef.current(run, controller)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted || (isAxiosError(reason) && reason.response?.status === 404))
          return
        setGenerationError(errorMessage(reason, '진행 중인 AI 보고서를 복구하지 못했습니다.'))
      })
      .finally(() => {
        if (recoveryAbort.current === controller) {
          recoveryAbort.current = null
          setRecovering(false)
        }
      })
    return () => controller.abort()
  }, [kind, dateISO, scopeKey, existingLoading, canonical?.id, canonical?.apiStatus])

  useEffect(
    () => () => {
      generationAbort.current?.abort()
      recoveryAbort.current?.abort()
    },
    [],
  )

  /**
   * 제출을 막는 이유들. 버튼 비활성과 안내 문구가 같은 값을 씁니다.
   *
   * 근거가 무엇이든 하나는 있어야 합니다 — canGenerate 와 같은 기준입니다. 자료가
   * 없는 기간을 직접 적어 만들어 놓고 낼 수 없으면 그 화면이 막다른 길이 됩니다.
   */
  const missing = useMemo(() => {
    const reasons: string[] = []
    if (included.length === 0 && transcript.trim() === '' && files.attachments.length === 0) {
      reasons.push('자료 1건 이상')
    }
    for (const field of template.fields) {
      if (field.required && !values[field.id]?.trim()) reasons.push(field.label)
    }
    return reasons
  }, [included, transcript, files.attachments, values, template])

  return {
    phase,
    setPhase,
    template,
    hasAiFields,
    activities,
    /** activity.id → 원본 상태와 바로가기 */
    meta: sources.meta,
    includedCount: included.length,
    toggleActivity,
    transcript,
    setTranscript,
    attachments: files.attachments,
    addAttachments: files.addAttachments,
    removeAttachment: files.removeAttachment,
    attachmentError: files.attachmentError,
    values,
    setValue,
    approver,
    setApprover,
    aiFilledIds,
    dirtyIds,
    canGenerate,
    generate,
    recovering,
    pendingRecovery,
    acceptPendingRecovery: () => {
      if (!pendingRecovery) return
      const run = pendingRecovery
      setPendingRecovery(null)
      const controller = new AbortController()
      recoveryAbort.current = controller
      setRecovering(true)
      void resumeGeneration(run, controller)
    },
    discardPendingRecovery: () => setPendingRecovery(null),
    generationRunId,
    generationError,
    missing,
    reset,
    /** 이 기간에 이미 있는 보고서. 이어 쓰는 중인지 화면이 이 값으로 안내합니다. */
    existing: canonical,
    loading: agendaLoading || meetingLoading || reportLoading || existingLoading,
    error: agendaError ?? meetingError ?? reportError ?? existingError,
    reload: () => {
      recoveredScope.current = ''
      setRecovering(true)
      void reloadAgenda()
      reloadMeetings()
      reloadReports()
      reloadExisting()
    },
  }
}
