import type { AgendaKind } from './agenda'

/**
 * "AI 추천 일정" 패널의 후보 한 건.
 *
 * 보고서 승인·일정 수동 등록·영업 딜 생성/이동·CS 접수 처리 시작 트리거로 서버가 미리
 * "다음 미팅 제안 → 일정 후보"까지 이어서 계산해 저장해 둔 결과를 그대로 읽는다 — 날짜·
 * 시간까지 이미 붙어 있어 화면이 LLM 호출 없이 바로 뜬다. 자세한 배경은
 * docs/technical/multiagent/계약에이전트_설계.md 3장·11장 참고.
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
  /** 다음 미팅 제안의 이유 */
  proposalReason: string
  /** 추천 근거 배지. 예: ['계약 만료 임박', '재방문 필요'] */
  basis: string[]
  /** 승인 시 브리핑 실행을 이어붙이는 데 쓰는 일정관리 실행 id */
  scheduleRunId: string
}
