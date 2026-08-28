import { client } from './client'

import type { AgentRunResponse, AgentRunStatus } from '@/types'

const POLL_INTERVAL_MS = 2_000
const MAX_POLLS = 30

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

export interface ReportDraftResult {
  values: Record<string, string>
  evidence?: string
}

/**
 * @param onStatus 폴링할 때마다 서버가 말한 상태. 기다리는 화면이 지금 어디쯤인지
 *                 말해 줄 때 씁니다. 서버는 이 세 가지 말고는 알려 주지 않습니다.
 */
export async function generateReportDraft(
  reportId: string,
  onStatus?: (status: AgentRunStatus) => void,
): Promise<ReportDraftResult> {
  const { data: created } = await client.post<AgentRunResponse>('/agent-runs', {
    agent_code: 'report_writing',
    report_id: reportId,
    idempotency_key: crypto.randomUUID(),
  })

  let run = created
  onStatus?.(run.status_code)
  for (let poll = 0; run.status_code === 'queued' || run.status_code === 'running'; poll += 1) {
    if (poll >= MAX_POLLS) throw new Error('agent_run_timeout')
    await wait(POLL_INTERVAL_MS)
    run = (await client.get<AgentRunResponse>(`/agent-runs/${run.id}`)).data
    onStatus?.(run.status_code)
  }

  if (run.status_code !== 'completed' || !run.output_snapshot) {
    throw new Error(run.error_message ?? 'agent_run_failed')
  }

  return {
    values: Object.fromEntries(
      (run.output_snapshot.fields ?? []).map((field) => [field.field_id, field.value]),
    ),
    evidence: run.evidence?.summary ?? run.output_snapshot.summary,
  }
}
