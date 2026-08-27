// 계약관리·일정관리 에이전트(`/agent-runs`)가 주고받는 값의 모양.
// backend/app/agents/contract_management.py, schedule_management.py 의 Pydantic 스키마를
// 그대로 옮긴다 — 필드가 바뀌면 두 쪽을 같이 맞춘다.

import type { AgentRunStatus } from './reports'

/** `POST/GET /agent-runs` 공통 응답 뼈대. output_snapshot 모양은 agent_code 마다 다르다. */
export interface AgentRunEnvelope<TOutput> {
  id: string
  status_code: AgentRunStatus
  output_snapshot: TOutput | null
  error_message: string | null
}

// 화면·알림·테스트가 이 값에 의존하므로 자유 문구 대신 일곱 가지로 고정한다
// (contract_management.py 의 RiskCode 와 동일).
export type RiskCode =
  | 'contract_expiring'
  | 'quote_expiring'
  | 'delivery_delay_risk'
  | 'unresolved_support'
  | 'follow_up_overdue'
  | 'missing_contract_information'
  | 'contract_revisit_due'

export type RiskSeverity = 'low' | 'medium' | 'high'

export interface ContractRisk {
  code: RiskCode
  severity: RiskSeverity
  message: string
}

export interface SelectedNextMeetingCandidate {
  customer_company_id: string
  sales_deal_id: string
  reason: string
  priority: number
}

export interface SelectNextMeetingCandidatesOutput {
  candidates: SelectedNextMeetingCandidate[]
}

export interface NextMeetingSuggestion {
  sales_deal_id: string
  reason: string
  preferred_starts_at: string | null
  preferred_ends_at: string | null
  duration_minutes: number
}

export interface NextMeetingProposalOutput {
  risks: ContractRisk[]
  missing_information: string[]
  recommended_actions: string[]
  next_meeting_suggestion: NextMeetingSuggestion | null
}

export interface ScheduleCandidate {
  candidate_id: string
  title: string
  starts_at: string
  ends_at: string
  priority: number
  reason: string
}

export interface ScheduleManagementOutput {
  schedule_candidates: ScheduleCandidate[]
}

export interface ContractBriefingOutput {
  contract_summary: string
  risks: ContractRisk[]
  missing_information: string[]
  recommended_actions: string[]
}
