import { client } from './client'
import {
  AgentRunTerminalError,
  isAgentRunTerminalError,
  MEETING_WAIT_MS,
  meetingChildDecision,
  waitForMeetingRun,
} from './meetingStream'

export { isAgentRunTerminalError }

import type {
  AgentRunResponse,
  AgentRunChildResponse,
  AgentRunStatus,
  MeetingProcessingOutput,
  MeetingAnalysisChildOutput,
  MeetingReportChildOutput,
  MeetingProgress,
  ReportFinalizeRequest,
  ReportGenerationInput,
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

async function waitForMeetingReportChild(
  child: AgentRunChildResponse,
  parentRunId: string,
  onProgress: ((progress: MeetingProgress) => void) | undefined,
  signal: AbortSignal | undefined,
  pollIntervalMs: number,
): Promise<AgentRunChildResponse> {
  if (!['queued', 'running'].includes(child.status_code)) return child
  const created = {
    ...child,
    report_id: null,
    generation_input: null,
    attempt_count: 1,
    evidence: null,
  } as unknown as AgentRunResponse<MeetingReportChildOutput>
  const completed = await waitForMeetingRun(created, {
    eventsUrl: client.getUri({ url: `/agent-runs/${child.id}/events` }),
    readRun: async (pollSignal) =>
      (
        await client.get<AgentRunResponse<MeetingReportChildOutput>>(`/agent-runs/${child.id}`, {
          signal: pollSignal,
        })
      ).data,
    onProgress: (progress) => onProgress?.({ ...progress, run_id: parentRunId }),
    signal,
    pollIntervalMs,
  })
  return {
    ...child,
    ...completed,
    output_snapshot: completed.output_snapshot,
  } as AgentRunChildResponse
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

function generationInputComparable(
  value: ReportGenerationInput | ReportGenerationRequest,
): Record<string, unknown> {
  return {
    report_kind: value.report_kind,
    report_date: value.report_date,
    period_start: value.period_start ?? null,
    period_end: value.period_end ?? null,
    source_activity_id: value.source_activity_id ?? null,
    sales_deal_ids: value.sales_deal_ids ?? [],
    attachments: value.attachments ?? [],
    template_snapshot: value.template_snapshot,
    content: value.content,
    transcript: value.transcript ?? null,
    guidance: value.guidance ?? null,
  }
}

/** Compare frozen generation inputs without considering the POST idempotency key. */
export function sameReportGenerationInput(
  previous: ReportGenerationInput | null | undefined,
  current: ReportGenerationRequest,
): boolean {
  if (!previous) return false
  return (
    idempotencyAttemptFor(undefined, generationInputComparable(previous)).signature ===
    idempotencyAttemptFor(undefined, generationInputComparable(current)).signature
  )
}

/** 성공하거나 확정 실패한 현재 시도만 닫습니다. 더 늦게 끝난 옛 요청은 건드리지 않습니다. */
export function finishIdempotencyAttempt(
  current: IdempotencyAttempt | undefined,
  key: string,
): IdempotencyAttempt | undefined {
  return current?.key === key ? undefined : current
}

export async function createReportGeneration<T>(
  request: ReportGenerationRequest,
): Promise<AgentRunResponse<T>> {
  return (await client.post<AgentRunResponse<T>>('/report-generations', request)).data
}

export async function retryMeetingReport<T>(agentRunId: string): Promise<AgentRunResponse<T>> {
  return (await client.post<AgentRunResponse<T>>(`/agent-runs/${agentRunId}/retry`)).data
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
  pollIntervalMs = POLL_INTERVAL_MS,
) {
  return waitForMeetingChildren(run, onProgress, signal, pollIntervalMs)
}

async function waitForMeetingChildren(
  created: AgentRunResponse<MeetingProcessingOutput>,
  onProgress?: (progress: MeetingProgress) => void,
  signal?: AbortSignal,
  pollIntervalMs = POLL_INTERVAL_MS,
): Promise<CompletedAgentRun<MeetingProcessingOutput>> {
  let run = created
  const parentId =
    created.agent_code === 'meeting_processing'
      ? created.id
      : String(created.source_refs.parent_run_id ?? created.id)
  const deadline = Date.now() + MEETING_WAIT_MS
  while (true) {
    if (Date.now() >= deadline) throw new Error('agent_run_timeout')
    if (run.agent_code === 'meeting_report_writing') {
      await waitForMeetingReportChild(
        run as unknown as AgentRunChildResponse,
        parentId,
        onProgress,
        signal,
        pollIntervalMs,
      )
      run = (
        await client.get<AgentRunResponse<MeetingProcessingOutput>>(`/agent-runs/${parentId}`, {
          signal,
        })
      ).data
      continue
    }
    const report = [...(run.child_runs ?? [])]
      .reverse()
      .find((child) => child.agent_code === 'meeting_report_writing')
    const analysis = [...(run.child_runs ?? [])]
      .reverse()
      .find((child) => child.agent_code === 'meeting_analysis')
    const decision = meetingChildDecision(run)
    if (decision === 'failed') {
      throw new AgentRunTerminalError(run.error_code ?? run.error_message ?? 'agent_run_failed')
    }
    const parentOutput = run.output_snapshot as unknown as Record<string, unknown> | null
    if (decision === 'legacy') {
      return run as CompletedAgentRun<MeetingProcessingOutput>
    }
    if (report && ['queued', 'running'].includes(report.status_code)) {
      await waitForMeetingReportChild(report, run.id, onProgress, signal, pollIntervalMs)
      run = (
        await client.get<AgentRunResponse<MeetingProcessingOutput>>(`/agent-runs/${parentId}`, {
          signal,
        })
      ).data
      continue
    }
    if (report && decision === 'ready') {
      const reports = report.output_snapshot as MeetingReportChildOutput | null
      if (reports) {
        const output: MeetingProcessingOutput = {
          reports: reports as MeetingProcessingOutput['reports'],
          analyses:
            (analysis?.output_snapshot as MeetingAnalysisChildOutput | null)?.analyses ?? [],
          evidence:
            (parentOutput?.evidence as MeetingProcessingOutput['evidence'] | undefined) ??
            (() => {
              throw new AgentRunTerminalError('meeting_evidence_missing')
            })(),
          errors: {
            ...(report.error_code ? { report_writing: report.error_code } : {}),
            ...(analysis?.error_code ? { meeting_analysis: analysis.error_code } : {}),
          },
        }
        return {
          ...run,
          id: report.id,
          source_refs: { ...run.source_refs, parent_run_id: run.id },
          output_snapshot: output,
        }
      }
    }
    if (run.status_code === 'queued' || run.status_code === 'running') {
      onProgress?.({
        run_id: run.id,
        status_code: run.status_code,
        stage: run.current_stage_code ?? 'starting',
        previews: [],
      })
    }
    await wait(pollIntervalMs, signal)
    run = (
      await client.get<AgentRunResponse<MeetingProcessingOutput>>(`/agent-runs/${parentId}`, {
        signal,
      })
    ).data
  }
}

function latestMeetingAnalysisChild(
  run: AgentRunResponse<MeetingProcessingOutput>,
): AgentRunChildResponse | undefined {
  return [...(run.child_runs ?? [])]
    .reverse()
    .find((child) => child.agent_code === 'meeting_analysis')
}

/** Keep the report editable while the independent analysis child finishes. */
export async function waitForMeetingAnalysis(
  parentRunId: string,
  onAnalysis?: (child: AgentRunChildResponse) => void,
  signal?: AbortSignal,
  pollIntervalMs = POLL_INTERVAL_MS,
): Promise<AgentRunChildResponse | undefined> {
  const deadline = Date.now() + MEETING_WAIT_MS
  let run = (
    await client.get<AgentRunResponse<MeetingProcessingOutput>>(`/agent-runs/${parentRunId}`, {
      signal,
    })
  ).data
  while (Date.now() < deadline) {
    if (run.status_code === 'failed' || run.status_code === 'cancelled') return undefined
    const child = latestMeetingAnalysisChild(run)
    if (child) {
      onAnalysis?.(child)
      if (!['queued', 'running'].includes(child.status_code)) return child
    }
    const remaining = deadline - Date.now()
    if (remaining <= 0) break
    await wait(Math.min(pollIntervalMs, remaining), signal)
    run = (
      await client.get<AgentRunResponse<MeetingProcessingOutput>>(`/agent-runs/${parentRunId}`, {
        signal,
      })
    ).data
  }
  throw new Error('agent_run_timeout')
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
