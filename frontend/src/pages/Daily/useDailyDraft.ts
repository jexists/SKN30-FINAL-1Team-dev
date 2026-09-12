// 기간 보고서 작성 상태. 생성에 쓴 하위 보고서 참조는 최종 제출까지 보존합니다.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { useCurrentUser } from '@/auth/sessionContext'
import { errorMessage, reportGenerationMessage } from '@/api/errorMessage'
import {
  createReportGeneration,
  finishIdempotencyAttempt,
  idempotencyAttemptFor,
  isAgentRunTerminalError,
  latestReportGeneration,
  waitForReportGeneration,
} from '@/api/reportAgent'
import type { IdempotencyAttempt } from '@/api/reportAgent'
import {
  APPROVERS,
  canRecoverReportGeneration,
  reportInputError,
  templateFor,
} from '@/shared/reports'
import useAttachments from '@/shared/useAttachments'
import useAgentRunCancellation from '@/shared/useAgentRunCancellation'
import type {
  AgentRunResponse,
  ReportActivity,
  ReportDraftSnapshot,
  ReportGenerationInput,
  ReportKind,
} from '@/types'
import { attachmentPayloadsOf } from '@/utils/attachment'

import { periodRange, periodStart } from './periods'
import {
  periodGenerationSeedOf,
  periodGenerationRequestOf,
  reportRequestOf,
  useRelatedReports,
  useReportOfPeriod,
} from './useDailyReports'

export type DraftPhase = 'idle' | 'generating' | 'ready' | 'submitted'

/** 기간 보고서 생성 후보는 canonical 본문 한 칸만 받습니다. */
export function mergeGeneratedValues(fields: { field_id: string; value: string }[]) {
  return { body: fields.find((field) => field.field_id === 'body')?.value ?? '' }
}

/** 새 보고서 추가·정렬 변경은 허용하되 선택했던 제출본의 변경·누락은 감지합니다. */
export function generationSourcesAreAvailable(
  frozen: ReportActivity[],
  available: ReportActivity[],
) {
  const key = (activity: ReportActivity) =>
    `${activity.source}:${activity.refId}:${activity.sourceSubmissionId ?? ''}`
  const current = new Set(available.filter((activity) => activity.included).map(key))
  return frozen
    .filter((activity) => activity.included)
    .every((activity) => activity.refId && current.has(key(activity)))
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

export default function useDailyDraft(dateISO: string, kind: ReportKind) {
  const { memberId } = useCurrentUser()
  const related = useRelatedReports(kind, dateISO, true, true)
  // 이 기간에 쓰다 만 보고서. 목록을 뒤지지 않고 그 기간만 서버에 묻습니다.
  const {
    report: existing,
    loading: existingLoading,
    error: existingError,
    reload: reloadExisting,
  } = useReportOfPeriod(kind, dateISO)
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
  const template = templateFor(kind)

  const [phase, setPhase] = useState<DraftPhase>('idle')
  const [frozenActivities, setFrozenActivities] = useState<ReportActivity[] | null>(null)
  const activities = frozenActivities ?? related.activities
  /** 저장된 사용자 메모는 최종 제출 때 보존하고, 입력 중에는 새 생성 지침으로 사용합니다. */
  const [transcript, setTranscript] = useState('')
  const files = useAttachments()
  const {
    addAttachments: addFiles,
    removeAttachment: removeFile,
    setAttachments,
    setAttachmentError,
  } = files
  const [values, setValues] = useState<Record<string, string>>({ body: '' })
  const [approver, setApprover] = useState<string>(APPROVERS[0] ?? '')
  const [aiFilledIds, setAiFilledIds] = useState<ReadonlySet<string>>(new Set())
  const [dirtyIds, setDirtyIds] = useState<ReadonlySet<string>>(new Set())
  const [generationError, setGenerationError] = useState<string | null>(null)
  const [generationRunId, setGenerationRunId] = useState<string>()
  const [activeRunId, setActiveRunId] = useState<string>()
  const [generationEvidence, setGenerationEvidence] = useState<Record<string, unknown> | null>(null)
  const generationAbort = useRef<AbortController | null>(null)
  const generationAttempt = useRef<IdempotencyAttempt | undefined>(undefined)
  const recoveryAbort = useRef<AbortController | null>(null)
  const recoveredScope = useRef('')
  const [recovering, setRecovering] = useState(true)
  const cancelGeneration = useCallback(() => {
    setActiveRunId(undefined)
    setGenerationError(null)
    setPhase((current) => (current === 'generating' ? 'ready' : current))
  }, [])
  const cancellation = useAgentRunCancellation(
    activeRunId,
    () => generationAbort.current?.abort(),
    cancelGeneration,
  )

  const addAttachments = useCallback(
    (picked: FileList | File[]) => {
      generationAbort.current?.abort()
      setGenerationRunId(undefined)
      return addFiles(picked)
    },
    [addFiles],
  )
  const removeAttachment = useCallback(
    (id: string) => {
      generationAbort.current?.abort()
      setGenerationRunId(undefined)
      return removeFile(id)
    },
    [removeFile],
  )
  const changeTranscript = useCallback((value: string) => {
    generationAbort.current?.abort()
    setGenerationRunId(undefined)
    setActiveRunId(undefined)
    setTranscript(value)
  }, [])

  // 기간이나 종류가 바뀌면 자료를 다시 모으고 처음 상태로 돌아갑니다.
  // 쓰던 내용을 지워도 되는지는 화면이 먼저 묻습니다.
  const reset = useCallback(() => {
    generationAbort.current?.abort()
    recoveryAbort.current?.abort()
    generationAttempt.current = undefined
    const saved = canonical
    setFrozenActivities(saved?.activities.map((activity) => ({ ...activity })) ?? null)
    setAttachments(saved?.attachments ?? [])
    setAttachmentError(null)
    setTranscript(saved?.transcript ?? '')
    setValues({ body: saved?.values.body ?? '' })
    setApprover(saved?.approver ?? APPROVERS[0] ?? '')
    setAiFilledIds(new Set())
    setDirtyIds(new Set())
    setGenerationError(null)
    setGenerationRunId(undefined)
    setActiveRunId(undefined)
    setGenerationEvidence(saved?.aiEvidence ?? null)
    setRecovering(true)
    // 이어 쓰는 보고서는 이미 쓴 내용이 있으므로 입력칸을 바로 펴 줍니다.
    setPhase(saved ? 'ready' : 'idle')
  }, [setAttachments, setAttachmentError, canonical])

  useEffect(() => {
    reset()
  }, [reset, scopeKey])

  const setValue = useCallback((id: string, value: string) => {
    setValues((prev) => ({ ...prev, [id]: value }))
    setDirtyIds((prev) => new Set(prev).add(id))
  }, [])

  const hasAiFields = useMemo(() => template.fields.some((field) => field.aiFilled), [template])
  const sourcesReady = !related.loading && !related.error
  const sourceError = !sourcesReady
    ? (related.error ?? '관련 보고서를 불러오는 중입니다.')
    : frozenActivities && !generationSourcesAreAvailable(frozenActivities, related.activities)
      ? '생성에 사용한 하위 보고서의 제출본이 변경되었거나 조회 범위에 없습니다. 범위를 확인하거나 AI 보고서를 다시 작성하세요.'
      : null
  const hasInput =
    related.activities.some((activity) => activity.included) ||
    files.attachments.some(
      (attachment) => attachment.state === 'done' && attachment.extract?.trim(),
    ) ||
    Boolean(transcript.trim()) ||
    Boolean(values.body?.trim())
  const generationPayload = useCallback(
    () => ({
      reportId: canonical?.id,
      version: canonical?.version,
      statusCode: canonical?.apiStatus,
      date: dateISO,
      kind,
      approver,
      values,
      activities: related.activities.map((activity) => ({ ...activity })),
      attachments: files.attachments,
      transcript,
    }),
    [canonical, dateISO, kind, approver, values, related.activities, files.attachments, transcript],
  )

  const inputError = reportInputError(periodGenerationRequestOf(generationPayload(), ''))
  const guidanceError =
    inputError === 'guidance_too_large' ? reportGenerationMessage(inputError) : null
  const submitInputError = reportInputError({
    ...reportRequestOf({ ...generationPayload(), activities }),
    attachments: attachmentPayloadsOf(files.attachments),
    guidance: generationPayload().transcript.trim() || undefined,
  })
  const canGenerate =
    !recovering &&
    !existingLoading &&
    !existingError &&
    sourcesReady &&
    !files.pending &&
    !inputError &&
    hasAiFields &&
    hasInput

  const acceptGeneration = useCallback(
    (
      runId: string,
      fields: { field_id: string; value: string }[],
      evidence: Record<string, unknown> | null,
    ) => {
      const generated = mergeGeneratedValues(fields)
      setValues(generated)
      setAiFilledIds(generated.body ? new Set(['body']) : new Set())
      setDirtyIds(new Set())
      setGenerationRunId(runId)
      setGenerationEvidence(evidence)
      setGenerationError(null)
      setPhase('ready')
    },
    [],
  )

  const restoreGenerationInput = useCallback(
    (input: ReportGenerationInput) => {
      const restored = periodGenerationSeedOf(input)
      setFrozenActivities(restored.activities.map((activity) => ({ ...activity })))
      setAttachments(restored.attachments)
      setAttachmentError(null)
      setTranscript(restored.transcript)
      setValues(restored.values)
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
      restoreGenerationInput(input)
      try {
        if (run.status_code === 'failed' || run.status_code === 'cancelled') {
          throw new Error(run.error_code ?? run.error_message ?? 'agent_run_failed')
        }
        if (run.status_code === 'queued' || run.status_code === 'running') {
          setActiveRunId(run.id)
          setPhase('generating')
        }
        const completed = ['queued', 'running'].includes(run.status_code)
          ? await waitForReportGeneration(run, undefined, controller.signal)
          : run
        if (!completed.output_snapshot) throw new Error('agent_run_failed')
        if (!controller.signal.aborted) {
          acceptGeneration(completed.id, completed.output_snapshot.fields, completed.evidence)
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
    recoveryAbort.current?.abort()
    const controller = new AbortController()
    generationAbort.current = controller
    setPhase('generating')
    setGenerationError(null)
    const previous = generationPayload()
    const payload = {
      ...previous,
      attachments: previous.attachments.map((attachment) => ({
        ...attachment,
        purpose: 'reference' as const,
      })),
    }
    const previousActivities = frozenActivities?.map((activity) => ({ ...activity })) ?? null
    const previousRunId = generationRunId
    setFrozenActivities(payload.activities)
    setAttachments(payload.attachments)
    setActiveRunId(undefined)
    const attempt = idempotencyAttemptFor(generationAttempt.current, payload)
    generationAttempt.current = attempt

    try {
      const created = await createReportGeneration<ReportDraftSnapshot>(
        periodGenerationRequestOf(payload, attempt.key),
      )
      setActiveRunId(created.id)
      const completed = await waitForReportGeneration(created, undefined, controller.signal)
      if (!controller.signal.aborted) {
        acceptGeneration(completed.id, completed.output_snapshot.fields, completed.evidence)
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
        setFrozenActivities(previousActivities)
        setGenerationRunId(previousRunId)
        setGenerationError(errorMessage(reason, 'AI 보고서 초안을 만들지 못했습니다.'))
        setPhase(
          canonical || Object.values(values).some((value) => value.trim()) ? 'ready' : 'idle',
        )
      }
    } finally {
      if (generationAbort.current === controller) {
        generationAbort.current = null
        setActiveRunId(undefined)
      }
    }
  }, [
    canGenerate,
    generationPayload,
    acceptGeneration,
    canonical,
    values,
    setAttachments,
    frozenActivities,
    generationRunId,
  ])

  useEffect(() => {
    if (existingLoading || recoveredScope.current === scopeKey) return
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
        if (!canRecoverReportGeneration(run, canonical, memberId)) return
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
    return () => {
      controller.abort()
      if (recoveryAbort.current === controller) {
        recoveryAbort.current = null
        recoveredScope.current = ''
      }
    }
  }, [kind, dateISO, scopeKey, existingLoading, canonical, memberId])

  useEffect(
    () => () => {
      generationAbort.current?.abort()
      recoveryAbort.current?.abort()
    },
    [],
  )

  /** 제출에는 사람이 확인할 필수 본문이 필요합니다. */
  const missing = useMemo(() => {
    const reasons: string[] = []
    if (sourceError) reasons.push(sourceError)
    if (submitInputError) reasons.push(reportGenerationMessage(submitInputError))
    for (const field of template.fields) {
      if (field.required && !values[field.id]?.trim()) reasons.push(field.label)
    }
    return reasons
  }, [values, template, sourceError, submitInputError])

  return {
    phase,
    setPhase,
    template,
    hasAiFields,
    activities,
    /** 관련 보고서 상태와 바로가기 */
    meta: related.meta,
    transcript,
    setTranscript: changeTranscript,
    guidanceError,
    attachments: files.attachments,
    addAttachments,
    removeAttachment,
    attachmentError: files.attachmentError,
    attachmentsPending: files.pending,
    values,
    setValue,
    approver,
    setApprover,
    aiFilledIds,
    dirtyIds,
    canGenerate,
    generate,
    recovering,
    generationRunId,
    cancelGeneration: cancellation.cancel,
    cancelling: cancellation.cancelling,
    cancelled: cancellation.cancelled,
    cancelError: cancellation.cancelError,
    generationEvidence,
    generationError: inputError ? reportGenerationMessage(inputError) : generationError,
    sourceError,
    missing,
    reset,
    /** 이 기간에 이미 있는 보고서. 이어 쓰는 중인지 화면이 이 값으로 안내합니다. */
    existing: canonical,
    loading: existingLoading,
    relatedLoading: related.loading,
    relatedError: related.error,
    reloadRelated: related.reload,
    error: existingError,
    reload: () => {
      recoveredScope.current = ''
      setRecovering(true)
      reloadExisting()
    },
  }
}
