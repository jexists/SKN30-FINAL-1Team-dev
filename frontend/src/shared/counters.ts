import type { CsRequest, CsState, FollowUp, Renewal } from '@/types'

export const followUps: FollowUp[] = []
export const renewals: Renewal[] = []

const items: CsRequest[] = []

export function subscribeCs(_notify: () => void) {
  return () => undefined
}

export function csSnapshot(): CsRequest[] {
  return items
}

export interface CsDraft {
  issue: string
  org: string
  owner: string
  product: string
  note: string
  state: CsState
  urgent: boolean
}

export function addCsRequest(_draft: CsDraft): CsRequest {
  throw new Error('고객불만 변경은 지원요청 API 훅을 사용해야 합니다.')
}

export function setCsState(_id: string, _state: CsState) {
  // 레거시 호출부를 위한 no-op입니다. 실행 화면은 지원요청 API 훅을 사용합니다.
}

export function useCsRequests(): CsRequest[] {
  return items
}
