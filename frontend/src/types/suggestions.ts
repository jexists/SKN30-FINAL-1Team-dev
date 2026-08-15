import type { AgendaKind } from './agenda'

export interface AiSuggestionSeed {
  id: string
  /** 담당 영업 */
  owner: string
  /** 오늘로부터 며칠 */
  off: number
  time: string
  dur: string
  kind: AgendaKind
  title: string
  hospital: string
  dept: string
  contact: string
  place: string
  /** 왜 지금 이 일정을 잡아야 하는지 한 줄 */
  reason: string
  /** 추천 근거. 배지로 나옵니다. 예: ['12일 미접촉', '계약 협의'] */
  basis: string[]
}

/** 실제 날짜가 붙은 추천 */
export interface AiSuggestion extends AiSuggestionSeed {
  date: string
}
