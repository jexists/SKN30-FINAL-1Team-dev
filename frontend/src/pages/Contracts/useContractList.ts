// 백엔드가 붙는 지점은 이 파일 하나입니다. 화면은 아래 반환값만 알면 되므로
// 시드를 API 응답으로, 각 mutator 를 요청으로 바꾸면 나머지는 그대로 둘 수 있습니다.
//
// 상태를 모듈 수준에 두는 이유: 목록(/contracts)·추가(/contracts/new)·상세(/contracts/:no)가
// 서로 다른 페이지라 훅 인스턴스가 따로 생깁니다. useState 로 두면 상세에서 고친 값이
// 목록으로 돌아왔을 때 사라집니다. 발주의 useOrderList 와 같은 방식입니다.
//
// 영업현황(/deals)은 같은 시드를 저마다의 단계로 따로 들고 있습니다. 두 화면이 보는
// 단계 어휘가 달라 한 목록으로는 담기지 않습니다.
import { useCallback, useSyncExternalStore } from 'react'

import { regionOf } from '@/shared/regions'
import type { ContractDraft, StagedContract } from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import { initialContracts, nextContractNo, stageById } from './stages'

let list: StagedContract[] = initialContracts()
const listeners = new Set<() => void>()

function publish(next: StagedContract[]) {
  list = next
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 계약일이 바뀌면 시드와 같은 형태를 지키도록 offset 도 다시 잽니다. */
const offsetOf = (dateISO: string) =>
  Math.round((parseISO(dateISO).getTime() - TODAY.getTime()) / 86_400_000)

export default function useContractList() {
  const contracts = useSyncExternalStore(
    subscribe,
    () => list,
    () => list,
  )

  const findContract = useCallback((no: string) => contracts.find((c) => c.no === no), [contracts])

  const addContract = useCallback((draft: ContractDraft, stageId: string) => {
    const stage = stageById(stageId) ?? stageById('draft')!
    const contract: StagedContract = {
      no: nextContractNo(list),
      ...draft,
      status: stage.outcome,
      signedOff: offsetOf(draft.date),
      region: regionOf(draft.org),
      stageId: stage.id,
    }
    // 새로 넣은 계약이 목록 아래로 묻히면 저장됐는지 알 수 없어 맨 위에 둡니다.
    publish([contract, ...list])
    return contract.no
  }, [])

  const updateContract = useCallback((no: string, draft: ContractDraft) => {
    publish(
      list.map((c) =>
        c.no === no
          ? { ...c, ...draft, signedOff: offsetOf(draft.date), region: regionOf(draft.org) }
          : c,
      ),
    )
  }, [])

  /** 단계를 옮깁니다. 놓인 단계가 계약의 status 를 정하므로 함께 다시 매깁니다. */
  const setStage = useCallback((no: string, stageId: string) => {
    const stage = stageById(stageId)
    if (!stage) return
    publish(list.map((c) => (c.no === no ? { ...c, stageId, status: stage.outcome } : c)))
  }, [])

  const removeContract = useCallback((no: string) => {
    publish(list.filter((c) => c.no !== no))
  }, [])

  return { contracts, findContract, addContract, updateContract, setStage, removeContract }
}
