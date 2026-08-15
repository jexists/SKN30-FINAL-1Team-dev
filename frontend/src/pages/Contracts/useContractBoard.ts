// 백엔드가 붙는 지점은 이 파일 하나입니다. 화면은 아래 반환값만 알면 되므로
// 시드를 API 응답으로, 각 mutator 를 요청으로 바꾸면 나머지는 그대로 둘 수 있습니다.
//
// 상태를 모듈 수준에 두는 이유: 보드(/contracts)와 상세(/contracts/:no)가 서로 다른
// 페이지라 훅 인스턴스가 따로 생깁니다. useState 로 두면 상세에서 고친 값이
// 보드로 돌아왔을 때 사라집니다.
import { useCallback, useMemo, useSyncExternalStore } from 'react'

import { regionOf } from '@/shared/regions'
import type { ContractKind } from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import {
  DEFAULT_COLUMNS,
  initialCards,
  NEW_COLUMN_OUTCOME,
  nextContractNo,
  type BoardColumn,
  type BoardContract,
  type ColumnTone,
} from './board'

interface Board {
  columns: BoardColumn[]
  cards: BoardContract[]
}

let board: Board = { columns: DEFAULT_COLUMNS, cards: initialCards() }
const listeners = new Set<() => void>()

function publish(next: Board) {
  board = next
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 컬럼 안의 카드를 order 순으로. 화면과 이동 계산이 같은 순서를 봅니다. */
function cardsOf(cards: BoardContract[], columnId: string): BoardContract[] {
  return cards.filter((c) => c.stageId === columnId).sort((a, b) => a.order - b.order)
}

/** 한 컬럼의 order 를 0,1,2… 로 다시 매깁니다. 이동 뒤에는 늘 이걸 거칩니다. */
function renumber(list: BoardContract[], columnId: string, outcome: BoardColumn['outcome']) {
  return list.map((card, order) => ({ ...card, stageId: columnId, order, status: outcome }))
}

export interface ContractDraft {
  org: string
  product: string
  amount: number
  kind: ContractKind
  owner: string
  /** YYYY-MM-DD */
  date: string
  memo: string
}

export default function useContractBoard() {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => board,
    () => board,
  )

  const { columns, cards } = snapshot

  // 컬럼 → 그 컬럼의 카드. 보드가 컬럼마다 목록과 합계를 그리는 데 씁니다.
  const byColumn = useMemo(() => {
    const map = new Map<string, BoardContract[]>()
    for (const column of columns) map.set(column.id, cardsOf(cards, column.id))
    return map
  }, [columns, cards])

  const findContract = useCallback((no: string) => cards.find((c) => c.no === no), [cards])

  /**
   * 카드를 옮깁니다. 컬럼 이동과 같은 컬럼 안 재정렬을 하나로 다룹니다.
   * 놓인 컬럼이 계약의 status 를 정하므로 옮길 때마다 다시 매깁니다.
   */
  const moveCard = useCallback((no: string, toColumnId: string, toIndex: number) => {
    const card = board.cards.find((c) => c.no === no)
    const target = board.columns.find((col) => col.id === toColumnId)
    if (!card || !target) return

    const fromColumnId = card.stageId
    const source = cardsOf(board.cards, fromColumnId).filter((c) => c.no !== no)

    if (fromColumnId === toColumnId) {
      // 같은 컬럼에서 아래로 옮길 때는 자기 자신이 빠진 만큼 자리가 하나 당겨집니다.
      // 그대로 넣으면 가리킨 카드보다 한 칸 더 내려갑니다.
      const fromIndex = cardsOf(board.cards, fromColumnId).findIndex((c) => c.no === no)
      const wanted = fromIndex < toIndex ? toIndex - 1 : toIndex
      const clamped = Math.min(Math.max(wanted, 0), source.length)
      source.splice(clamped, 0, card)
      const moved = renumber(source, toColumnId, target.outcome)
      publish({
        ...board,
        cards: board.cards.map((c) => moved.find((m) => m.no === c.no) ?? c),
      })
      return
    }

    const destination = cardsOf(board.cards, toColumnId)
    const clamped = Math.min(Math.max(toIndex, 0), destination.length)
    destination.splice(clamped, 0, card)

    const fromColumn = board.columns.find((col) => col.id === fromColumnId)
    const moved = [
      ...renumber(source, fromColumnId, fromColumn?.outcome ?? card.status),
      ...renumber(destination, toColumnId, target.outcome),
    ]
    publish({
      ...board,
      cards: board.cards.map((c) => moved.find((m) => m.no === c.no) ?? c),
    })
  }, [])

  const addContract = useCallback((draft: ContractDraft, columnId: string) => {
    const column = board.columns.find((col) => col.id === columnId) ?? board.columns[0]
    const card: BoardContract = {
      no: nextContractNo(board.cards),
      org: draft.org,
      product: draft.product,
      amount: draft.amount,
      kind: draft.kind,
      owner: draft.owner,
      status: column.outcome,
      date: draft.date,
      // 시드와 타입을 공유하므로 오늘 기준 일수도 채워 둡니다.
      signedOff: Math.round((parseISO(draft.date).getTime() - TODAY.getTime()) / 86_400_000),
      region: regionOf(draft.org),
      stageId: column.id,
      // 새로 넣은 카드가 목록 아래로 묻히면 저장됐는지 알 수 없어 맨 위에 둡니다.
      order: -1,
      memo: draft.memo,
    }

    const rest = cardsOf(board.cards, column.id)
    const moved = renumber([card, ...rest], column.id, column.outcome)
    publish({
      ...board,
      cards: [...moved, ...board.cards.filter((c) => c.stageId !== column.id)],
    })
    return card.no
  }, [])

  const updateContract = useCallback((no: string, draft: ContractDraft) => {
    publish({
      ...board,
      cards: board.cards.map((c) =>
        c.no === no
          ? {
              ...c,
              ...draft,
              signedOff: Math.round(
                (parseISO(draft.date).getTime() - TODAY.getTime()) / 86_400_000,
              ),
              region: regionOf(draft.org),
            }
          : c,
      ),
    })
  }, [])

  const removeContract = useCallback((no: string) => {
    publish({ ...board, cards: board.cards.filter((c) => c.no !== no) })
  }, [])

  const renameColumn = useCallback((id: string, name: string) => {
    publish({
      ...board,
      columns: board.columns.map((col) => (col.id === id ? { ...col, name } : col)),
    })
  }, [])

  const recolorColumn = useCallback((id: string, tone: ColumnTone) => {
    publish({
      ...board,
      columns: board.columns.map((col) => (col.id === id ? { ...col, tone } : col)),
    })
  }, [])

  /** afterId 오른쪽에 넣습니다. 주지 않으면 맨 끝입니다. */
  const addColumn = useCallback((name: string, tone: ColumnTone, afterId?: string) => {
    const id = `col-${Date.now().toString(36)}`
    const column: BoardColumn = { id, name, tone, outcome: NEW_COLUMN_OUTCOME }
    const at = afterId ? board.columns.findIndex((col) => col.id === afterId) + 1 : -1
    const columns = [...board.columns]
    if (at > 0) columns.splice(at, 0, column)
    else columns.push(column)
    publish({ ...board, columns })
    return id
  }, [])

  /**
   * 컬럼을 지웁니다. 남은 카드는 moveToId 컬럼으로 옮깁니다.
   * 마지막 컬럼은 지우지 않습니다. 카드를 둘 곳이 없어집니다.
   */
  const removeColumn = useCallback((id: string, moveToId: string) => {
    if (board.columns.length <= 1) return
    const target = board.columns.find((col) => col.id === moveToId)
    if (!target || target.id === id) return

    const moving = cardsOf(board.cards, id)
    const merged = renumber(
      [...cardsOf(board.cards, moveToId), ...moving],
      moveToId,
      target.outcome,
    )

    publish({
      columns: board.columns.filter((col) => col.id !== id),
      cards: [...board.cards.filter((c) => c.stageId !== id && c.stageId !== moveToId), ...merged],
    })
  }, [])

  return {
    columns,
    cards,
    /** 컬럼 id → 그 컬럼의 카드 (order 순) */
    byColumn,
    findContract,
    moveCard,
    addContract,
    updateContract,
    removeContract,
    renameColumn,
    recolorColumn,
    addColumn,
    removeColumn,
  }
}
