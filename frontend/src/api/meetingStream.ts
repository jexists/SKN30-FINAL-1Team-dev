import { isAxiosError, isCancel } from 'axios'

import type { AgentRunResponse, MeetingPreview, MeetingProgress } from '@/types'

export const MEETING_WAIT_MS = 25 * 60 * 1_000
const POLL_INTERVAL_MS = 2_000

export class AgentRunTerminalError extends Error {}

function stableSignature(value: unknown): string {
  return JSON.stringify(value, (_key, nested) =>
    nested && typeof nested === 'object' && !Array.isArray(nested)
      ? Object.fromEntries(
          Object.entries(nested).sort(([left], [right]) => left.localeCompare(right)),
        )
      : nested,
  )
}

export function retryableMeetingReportChildId(
  run: {
    generation_input: {
      report_kind?: string
      report_date?: string
      period_start?: string | null
      period_end?: string | null
      source_activity_id: string | null
      transcript: string | null
      sales_deal_ids: string[]
      attachments?: unknown[]
      template_snapshot?: unknown
      content?: unknown
      guidance?: string | null
    } | null
    child_runs?: Array<{
      id: string
      agent_code: string
      status_code: string
    }>
  },
  input: {
    report_kind?: string
    report_date?: string
    period_start?: string | null
    period_end?: string | null
    source_activity_id?: string
    transcript?: string
    sales_deal_ids?: string[]
    attachments?: unknown[]
    template_snapshot?: unknown
    content?: unknown
    guidance?: string | null
  },
): string | null {
  const generationInput = run.generation_input
  if (
    !generationInput ||
    stableSignature({
      report_kind: generationInput.report_kind,
      report_date: generationInput.report_date,
      period_start: generationInput.period_start ?? null,
      period_end: generationInput.period_end ?? null,
      source_activity_id: generationInput.source_activity_id ?? null,
      sales_deal_ids: generationInput.sales_deal_ids ?? [],
      attachments: generationInput.attachments ?? [],
      template_snapshot: generationInput.template_snapshot,
      content: generationInput.content,
      transcript: generationInput.transcript ?? null,
      guidance: generationInput.guidance ?? null,
    }) !==
      stableSignature({
        report_kind: input.report_kind,
        report_date: input.report_date,
        period_start: input.period_start ?? null,
        period_end: input.period_end ?? null,
        source_activity_id: input.source_activity_id ?? null,
        sales_deal_ids: input.sales_deal_ids ?? [],
        attachments: input.attachments ?? [],
        template_snapshot: input.template_snapshot,
        content: input.content,
        transcript: input.transcript ?? null,
        guidance: input.guidance ?? null,
      })
  )
    return null
  return (
    [...(run.child_runs ?? [])]
      .reverse()
      .find(
        (child) =>
          child.agent_code === 'meeting_report_writing' &&
          (child.status_code === 'failed' || child.status_code === 'cancelled'),
      )?.id ?? null
  )
}

export function isAgentRunTerminalError(error: unknown): error is AgentRunTerminalError {
  return error instanceof AgentRunTerminalError
}

export function meetingChildDecision(run: {
  status_code: string
  output_snapshot: unknown
  child_runs?: Array<{
    agent_code: string
    status_code: string
    output_snapshot: unknown
  }>
}): 'legacy' | 'waiting' | 'failed' | 'ready' {
  if (run.status_code === 'failed' || run.status_code === 'cancelled') return 'failed'
  if (run.output_snapshot && typeof run.output_snapshot === 'object') {
    const output = run.output_snapshot as Record<string, unknown>
    if ('reports' in output && 'analyses' in output) return 'legacy'
  }
  const report = [...(run.child_runs ?? [])]
    .reverse()
    .find((child) => child.agent_code === 'meeting_report_writing')
  if (!report || ['queued', 'running'].includes(report.status_code)) return 'waiting'
  if (report.status_code === 'failed' || report.status_code === 'cancelled') return 'failed'
  return report.output_snapshot ? 'ready' : 'failed'
}

/** 연결·서버의 일시 장애만 재조회합니다. 권한/업무 오류와 취소는 즉시 종료합니다. */
export function isRetryableMeetingReadError(error: unknown): boolean {
  if (!isAxiosError(error) || isCancel(error) || error.code === 'ERR_CANCELED') return false
  const status = error.response?.status
  return status === undefined || (status >= 500 && status <= 599)
}

/** SSE도 입력 경계입니다. 다른 실행/깨진 메시지는 화면에 반영하지 않습니다. */
export function readMeetingProgress(value: unknown, runId: string): MeetingProgress | null {
  if (!value || typeof value !== 'object') return null
  const event = value as Partial<MeetingProgress>
  if (
    event.run_id !== runId ||
    !['queued', 'running', 'completed', 'partial', 'failed', 'cancelled'].includes(
      event.status_code ?? '',
    ) ||
    typeof event.stage !== 'string' ||
    !Array.isArray(event.previews)
  )
    return null
  if (
    event.attempt_count !== undefined &&
    (!Number.isInteger(event.attempt_count) || event.attempt_count < 1)
  )
    return null
  if (event.sequence !== undefined && (!Number.isInteger(event.sequence) || event.sequence < 0))
    return null
  const validPreview = (preview: any) =>
    preview &&
    ['deal', 'common', 'unassigned', 'body'].includes(preview.section) &&
    (preview.section === 'deal'
      ? typeof preview.sales_deal_id === 'string'
      : preview.sales_deal_id === null) &&
    typeof preview.body === 'string' &&
    Number.isInteger(preview.revision) &&
    preview.revision >= 0 &&
    (preview.draft_version === undefined || Number.isInteger(preview.draft_version)) &&
    (preview.preview_state === undefined ||
      ['streaming', 'confirmed', 'rollback'].includes(preview.preview_state))
  if (!event.previews.every(validPreview)) return null
  if (
    event.confirmed_previews !== undefined &&
    (!Array.isArray(event.confirmed_previews) || !event.confirmed_previews.every(validPreview))
  )
    return null
  if (
    event.stage_results !== undefined &&
    (!Array.isArray(event.stage_results) ||
      !event.stage_results.every(
        (item: any) =>
          item &&
          ['prepare', 'review_initial', 'content_analysis', 'repair'].includes(item.stage) &&
          typeof item.key === 'string' &&
          typeof item.body === 'string' &&
          (item.preview_state === undefined ||
            ['streaming', 'confirmed'].includes(item.preview_state)),
      ))
  )
    return null
  const counts = event.phase_counts
  if (
    counts !== undefined &&
    (!counts ||
      typeof counts.phase !== 'string' ||
      !Number.isInteger(counts.total) ||
      !Number.isInteger(counts.completed) ||
      !Number.isInteger(counts.failed) ||
      counts.total < 0 ||
      counts.completed < 0 ||
      counts.failed < 0 ||
      counts.completed + counts.failed > counts.total)
  )
    return null
  return {
    run_id: runId,
    ...(typeof event.sequence === 'number' ? { sequence: event.sequence } : {}),
    ...(typeof event.attempt_count === 'number' ? { attempt_count: event.attempt_count } : {}),
    ...(event.recovery_reason === 'original_source_fallback' ||
    event.recovery_reason === 'valid_draft_fallback'
      ? { recovery_reason: event.recovery_reason }
      : {}),
    status_code: event.status_code!,
    stage: event.stage,
    previews: event.previews,
    ...(Array.isArray(event.confirmed_previews)
      ? { confirmed_previews: event.confirmed_previews }
      : {}),
    ...(Array.isArray(event.stage_results) ? { stage_results: event.stage_results } : {}),
    ...(typeof event.report_kind === 'string' ? { report_kind: event.report_kind } : {}),
    ...(counts ? { phase_counts: counts } : {}),
    ...(typeof event.review_attempt === 'number' ? { review_attempt: event.review_attempt } : {}),
    ...(typeof event.review_limit === 'number' ? { review_limit: event.review_limit } : {}),
  }
}

/** body는 토큰 델타가 아닌 전체 문자열입니다. 재작성 revision을 이어 붙이지 않습니다. */
export function mergeMeetingProgress(
  previous: MeetingProgress | null,
  next: MeetingProgress,
): MeetingProgress {
  if (previous && previous.run_id !== next.run_id) return previous
  if (
    previous &&
    next.attempt_count !== undefined &&
    previous.attempt_count !== undefined &&
    next.attempt_count < previous.attempt_count
  )
    return previous
  if (
    previous &&
    next.attempt_count !== undefined &&
    previous.attempt_count !== undefined &&
    next.attempt_count > previous.attempt_count
  ) {
    previous = null
  }
  if (
    previous &&
    next.sequence !== undefined &&
    previous.sequence !== undefined &&
    next.sequence < previous.sequence
  )
    return previous
  const key = (preview: MeetingPreview) => `${preview.section}:${preview.sales_deal_id ?? ''}`
  const old = new Map(previous?.previews.map((preview) => [key(preview), preview]))
  const incoming = new Map(next.previews.map((preview) => [key(preview), preview]))
  const confirmedBefore = new Map(
    previous?.confirmed_previews?.map((preview) => [key(preview), preview]),
  )
  const newer = (candidate: MeetingPreview, existing?: MeetingPreview) =>
    !existing ||
    (candidate.draft_version ?? 0) > (existing.draft_version ?? 0) ||
    ((candidate.draft_version ?? 0) === (existing.draft_version ?? 0) &&
      candidate.revision >= existing.revision)
  const merged = [...old.entries()]
  for (const [previewKey, preview] of incoming) {
    const existing = old.get(previewKey)
    const confirmed = confirmedBefore.get(previewKey)
    if (
      newer(preview, existing) &&
      !(
        confirmed &&
        preview.preview_state === 'streaming' &&
        (preview.draft_version ?? 0) <= (confirmed.draft_version ?? 0)
      )
    ) {
      const index = merged.findIndex(([key]) => key === previewKey)
      if (index >= 0) merged[index] = [previewKey, preview]
      else merged.push([previewKey, preview])
    }
  }
  const confirmed = new Map(confirmedBefore)
  for (const preview of next.confirmed_previews ?? []) {
    const existing = confirmed.get(key(preview))
    if (newer(preview, existing)) confirmed.set(key(preview), preview)
  }
  const stageResults = new Map(previous?.stage_results?.map((item) => [item.key, item]))
  for (const item of next.stage_results ?? []) {
    const existing = stageResults.get(item.key)
    if (!existing || existing.preview_state !== 'confirmed' || item.preview_state === 'confirmed')
      stageResults.set(item.key, item)
  }
  const reportStage = (stage?: string) =>
    stage?.startsWith('report_') || stage === 'report_preparing'
  const retainingReportStage = Boolean(
    previous && reportStage(previous.stage) && !reportStage(next.stage),
  )
  const stage = retainingReportStage ? previous!.stage : next.stage
  return {
    ...next,
    stage,
    ...(retainingReportStage && previous?.sequence !== undefined && next.sequence === undefined
      ? { sequence: previous.sequence }
      : {}),
    ...(retainingReportStage && previous?.report_kind ? { report_kind: previous.report_kind } : {}),
    ...(retainingReportStage && previous?.phase_counts
      ? { phase_counts: previous.phase_counts }
      : {}),
    previews: merged.map(([, preview]) => preview),
    ...(confirmed.size ? { confirmed_previews: [...confirmed.values()] } : {}),
    ...(stageResults.size ? { stage_results: [...stageResults.values()] } : {}),
  }
}

export function restoreConfirmedBody(
  values: Record<string, string>,
  confirmed: MeetingPreview[] | undefined,
): { values: Record<string, string>; adopted: boolean } {
  const body = confirmed?.find(
    (preview) => preview.section === 'body' && preview.preview_state !== 'streaming',
  )?.body
  return body === undefined
    ? { values, adopted: false }
    : { values: { ...values, body }, adopted: true }
}

/** 스트림 실패 시 같은 실행만 GET 합니다. 실행 생성/저장 API는 이 함수에 없습니다. */
export function waitForMeetingRun<T>(
  created: AgentRunResponse<T>,
  options: {
    eventsUrl: string
    readRun: (signal: AbortSignal) => Promise<AgentRunResponse<T>>
    onProgress?: (progress: MeetingProgress) => void
    signal?: AbortSignal
    pollIntervalMs?: number
  },
): Promise<AgentRunResponse<T> & { output_snapshot: T }> {
  return new Promise((resolve, reject) => {
    const controller = new AbortController()
    let stream: EventSource | undefined
    let polling = false
    let settled = false
    let pollTimer: ReturnType<typeof setTimeout> | undefined
    let retryDelay = options.pollIntervalMs ?? POLL_INTERVAL_MS
    let progress: MeetingProgress | null = null
    const timeout = setTimeout(() => finish(new Error('agent_run_timeout')), MEETING_WAIT_MS)

    function cleanup() {
      stream?.close()
      clearTimeout(timeout)
      clearTimeout(pollTimer)
      controller.abort()
      options.signal?.removeEventListener('abort', aborted)
    }
    function finish(error?: unknown, run?: AgentRunResponse<T> & { output_snapshot: T }) {
      if (settled) return
      settled = true
      cleanup()
      if (run) resolve(run)
      else reject(error)
    }
    function aborted() {
      finish(new DOMException('화면을 떠나 대기를 종료했습니다.', 'AbortError'))
    }
    function terminal(run: AgentRunResponse<T>): boolean {
      if (run.id !== created.id) return false
      if (run.status_code === 'failed' || run.status_code === 'cancelled') {
        finish(new AgentRunTerminalError(run.error_code ?? run.error_message ?? 'agent_run_failed'))
        return true
      }
      if (run.status_code === 'completed' || run.status_code === 'partial') {
        if (run.output_snapshot) finish(undefined, { ...run, output_snapshot: run.output_snapshot })
        else finish(new AgentRunTerminalError('agent_run_failed'))
        return true
      }
      return false
    }
    async function poll() {
      if (settled) return
      try {
        const run = await options.readRun(controller.signal)
        if (settled || terminal(run)) return
        retryDelay = options.pollIntervalMs ?? POLL_INTERVAL_MS
        pollTimer = setTimeout(() => void poll(), options.pollIntervalMs ?? POLL_INTERVAL_MS)
      } catch (error) {
        if (settled) return
        if (!controller.signal.aborted && isRetryableMeetingReadError(error)) {
          pollTimer = setTimeout(() => void poll(), retryDelay)
          retryDelay = Math.min(retryDelay * 2, 10_000)
        } else finish(error)
      }
    }
    function fallback() {
      if (settled || polling) return
      polling = true
      stream?.close()
      void poll()
    }

    if (options.signal?.aborted) {
      aborted()
      return
    }
    options.signal?.addEventListener('abort', aborted, { once: true })
    if (terminal(created)) return
    try {
      stream = new EventSource(options.eventsUrl, { withCredentials: true })
      stream.addEventListener('progress', (event) => {
        if (settled || polling) return
        try {
          const next = readMeetingProgress(JSON.parse((event as MessageEvent).data), created.id)
          if (!next) return
          progress = mergeMeetingProgress(progress, next)
          options.onProgress?.(progress)
        } catch {
          fallback()
        }
      })
      stream.addEventListener('done', (event) => {
        if (settled || polling) return
        try {
          terminal(JSON.parse((event as MessageEvent).data) as AgentRunResponse<T>)
        } catch {
          fallback()
        }
      })
      stream.onerror = fallback
    } catch {
      fallback()
    }
  })
}
