import { client } from './client'
import { MEETING_WAIT_MS, waitForMeetingRun } from './meetingStream'

import type {
  AgentRunResponse,
  AgentRunStatus,
  DealAssessment,
  MeetingAnalysisSnapshot,
  MeetingAssignmentOverride,
  MeetingProcessingOutput,
  MeetingProgress,
  ReportDraftSnapshot,
  ReportResponse,
} from '@/types'

const POLL_INTERVAL_MS = 2_000

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

export interface ReportDraftResult {
  values: Record<string, string>
  evidence?: string
}

type CompletedAgentRun<T> = Omit<AgentRunResponse<T>, 'output_snapshot'> & {
  output_snapshot: T
}

async function runAgent<T>(
  agentCode: 'report_writing' | 'meeting_analysis',
  reportId: string,
  onStatus?: (status: AgentRunStatus) => void,
): Promise<CompletedAgentRun<T>> {
  const { data: created } = await client.post<AgentRunResponse<T>>('/agent-runs', {
    agent_code: agentCode,
    report_id: reportId,
    idempotency_key: crypto.randomUUID(),
  })

  return pollRun(created, onStatus)
}

async function pollRun<T>(
  created: AgentRunResponse<T>,
  onStatus?: (status: AgentRunStatus) => void,
): Promise<CompletedAgentRun<T>> {
  let run = created
  const deadline = Date.now() + MEETING_WAIT_MS
  onStatus?.(run.status_code)
  while (run.status_code === 'queued' || run.status_code === 'running') {
    if (Date.now() >= deadline) throw new Error('agent_run_timeout')
    await wait(Math.min(POLL_INTERVAL_MS, deadline - Date.now()))
    const remaining = deadline - Date.now()
    if (remaining <= 0) throw new Error('agent_run_timeout')
    run = (
      await client.get<AgentRunResponse<T>>(`/agent-runs/${run.id}`, {
        timeout: Math.min(client.defaults.timeout || 10_000, remaining),
      })
    ).data
    onStatus?.(run.status_code)
  }

  const output = run.output_snapshot
  if (run.status_code !== 'completed' || !output) {
    throw new Error(run.error_message ?? 'agent_run_failed')
  }
  return { ...run, output_snapshot: output }
}

/**
 * @param onStatus 폴링할 때마다 서버가 말한 상태. 기다리는 화면이 지금 어디쯤인지
 *                 말해 줄 때 씁니다. 서버는 이 세 가지 말고는 알려 주지 않습니다.
 */
export async function generateReportDraft(
  reportId: string,
  onStatus?: (status: AgentRunStatus) => void,
): Promise<ReportDraftResult> {
  const run = await runAgent<ReportDraftSnapshot>('report_writing', reportId, onStatus)
  const output = run.output_snapshot

  return {
    values: Object.fromEntries((output.fields ?? []).map((field) => [field.field_id, field.value])),
    evidence: run.evidence?.summary ?? output.summary,
  }
}

/** 미팅분석 에이전트와 ML 모델이 만든 딜별 판정입니다. Report 자체는 고치지 않습니다. */
export async function analyzeMeetingReport(reportId: string): Promise<DealAssessment> {
  const run = await runAgent<MeetingAnalysisSnapshot>('meeting_analysis', reportId)
  return run.output_snapshot.deal_assessment
}

/** 선택된 딜 전체가 같은 원문·근거 장부로 처리되는 미팅 실행입니다. */
export async function processMeeting(
  reportId: string,
  overrides?: { parent_run_id: string; assignment_overrides: MeetingAssignmentOverride[] },
  onProgress?: (progress: MeetingProgress) => void,
  signal?: AbortSignal,
) {
  const { data } = await client.post<AgentRunResponse<MeetingProcessingOutput>>(
    `/reports/${reportId}/generations`,
    {
      idempotency_key: crypto.randomUUID(),
      ...overrides,
    },
    { signal },
  )
  return waitForMeetingProcessing(data, onProgress, signal)
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

export async function readReport(reportId: string): Promise<ReportResponse> {
  return (await client.get<ReportResponse>(`/reports/${reportId}`)).data
}

export async function latestMeetingProcessing(
  reportId: string,
): Promise<AgentRunResponse<MeetingProcessingOutput>> {
  return (
    await client.get<AgentRunResponse<MeetingProcessingOutput>>(
      `/reports/${reportId}/generations/latest`,
    )
  ).data
}

export async function saveMeetingNotes(
  runId: string,
  expectedRevision: string,
  commonBody: string | null,
  unassignedBody: string | null,
): Promise<ReportResponse> {
  return (
    await client.patch<ReportResponse>(`/agent-runs/${runId}/meeting-notes`, {
      expected_revision: expectedRevision,
      common_body: commonBody,
      unassigned_body: unassignedBody,
    })
  ).data
}
