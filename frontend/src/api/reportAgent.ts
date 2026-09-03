import { client } from './client'
import {
  AgentRunTerminalError,
  isAgentRunTerminalError,
  MEETING_WAIT_MS,
  waitForMeetingRun,
} from './meetingStream'

export { isAgentRunTerminalError }

import type {
  AgentRunResponse,
  AgentRunStatus,
  MeetingProcessingOutput,
  MeetingProgress,
  ReportFinalizeRequest,
  ReportGenerationRequest,
  ReportGenerationScope,
  ReportResponse,
} from '@/types'

const POLL_INTERVAL_MS = 2_000

const wait = (milliseconds: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('화면을 떠나 대기를 종료했습니다.', 'AbortError'))
      return
    }
    const aborted = () => {
      globalThis.clearTimeout(timer)
      reject(new DOMException('화면을 떠나 대기를 종료했습니다.', 'AbortError'))
    }
    const timer = globalThis.setTimeout(() => {
      signal?.removeEventListener('abort', aborted)
      resolve()
    }, milliseconds)
    signal?.addEventListener('abort', aborted, { once: true })
  })

type CompletedAgentRun<T> = Omit<AgentRunResponse<T>, 'output_snapshot'> & {
  output_snapshot: T
}

export interface IdempotencyAttempt {
  signature: string
  key: string
}

/** 같은 내용의 응답 유실 재시도에는 같은 키를, 내용이 바뀌면 새 키를 줍니다. */
export function idempotencyAttemptFor(
  current: IdempotencyAttempt | undefined,
  payload: unknown,
): IdempotencyAttempt {
  const signature = JSON.stringify(payload, (_key, value) =>
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(
          Object.entries(value).sort(([left], [right]) => left.localeCompare(right)),
        )
      : value,
  )
  return current?.signature === signature ? current : { signature, key: crypto.randomUUID() }
}

/** 성공하거나 확정 실패한 현재 시도만 닫습니다. 더 늦게 끝난 옛 요청은 건드리지 않습니다. */
export function finishIdempotencyAttempt(
  current: IdempotencyAttempt | undefined,
  key: string,
): IdempotencyAttempt | undefined {
  return current?.key === key ? undefined : current
}

/** Canonical 보고서가 있으면 재접속 후보를 사람 확인 없이 덮지 않습니다. */
export function requiresRecoveryConfirmation(reportId?: string): boolean {
  return Boolean(reportId)
}

export async function createReportGeneration<T>(
  request: ReportGenerationRequest,
): Promise<AgentRunResponse<T>> {
  return (await client.post<AgentRunResponse<T>>('/report-generations', request)).data
}

export async function latestReportGeneration<T>(
  scope: ReportGenerationScope,
  signal?: AbortSignal,
): Promise<AgentRunResponse<T>> {
  return (
    await client.get<AgentRunResponse<T>>('/report-generations/latest', {
      params: scope,
      signal,
    })
  ).data
}

export async function finalizeReport(
  request: ReportFinalizeRequest,
  signal?: AbortSignal,
): Promise<ReportResponse> {
  return (await client.post<ReportResponse>('/reports/finalize', request, { signal })).data
}

export async function waitForReportGeneration<T>(
  created: AgentRunResponse<T>,
  onStatus?: (status: AgentRunStatus) => void,
  signal?: AbortSignal,
  pollIntervalMs = POLL_INTERVAL_MS,
): Promise<CompletedAgentRun<T>> {
  let run = created
  const deadline = Date.now() + MEETING_WAIT_MS
  onStatus?.(run.status_code)
  while (run.status_code === 'queued' || run.status_code === 'running') {
    if (Date.now() >= deadline) throw new Error('agent_run_timeout')
    await wait(Math.min(pollIntervalMs, deadline - Date.now()), signal)
    const remaining = deadline - Date.now()
    if (remaining <= 0) throw new Error('agent_run_timeout')
    run = (
      await client.get<AgentRunResponse<T>>(`/agent-runs/${run.id}`, {
        timeout: Math.min(client.defaults.timeout || 10_000, remaining),
        signal,
      })
    ).data
    onStatus?.(run.status_code)
  }

  const output = run.output_snapshot
  if (!['completed', 'partial'].includes(run.status_code) || !output) {
    throw new AgentRunTerminalError(run.error_code ?? run.error_message ?? 'agent_run_failed')
  }
  return { ...run, output_snapshot: output }
}

export function waitForMeetingProcessing(
  run: AgentRunResponse<MeetingProcessingOutput>,
  onProgress?: (progress: MeetingProgress) => void,
  signal?: AbortSignal,
) {
  return waitForMeetingRun(run, {
    eventsUrl: client.getUri({ url: `/agent-runs/${run.id}/events` }),
    readRun: async (pollSignal) =>
      (
        await client.get<AgentRunResponse<MeetingProcessingOutput>>(`/agent-runs/${run.id}`, {
          signal: pollSignal,
        })
      ).data,
    onProgress,
    signal,
  })
}

export async function latestMeetingProcessing(
  sourceActivityId: string,
  signal?: AbortSignal,
): Promise<AgentRunResponse<MeetingProcessingOutput>> {
  return latestReportGeneration<MeetingProcessingOutput>(
    { report_kind: 'meeting', source_activity_id: sourceActivityId },
    signal,
  )
}
