import type { AgendaKind } from './agenda'

/** 카드에서 고를 수 있는 시간 후보 하나. 일정관리 에이전트가 만든 것 그대로다. */
export interface AiSuggestionOption {
  candidateId: string
  date: string
  time: string
  dur: string
  startsAt: string
  endsAt: string
  title: string
  /** 1이 가장 추천. 목록은 이 순서로 정렬돼 있다 */
  priority: number
}

/**
 * "AI 추천 일정" 패널의 후보 한 건. 카드 하나가 영업 건 하나다.
 *
 * 트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리 시작)가 서버에서 미리
 * 계산해 저장해 둔 제안을 그대로 옮긴 값이라, 처음부터 날짜·시간까지 채워져 있다 —
 * 화면에서 LLM을 기다리는 단계가 없다.
 * 자세한 배경은 docs/technical/multiagent/계약에이전트_설계.md 11장 참고.
 */
export interface AiSuggestion {
  /** sales_deal_id */
  id: string
  customerCompanyId: string
  customerContactId: string | null
  /** 담당 영업 표시용 */
  owner: string
  hospital: string
  title: string
  contact: string
  dept: string
  kind: AgendaKind
  date: string
  time: string
  dur: string
  startsAt: string
  endsAt: string
  place: string
  /** 일정 후보가 붙인 제목. 승인 시 실제 활동 제목으로 쓴다(카드에 보이는 title=딜 제목과 다름) */
  activityTitle: string
  /** 다음 미팅 제안이 준 이유 */
  proposalReason: string
  /** 추천 근거 배지. 예: ['계약 만료 임박', '재방문 필요'] */
  basis: string[]
  /** 승인 시 브리핑 실행을 이어붙이는 데 쓰는 일정관리 실행 id */
  scheduleRunId: string
  /** 고를 수 있는 시간 후보 전체. 위의 date/time/dur 은 이 중 선택된 것의 값이다 */
  options: AiSuggestionOption[]
  selectedCandidateId: string
}
