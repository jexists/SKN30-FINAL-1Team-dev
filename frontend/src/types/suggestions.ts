import type { AgendaKind } from './agenda'

/**
 * "AI 추천 일정" 패널의 후보 한 건.
 *
 * 0차 선별 직후엔 `collapsed`(회사·딜·선별 이유만 있음)로 시작한다. 사용자가 카드를
 * 펼치면(`expand`) 1차 제안 + 일정 후보를 마저 불러와 `ready`(날짜·시간·위험 배지까지 있음)로
 * 바뀐다. LLM 호출은 펼쳐 본 카드에만 든다 — 자세한 배경은
 * docs/technical/multiagent/계약에이전트_설계.md 11장 참고.
 */
export type AiSuggestionStatus = 'collapsed' | 'loading' | 'ready' | 'error'

interface AiSuggestionBase {
  /** sales_deal_id */
  id: string
  customerCompanyId: string
  customerContactId: string | null
  /** 담당 영업 표시용. 지금은 로그인한 본인 이름을 그대로 쓴다 */
  owner: string
  hospital: string
  title: string
  contact: string
  dept: string
  /** 0차 선별이 고른 이유 */
  reason: string
  /** 1이 가장 시급하다 */
  priority: number
}

export interface AiSuggestionCollapsed extends AiSuggestionBase {
  status: 'collapsed'
}

export interface AiSuggestionLoading extends AiSuggestionBase {
  status: 'loading'
}

export interface AiSuggestionError extends AiSuggestionBase {
  status: 'error'
  error: string
}

/** 실제 날짜·시간이 붙은, 지금 바로 캘린더에 넣을 수 있는 추천 */
export interface AiSuggestionReady extends AiSuggestionBase {
  status: 'ready'
  kind: AgendaKind
  date: string
  time: string
  dur: string
  startsAt: string
  endsAt: string
  place: string
  /** 일정 후보가 붙인 제목. 승인 시 실제 활동 제목으로 쓴다(카드에 보이는 title=딜 제목과 다름) */
  activityTitle: string
  /** 1차 제안이 준, 더 구체적인 이유. 있으면 reason 대신 보여준다 */
  proposalReason: string
  /** 추천 근거 배지. 예: ['계약 만료 임박', '재방문 필요'] */
  basis: string[]
  /** 승인 시 브리핑 실행을 이어붙이는 데 쓰는 일정관리 실행 id */
  scheduleRunId: string
}

export type AiSuggestion =
  AiSuggestionCollapsed | AiSuggestionLoading | AiSuggestionError | AiSuggestionReady
