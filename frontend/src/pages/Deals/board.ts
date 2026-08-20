// 영업 보드의 어휘입니다. 컬럼 집합은 API 데이터이며 각 컬럼의
// outcome으로 해당 딜의 진행 상태를 정합니다.
import type { ColumnTone, SalesDealStatus, Stage } from '@/types'

/** 색 고르개가 보여 줄 순서 */
export const TONES: ColumnTone[] = ['gray', 'blue', 'purple', 'orange', 'green', 'red']

export const TONE_LABEL: Record<ColumnTone, string> = {
  gray: '회색',
  blue: '파랑',
  purple: '보라',
  orange: '주황',
  green: '초록',
  red: '빨강',
}

export interface BoardColumn extends Stage {
  /** 이 컬럼에 놓인 딜의 status. '확정'만 매출로 잡힙니다. */
  outcome: SalesDealStatus
}

/** 보드가 다루는 영업 딜 표시 모델. */
export interface BoardDeal {
  no: string
  org: string
  product: string
  amount: number
  kind: string
  status: SalesDealStatus
  signedOff: number
  owner: string
  date: string
  region: string
  memo?: string
  stageId: string
  /** 컬럼 안에서의 자리. 낮을수록 위 */
  order: number
}

/** 카드를 놓을 자리의 표식. `<컬럼 id>:<끼워 넣을 자리>` */
export const DROP_ATTR = 'data-drop-slot'

export const slotKey = (columnId: string, index: number) => `${columnId}:${index}`

export function parseSlot(key: string): { columnId: string; index: number } | null {
  const at = key.lastIndexOf(':')
  if (at < 0) return null
  const index = Number(key.slice(at + 1))
  return Number.isNaN(index) ? null : { columnId: key.slice(0, at), index }
}
