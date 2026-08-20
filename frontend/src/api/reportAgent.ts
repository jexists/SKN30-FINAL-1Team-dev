import { client } from './client'

import type { AgentRunResponse } from '@/types'

const POLL_INTERVAL_MS = 2_000
const MAX_POLLS = 30

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

export interface ReportDraftResult {
  values: Record<string, string>
  evidence?: string
}

export async function generateReportDraft(reportId: string): Promise<ReportDraftResult> {
  const { data: created } = await client.post<AgentRunResponse>('/agent-runs', {
    agent_code: 'report_writing',
    report_id: reportId,
    idempotency_key: crypto.randomUUID(),
  })

  let run = created
  for (let poll = 0; run.status_code === 'queued' || run.status_code === 'running'; poll += 1) {
    if (poll >= MAX_POLLS) throw new Error('agent_run_timeout')
    await wait(POLL_INTERVAL_MS)
    run = (await client.get<AgentRunResponse>(`/agent-runs/${run.id}`)).data
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
