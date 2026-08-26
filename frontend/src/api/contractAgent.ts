import { client } from './client'

import type {
  AgentRunEnvelope,
  NextMeetingProposalOutput,
  ScheduleManagementOutput,
  SelectNextMeetingCandidatesOutput,
} from '@/types'

// reportAgent.ts 의 report_writing 폴링과 같은 간격·횟수를 쓴다.
const POLL_INTERVAL_MS = 2_000
const MAX_POLLS = 30

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

/** agent-run 을 만들고, 끝날 때까지(성공/실패) 폴링해서 완료된 실행을 돌려준다. */
async function runAgent<TOutput>(
  payload: Record<string, unknown>,
): Promise<AgentRunEnvelope<TOutput>> {
  const { data: created } = await client.post<AgentRunEnvelope<TOutput>>('/agent-runs', {
    ...payload,
    idempotency_key: crypto.randomUUID(),
  })

  let run = created
  for (let poll = 0; run.status_code === 'queued' || run.status_code === 'running'; poll += 1) {
    if (poll >= MAX_POLLS) throw new Error('agent_run_timeout')
    await wait(POLL_INTERVAL_MS)
    run = (await client.get<AgentRunEnvelope<TOutput>>(`/agent-runs/${run.id}`)).data
  }

  if (run.status_code !== 'completed' || !run.output_snapshot) {
    throw new Error(run.error_message ?? 'agent_run_failed')
  }
  return run
}

/** 0차 선별: 담당자가 맡은 딜 중 다음 미팅 제안이 필요한 딜을 고른다. LLM 호출 1회. */
export async function selectNextMeetingCandidates(): Promise<SelectNextMeetingCandidatesOutput> {
  const run = await runAgent<SelectNextMeetingCandidatesOutput>({
    agent_code: 'contract_management_select_candidates',
  })
  return run.output_snapshot as SelectNextMeetingCandidatesOutput
}

/** 1차 제안: 한 회사의 위험을 판정하고 다음 미팅을 제안한다. */
export async function proposeNextMeeting(
  customerCompanyId: string,
): Promise<{ runId: string; output: NextMeetingProposalOutput }> {
  const run = await runAgent<NextMeetingProposalOutput>({
    agent_code: 'contract_management_next_meeting',
    customer_company_id: customerCompanyId,
  })
  return { runId: run.id, output: run.output_snapshot as NextMeetingProposalOutput }
}

/** 일정 후보: 1차 제안 실행을 이어받아 겹치지 않는 후보 시간을 추천한다. */
export async function scheduleCandidates(
  salesDealId: string,
  parentRunId: string,
): Promise<{ runId: string; output: ScheduleManagementOutput }> {
  const run = await runAgent<ScheduleManagementOutput>({
    agent_code: 'schedule_management',
    sales_deal_id: salesDealId,
    parent_run_id: parentRunId,
  })
  return { runId: run.id, output: run.output_snapshot as ScheduleManagementOutput }
}

// 브리핑 실행은 별도로 트리거하지 않는다 — `POST /activities`에 schedule_management 실행
// id(`scheduleManagementRunId`)를 실어 보내면 서버가 등록 커밋 직후 자동으로 큐잉한다
// (backend/app/api/activities.py `create_activity`).
