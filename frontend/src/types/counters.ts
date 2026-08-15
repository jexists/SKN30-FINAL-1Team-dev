// 대시보드 요약 밴드가 세는 것들. 후속·CS·갱신은 각자 화면이 없어 여기 모여 있습니다.

export interface FollowUp {
  /** 담당 영업 */
  owner: string
  task: string
  org: string
  who: string
  note: string
  dueOff: number
}

export type CsState = '처리중' | '처리완료'

export interface CsRequest {
  id: string
  /** 담당 영업 */
  owner: string
  issue: string
  org: string
  /** 접수한 사람. 화면에서 등록한 건은 비어 있습니다. */
  who: string
  /** 문제가 난 제품. 화면에서 등록한 건은 비어 있습니다. */
  product: string
  state: CsState
  urgent: boolean
  agoOff: number
  ago: string
  note: string
}

export interface Renewal {
  /** 담당 영업 */
  owner: string
  org: string
  who: string
  contract: string
  kind: string
  amount: number
  expireOff: number
  note: string
}
