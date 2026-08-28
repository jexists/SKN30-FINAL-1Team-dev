import { client } from './client'

import type { ContractNextMeetingSuggestion } from '@/types'

// 트리거(보고서 승인·일정 수동 등록·영업 딜 생성/이동·CS 접수 처리 시작)가 서버에서
// "다음 미팅 제안 → 일정 후보"까지 미리 계산해 저장해 둔다. 캘린더는 그 결과를 조회만
// 한다 — LLM을 직접 호출하지 않는다. docs/technical/multiagent/계약에이전트_설계.md
// 3장·11장 참고.

/** 캘린더 "AI 추천 일정" 패널에 보여줄, 저장된 제안 목록. */
export async function listNextMeetingSuggestions(): Promise<ContractNextMeetingSuggestion[]> {
  const { data } = await client.get<ContractNextMeetingSuggestion[]>(
    '/contract-next-meeting-suggestions',
  )
  return data
}

/** 카드를 닫는다. 서버 상태를 dismissed로 남겨 다음 조회에도 다시 뜨지 않는다. */
export async function dismissNextMeetingSuggestion(salesDealId: string): Promise<void> {
  await client.post(`/contract-next-meeting-suggestions/${salesDealId}/dismiss`)
}

// 브리핑 실행은 별도로 트리거하지 않는다 — `POST /activities`에 schedule_management 실행
// id(`scheduleManagementRunId`)를 실어 보내면 서버가 등록 커밋 직후 자동으로 큐잉하고,
// 같은 요청 안에서 이 제안의 상태도 accepted로 바꾼다
// (backend/app/api/activities.py `create_activity`).
