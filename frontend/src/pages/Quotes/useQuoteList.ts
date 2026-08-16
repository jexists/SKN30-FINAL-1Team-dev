// 백엔드가 붙는 지점은 이 파일 하나입니다. 화면은 아래 반환값만 알면 되므로
// 시드를 API 응답으로, 각 mutator 를 요청으로 바꾸면 나머지는 그대로 둘 수 있습니다.
//
// 상태를 모듈 수준에 두는 까닭은 계약의 useContractList 와 같습니다.
import { useCallback, useSyncExternalStore } from 'react'

import { quotes as seed } from '@/shared/quotes'
import type { Quote, QuoteStageId } from '@/types'
import { addDays, iso, parseISO, TODAY } from '@/utils/date'

import { nextQuoteNo } from './stages'

let list: Quote[] = [...seed]
const listeners = new Set<() => void>()

function publish(next: Quote[]) {
  list = next
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export interface QuoteDraft {
  org: string
  product: string
  amount: number
  kind: Quote['kind']
  owner: string
  stageId: QuoteStageId
  /** YYYY-MM-DD */
  date: string
  validDays: number
}

/** 시드와 같은 형태를 지키도록 날짜에서 상대 일수를 되짚습니다. */
const offsetOf = (dateISO: string) =>
  Math.round((parseISO(dateISO).getTime() - TODAY.getTime()) / 86_400_000)

/** 견적일과 유효일수에서 파생되는 것들. 넣을 때나 고칠 때나 같은 규칙을 씁니다. */
const resolve = (draft: QuoteDraft) => {
  const issuedOff = offsetOf(draft.date)
  return {
    issuedOff,
    validUntil: iso(addDays(TODAY, issuedOff + draft.validDays)),
  }
}

export default function useQuoteList() {
  const quotes = useSyncExternalStore(
    subscribe,
    () => list,
    () => list,
  )

  const findQuote = useCallback((no: string) => quotes.find((q) => q.no === no), [quotes])

  const addQuote = useCallback((draft: QuoteDraft) => {
    const quote: Quote = { no: nextQuoteNo(list), ...draft, ...resolve(draft) }
    // 새로 넣은 견적이 목록 아래로 묻히면 저장됐는지 알 수 없어 맨 위에 둡니다.
    publish([quote, ...list])
    return quote.no
  }, [])

  const updateQuote = useCallback((no: string, draft: QuoteDraft) => {
    publish(list.map((q) => (q.no === no ? { ...q, ...draft, ...resolve(draft) } : q)))
  }, [])

  const removeQuote = useCallback((no: string) => {
    publish(list.filter((q) => q.no !== no))
  }, [])

  return { quotes, findQuote, addQuote, updateQuote, removeQuote }
}
