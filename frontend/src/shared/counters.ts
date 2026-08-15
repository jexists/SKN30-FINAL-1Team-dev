// 후속·CS·갱신·매출목표 도메인. 후속·갱신·목표는 전부 시드라 mocks/ 를 그대로 내보냅니다.
//
// CS(고객불만)만 스토어입니다. 대시보드 C/S 대응요청 타일과 고객불만관리 화면이 같은
// 목록을 봐야 해서, 목록을 이 모듈 하나에 두고 화면은 아래 훅으로 구독합니다.
// shared/agenda.ts 가 대시보드와 캘린더를 묶은 방식과 같습니다.
//
// 백엔드가 붙는 지점은 addCsRequest / setCsState 둘입니다. 저장은 메모리에만 합니다.
import { useSyncExternalStore } from 'react'

import { csRequests as csSeed } from '@/mocks'
import type { CsRequest, CsState } from '@/types'

export { followUps, renewals, salesGoal } from '@/mocks'

/** 접수가 최근인 건이 위로 옵니다. 목록·드로어가 같은 순서를 씁니다. */
let items: CsRequest[] = [...csSeed].sort((a, b) => b.agoOff - a.agoOff)

const listeners = new Set<() => void>()

function commit(next: CsRequest[]) {
  items = next
  for (const notify of listeners) notify()
}

export function subscribeCs(notify: () => void) {
  listeners.add(notify)
  return () => {
    listeners.delete(notify)
  }
}

export function csSnapshot(): CsRequest[] {
  return items
}

/** 화면에서 받는 값. 나머지 칸은 아래에서 채웁니다. */
export interface CsDraft {
  issue: string
  org: string
  owner: string
  product: string
  note: string
  state: CsState
  /** 대시보드 C/S 타일의 '긴급 N건' 이 이 값을 셉니다. */
  urgent: boolean
}

// Date.now() 는 같은 밀리초 안에 두 번 부르면 같은 값이 나옵니다. id 가 겹치면
// 상태 변경이 엉뚱한 건을 바꾸므로 증가하는 번호를 씁니다.
let seq = 0

/**
 * 새 불만. 화면에서 만든 건에는 시드가 들고 있는 접수자가 없습니다.
 * 빈 값으로 두면 목록과 드로어가 그 칸을 아예 그리지 않습니다.
 */
export function addCsRequest(draft: CsDraft): CsRequest {
  const item: CsRequest = {
    ...draft,
    id: `cs-new-${++seq}`,
    who: '',
    agoOff: 0,
    ago: '방금 접수',
  }
  commit([item, ...items])
  return item
}

export function setCsState(id: string, state: CsState) {
  commit(items.map((item) => (item.id === id ? { ...item, state } : item)))
}

/** 목록이 바뀌면 다시 그립니다. */
export function useCsRequests(): CsRequest[] {
  return useSyncExternalStore(subscribeCs, csSnapshot)
}
