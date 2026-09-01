import { isAxiosError, isCancel } from 'axios'

import type { AgentRunResponse, MeetingPreview, MeetingProgress } from '@/types'

export const MEETING_WAIT_MS = 25 * 60 * 1_000
const POLL_INTERVAL_MS = 2_000

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
    !['queued', 'running', 'completed', 'failed'].includes(event.status_code ?? '') ||
    typeof event.stage !== 'string' ||
    !Array.isArray(event.previews)
  )
    return null
  if (
    !event.previews.every(
      (preview) =>
        preview &&
        ['deal', 'common', 'unassigned'].includes(preview.section) &&
        (preview.section === 'deal'
          ? typeof preview.sales_deal_id === 'string'
          : preview.sales_deal_id === null) &&
        typeof preview.body === 'string' &&
        Number.isInteger(preview.revision) &&
        preview.revision >= 0,
    )
  )
    return null
  return {
    run_id: runId,
    status_code: event.status_code!,
    stage: event.stage,
    previews: event.previews,
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
  const key = (preview: MeetingPreview) => `${preview.section}:${preview.sales_deal_id ?? ''}`
  const old = new Map(previous?.previews.map((preview) => [key(preview), preview]))
  return {
    ...next,
    previews: next.previews.map((preview) => {
      const existing = old.get(key(preview))
      return existing && existing.revision > preview.revision ? existing : preview
    }),
  }
}

/** 스트림 실패 시 같은 실행만 GET 합니다. 실행 생성/저장 API는 이 함수에 없습니다. */
export function waitForMeetingRun<T>(
  created: AgentRunResponse<T>,
  options: {
    eventsUrl: string
    readRun: (signal: AbortSignal) => Promise<AgentRunResponse<T>>
    onProgress?: (progress: MeetingProgress) => void
    signal?: AbortSignal
  },
): Promise<AgentRunResponse<T> & { output_snapshot: T }> {
  return new Promise((resolve, reject) => {
    const controller = new AbortController()
    let stream: EventSource | undefined
    let polling = false
    let settled = false
    let pollTimer: ReturnType<typeof setTimeout> | undefined
    let retryDelay = POLL_INTERVAL_MS
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
      if (run.status_code === 'failed') {
        finish(new Error(run.error_message ?? 'agent_run_failed'))
        return true
      }
      if (run.status_code === 'completed') {
        if (run.output_snapshot) finish(undefined, { ...run, output_snapshot: run.output_snapshot })
        else finish(new Error('agent_run_failed'))
        return true
      }
      return false
    }
    async function poll() {
      if (settled) return
      try {
        const run = await options.readRun(controller.signal)
        if (settled || terminal(run)) return
        retryDelay = POLL_INTERVAL_MS
        pollTimer = setTimeout(() => void poll(), POLL_INTERVAL_MS)
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
