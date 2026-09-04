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

export interface ScheduleCandidate {
  candidate_id: string
  title: string
  starts_at: string
  ends_at: string
  priority: number
  reason: string
}

/** 브리핑 본문이 인용한 근거 하나. id 는 종류에 따라 딜·보고서·문서의 id 다. */
export interface SourceRef {
  type: 'sales_deal' | 'report' | 'support_request' | 'activity' | 'document'
  id: string
}

export interface ContractBriefingOutput {
  contract_summary: string
  source_refs: SourceRef[]
  risks: ContractRisk[]
  missing_information: string[]
  recommended_actions: string[]
}

/**
 * `GET /contract-next-meeting-suggestions` 한 건. 트리거(보고서 확정·일정 수동 등록·영업 딜
 * 생성/이동·CS 처리 시작)로 서버가 미리 "다음 미팅 제안 → 일정 후보"까지 계산해 저장해 둔
 * 결과다 — 캘린더가 이 값을 읽을 때는 LLM을 부르지 않는다.
 * backend/app/schemas/contract_suggestions.py 의 ContractNextMeetingSuggestionRead 를 옮긴다.
 */
/**
 * 딜이 붙지 않은 예정 방문. 딜이 붙은 일정은 추천 계산이 이미 보고 있어 추천 자체가
 * 올라오지 않지만, 딜이 없는 일정은 그 계산에 잡히지 않는다.
 */
export interface ScheduledCompanyVisit {
  starts_at: string
  title: string
}

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
  schedule_candidates: ScheduleCandidate[]
  /** 이 회사에 딜 없이 잡아 둔 가장 이른 방문. 추천을 막지는 않고 카드에 알리기만 한다. */
  scheduled_company_visit: ScheduledCompanyVisit | null
  status_code: 'pending' | 'dismissed' | 'accepted'
  created_at: string
  updated_at: string
}
