import { client } from './client'

import type {
  AgentRunResponse,
  AgentRunStatus,
  DealAssessment,
  MeetingAnalysisSnapshot,
  ReportDraftSnapshot,
} from '@/types'

const POLL_INTERVAL_MS = 2_000
const MAX_POLLS = 30

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

  let run = created
  onStatus?.(run.status_code)
  for (let poll = 0; run.status_code === 'queued' || run.status_code === 'running'; poll += 1) {
    if (poll >= MAX_POLLS) throw new Error('agent_run_timeout')
    await wait(POLL_INTERVAL_MS)
    run = (await client.get<AgentRunResponse<T>>(`/agent-runs/${run.id}`)).data
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
