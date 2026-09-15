import { client } from './client'

import type { ContractNextMeetingSuggestion } from '@/types'

// 트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리 시작)가 서버에서
// "다음 미팅 제안 → 일정 후보"까지 미리 계산해 저장해 둔다. 캘린더는 그 결과를 조회만
// 한다 — LLM을 직접 호출하지 않으므로 화면이 기다리지 않는다.
// docs/technical/multiagent/계약에이전트_설계.md 3장·11장 참고.

/** 캘린더 "AI 추천 일정" 패널에 보여줄, 저장된 제안 목록. */
export async function listNextMeetingSuggestions(): Promise<ContractNextMeetingSuggestion[]> {
  const { data } = await client.get<ContractNextMeetingSuggestion[]>(
    '/contract-next-meeting-suggestions',
  )
  return data
}

/**
 * 카드를 닫는다. 서버 상태를 dismissed 로 남겨 캘린더에 다시 들어와도 뜨지 않는다.
 * 단 그 딜에 새 트리거가 걸리면 새 제안으로 다시 올라온다.
 */
export async function dismissNextMeetingSuggestion(salesDealId: string): Promise<void> {
  await client.post(`/contract-next-meeting-suggestions/${salesDealId}/dismiss`)
}

/** 저장된 최신 보고서·자료를 다시 읽어 일정 브리핑을 재생성한다. */
export async function regenerateBriefing(activityId: string): Promise<void> {
  await client.post('/agent-runs', {
    agent_code: 'contract_management_briefing',
    activity_id: activityId,
    idempotency_key: crypto.randomUUID(),
  })
}
