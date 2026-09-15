// 계약관리·일정관리 에이전트가 만든 값의 모양.
// backend/app/agents/contract_management.py, schedule_management.py 와
// backend/app/schemas/contract_suggestions.py 의 Pydantic 스키마를 그대로 옮긴다 —
// 필드가 바뀌면 두 쪽을 같이 맞춘다.

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

/** 브리핑 본문이 인용한 근거 하나. id 는 종류에 따라 딜·보고서·문서의 id 다. */
export interface SourceRef {
  type: 'sales_deal' | 'report' | 'support_request' | 'activity' | 'document'
  id: string
}

export interface BriefingHighlight {
  title: string
  body: string
  suggested_actions: string[]
  source_refs: SourceRef[]
  related_deal_ids: string[]
}

export interface HighlightBriefingOutput {
  highlights: BriefingHighlight[]
  missing_information: string[]
}

/** 마이그레이션 전에 저장된 AgentRun 결과를 일정 상세에서 계속 읽기 위한 구 형식. */
export interface LegacyContractBriefingOutput {
  contract_summary: string
  source_refs: SourceRef[]
  risks: ContractRisk[]
  missing_information: string[]
  recommended_actions: string[]
}

export type ContractBriefingOutput = HighlightBriefingOutput | LegacyContractBriefingOutput

/**
 * `GET /contract-next-meeting-suggestions` 한 건. 트리거(보고서 확정·일정 수동 등록·영업 딜
 * 생성/이동·CS 처리 시작)로 서버가 미리 "다음 미팅 날짜 제안 → 유효성 점검"까지 저장한
 * 결과다. 카드 하나에는 계약관리 Agent가 정한 날짜 하나만 있다.
 * backend/app/schemas/contract_suggestions.py 의 ContractNextMeetingSuggestionRead 를 옮긴다.
 */
export interface ContractNextMeetingSuggestion {
  id: string
  sales_deal_id: string
  customer_company_id: string
  customer_company_name: string
  customer_contact_id: string | null
  customer_contact_name: string | null
  owner_member_id: string
  owner_display_name: string
  sales_deal_title: string
  reason: string
  risks: ContractRisk[]
  schedule_management_run_id: string
  target_date: string
  target_time: string | null
  selected_duration_minutes: number | null
  duration_options: [30, 60, 90]
  refresh_reason: string | null
  status_code: 'pending' | 'rejected' | 'expired' | 'accepted'
  created_at: string
  updated_at: string
}

export interface ContractNextMeetingGenerationStatus {
  generating: boolean
  latest_report_pending: boolean
  sales_deal_ids: string[]
}
