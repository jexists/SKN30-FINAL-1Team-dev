import type { RiskCode } from '@/types'

/** 위험 배지에 쓰는 짧은 한글 라벨. backend/app/agents/contract_management.py 의 RiskCode 와 짝을 맞춘다. */
export const RISK_LABEL: Record<RiskCode, string> = {
  contract_expiring: '계약 만료 임박',
  quote_expiring: '견적 만료 임박',
  delivery_delay_risk: '배송 지연',
  unresolved_support: '미해결 C/S',
  follow_up_overdue: '연락 지연',
  missing_contract_information: '계약 정보 누락',
  contract_revisit_due: '재방문 필요',
}
