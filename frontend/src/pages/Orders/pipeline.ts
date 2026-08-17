// 발주 화면의 어휘입니다. 상태가 무엇이고 무슨 색으로 보이는지, 폼과 필터가
// 어떤 선택지를 내놓는지를 여기서 정합니다.
//
// 영업현황의 board.ts 와 달리 상태 집합은 데이터가 아니라 타입입니다. 발주 상태는
// 결재·생산·물류 흐름이라 화면에서 늘리고 줄일 수 있는 것이 아닙니다.
// (파일 이름이 orders.ts 가 아닌 이유: Orders.tsx 와 대소문자만 달라 충돌합니다.)
import type { ColumnTone, OrderStageCode, OrderStatus, Stage } from '@/types'

/** 상태 선택지. 타입에 적힌 순서가 곧 진행 순서입니다. 탭·정렬이 이 순서를 씁니다. */
export const ORDER_STATUSES: OrderStatus[] = [
  '발주 접수',
  '출고 의뢰서 완료',
  '생산중',
  '입고 완료',
  '납품 완료',
  '취소',
]

export const STATUS_BY_CODE: Record<OrderStageCode, OrderStatus> = {
  order_received: '발주 접수',
  dispatch_request_completed: '출고 의뢰서 완료',
  in_production: '생산중',
  stock_received: '입고 완료',
  delivered: '납품 완료',
  cancelled: '취소',
}

export const CODE_BY_STATUS: Record<OrderStatus, OrderStageCode> = {
  '발주 접수': 'order_received',
  '출고 의뢰서 완료': 'dispatch_request_completed',
  생산중: 'in_production',
  '입고 완료': 'stock_received',
  '납품 완료': 'delivered',
  취소: 'cancelled',
}

export const TONE_OF: Record<OrderStatus, ColumnTone> = {
  '발주 접수': 'gray',
  '출고 의뢰서 완료': 'purple',
  생산중: 'orange',
  '입고 완료': 'blue',
  '납품 완료': 'green',
  취소: 'red',
}

/** 단계 탭이 쓰는 어휘. 상태 하나가 곧 단계 하나입니다. */
export const ORDER_STAGES: Stage[] = ORDER_STATUSES.map((status) => ({
  id: status,
  name: status,
  tone: TONE_OF[status],
}))

/** 진행 스텝바가 보여 줄 다섯 칸 */
export const ORDER_STEPS: OrderStatus[] = ORDER_STATUSES.filter((status) => status !== '취소')

/** 상태가 놓이는 칸. 취소는 흐름 밖이라 -1 입니다. */
export const stepOf = (status: OrderStatus): number => ORDER_STEPS.indexOf(status)
