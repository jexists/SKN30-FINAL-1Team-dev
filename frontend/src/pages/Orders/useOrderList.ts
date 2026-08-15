// 백엔드가 붙는 지점은 이 파일 하나입니다. 화면은 아래 반환값만 알면 되므로
// 시드를 API 응답으로, 각 mutator 를 요청으로 바꾸면 나머지는 그대로 둘 수 있습니다.
//
// 상태를 모듈 수준에 두는 이유: 목록(/orders)·추가(/orders/new)·상세(/orders/:no)가
// 서로 다른 페이지라 훅 인스턴스가 따로 생깁니다. useState 로 두면 상세에서 고친 값이
// 목록으로 돌아왔을 때 사라집니다. 계약의 useContractBoard 와 같은 방식입니다.
import { useCallback, useSyncExternalStore } from 'react'

import type { OrderLine, OrderStatus, PurchaseOrder } from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import { initialOrders, nextOrderNo } from './pipeline'

let orders: PurchaseOrder[] = initialOrders()
const listeners = new Set<() => void>()

function publish(next: PurchaseOrder[]) {
  orders = next
  listeners.forEach((notify) => notify())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** 오늘로부터 며칠. isLate·dday 가 offset 을 보므로 저장할 때마다 다시 계산합니다. */
const offsetOf = (dateISO: string) =>
  Math.round((parseISO(dateISO).getTime() - TODAY.getTime()) / 86_400_000)

export interface OrderDraft {
  /** 연결된 계약번호. 비우면 계약 없는 선발주입니다. */
  contract: string
  hospital: string
  supplier: string
  status: OrderStatus
  /** YYYY-MM-DD */
  ordered: string
  due: string
  expect: string
  memo: string
  items: OrderLine[]
}

/** 초안을 저장 형태로. 날짜와 offset 이 늘 같은 값을 가리키게 합니다. */
function toOrder(no: string, draft: OrderDraft): PurchaseOrder {
  return {
    no,
    contract: draft.contract,
    hospital: draft.hospital,
    supplier: draft.supplier,
    status: draft.status,
    memo: draft.memo,
    items: draft.items,
    ordered: draft.ordered,
    due: draft.due,
    expect: draft.expect,
    orderedOff: offsetOf(draft.ordered),
    dueOff: offsetOf(draft.due),
    expectOff: offsetOf(draft.expect),
  }
}

export default function useOrderList() {
  const list = useSyncExternalStore(
    subscribe,
    () => orders,
    () => orders,
  )

  const findOrder = useCallback((no: string) => list.find((o) => o.no === no), [list])

  const addOrder = useCallback((draft: OrderDraft) => {
    const order = toOrder(nextOrderNo(orders), draft)
    // 새로 넣은 발주가 목록 아래로 묻히면 저장됐는지 알 수 없어 맨 위에 둡니다.
    publish([order, ...orders])
    return order.no
  }, [])

  const updateOrder = useCallback((no: string, draft: OrderDraft) => {
    publish(orders.map((o) => (o.no === no ? toOrder(no, draft) : o)))
  }, [])

  /** 상태만 바꿉니다. 상세에서 결재·출고를 넘길 때 폼 전체를 열 필요가 없습니다. */
  const setStatus = useCallback((no: string, status: OrderStatus) => {
    publish(orders.map((o) => (o.no === no ? { ...o, status } : o)))
  }, [])

  const removeOrder = useCallback((no: string) => {
    publish(orders.filter((o) => o.no !== no))
  }, [])

  return { orders: list, findOrder, addOrder, updateOrder, setStatus, removeOrder }
}
