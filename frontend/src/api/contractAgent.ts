import { client } from './client'

import type { ContractNextMeetingGenerationStatus, ContractNextMeetingSuggestion } from '@/types'

// 트리거(보고서 확정·일정 수동 등록·영업 딜 생성/이동·CS 처리 시작)가 서버에서
// "다음 미팅 날짜 제안 → 유효성 점검"까지 미리 계산해 저장해 둔다. 캘린더는 그 결과를 조회만
// 한다 — LLM을 직접 호출하지 않으므로 화면이 기다리지 않는다.
// docs/technical/multiagent/계약에이전트_설계.md 3장·11장 참고.

/** 캘린더 "AI 추천 일정" 패널에 보여줄, 저장된 제안 목록. */
export async function listNextMeetingSuggestions(): Promise<ContractNextMeetingSuggestion[]> {
  const { data } = await client.get<ContractNextMeetingSuggestion[]>(
    '/contract-next-meeting-suggestions',
  )
  return data
}

/** 저장된 추천을 오늘 기준으로 점검하고, 만료된 카드만 새 날짜로 교체한다. */
export async function refreshNextMeetingSuggestions(): Promise<void> {
  await client.post('/contract-next-meeting-suggestions/refresh')
}

/** 현재 날짜를 제외하고 계약관리 Agent에게 새 날짜를 요청한다. */
export async function rejectNextMeetingSuggestion(salesDealId: string): Promise<void> {
  await client.post(`/contract-next-meeting-suggestions/${salesDealId}/reject`)
}

/** 같은 최신 근거로 추천을 다시 만들도록 명시적으로 요청한다. */
export async function regenerateNextMeetingSuggestion(salesDealId: string): Promise<void> {
  await client.post(`/contract-next-meeting-suggestions/${salesDealId}/regenerate`)
}

/** 추천 생성 중인지 확인한다. LLM을 호출하지 않는 가벼운 상태 조회다. */
export async function getNextMeetingGenerationStatus(): Promise<ContractNextMeetingGenerationStatus> {
  const { data } = await client.get<ContractNextMeetingGenerationStatus>(
    '/contract-next-meeting-suggestions/generation-status',
  )
  return data
}

/** 시작 시각이 없는 추천을 날짜와 소요시간만 정한 상태로 반영한다. */
export async function applyDateOnlySuggestion(
  salesDealId: string,
  durationMinutes: 30 | 60 | 90,
  targetDate: string,
): Promise<void> {
  await client.post(`/contract-next-meeting-suggestions/${salesDealId}/apply`, {
    duration_minutes: durationMinutes,
    target_date: targetDate,
  })
}

/** 저장된 최신 보고서·자료를 다시 읽어 일정 브리핑을 재생성한다. */
export async function regenerateBriefing(activityId: string): Promise<void> {
  await client.post('/agent-runs', {
    agent_code: 'contract_management_briefing',
    activity_id: activityId,
    idempotency_key: crypto.randomUUID(),
  })
}
