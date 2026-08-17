// 영업 보드의 어휘입니다. 컬럼 집합은 API 데이터이며 각 컬럼의
// outcome으로 해당 딜의 진행 상태를 정합니다.
import { contracts as contractMocks } from '@/shared/contracts'
import { orders } from '@/shared/orders'
import type { ColumnTone, Contract, SalesDealStatus, Stage } from '@/types'

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

export const DEFAULT_COLUMNS: BoardColumn[] = [
  { id: 'needs', name: '니즈 검증', tone: 'gray', outcome: '진행중' },
  { id: 'demo', name: '제품 시연 평가', tone: 'blue', outcome: '진행중' },
  { id: 'quote', name: '견적서 발송', tone: 'purple', outcome: '진행중' },
  { id: 'sent', name: '계약서 발송', tone: 'orange', outcome: '진행중' },
  { id: 'reviewing', name: '계약서 검토', tone: 'orange', outcome: '진행중' },
  { id: 'won', name: '계약 완료', tone: 'green', outcome: '확정' },
  { id: 'delivered', name: '납품 완료', tone: 'green', outcome: '확정' },
  { id: 'lost', name: '취소', tone: 'red', outcome: '취소' },
]

/** 진행 스텝바가 쓰는 단계 차례. 취소는 흐름 밖이라 빠집니다. */
export const STAGE_ORDER: string[] = DEFAULT_COLUMNS.filter((column) => column.id !== 'lost').map(
  (column) => column.id,
)

export const STAGE_NAMES: string[] = DEFAULT_COLUMNS.filter((column) => column.id !== 'lost').map(
  (column) => column.name,
)

/** 이 단계가 몇 번째 칸인지. 모르는 단계·취소는 -1 입니다. */
export const stageIndexOf = (stageId: string): number => STAGE_ORDER.indexOf(stageId)

/** 새로 만든 컬럼의 기본 성격. */
export const NEW_COLUMN_OUTCOME: SalesDealStatus = '진행중'

/** 카드를 놓을 자리의 표식. `<컬럼 id>:<끼워 넣을 자리>` */
export const DROP_ATTR = 'data-drop-slot'

export const slotKey = (columnId: string, index: number) => `${columnId}:${index}`

export function parseSlot(key: string): { columnId: string; index: number } | null {
  const at = key.lastIndexOf(':')
  if (at < 0) return null
  const index = Number(key.slice(at + 1))
  return Number.isNaN(index) ? null : { columnId: key.slice(0, at), index }
}

// 아래 adapter는 대시보드 목업 표시만 위해 계약 목업을 영업 딜로 바꿉니다.
const PIPELINE = ['needs', 'demo', 'quote', 'sent', 'reviewing']
const DELIVERED_DEAL_NUMBERS = new Set(
  orders.filter((order) => order.status === '납품 완료').map((order) => order.contract),
)

function stageOf(contractMock: Contract, rankAmongOpen: number, openCount: number): string {
  if (contractMock.status === '확정') {
    return DELIVERED_DEAL_NUMBERS.has(contractMock.no) ? 'delivered' : 'won'
  }
  if (contractMock.status === '취소') return 'lost'
  const bucket = Math.floor((rankAmongOpen / Math.max(openCount, 1)) * PIPELINE.length)
  return PIPELINE[Math.min(bucket, PIPELINE.length - 1)]
}

export function initialDeals(): BoardDeal[] {
  const open = contractMocks.filter((item) => item.status === '진행중')
  const rank = new Map(open.map((item, index) => [item.no, index]))
  const counters = new Map<string, number>()

  return contractMocks.map((contractMock) => {
    const stageId = stageOf(contractMock, rank.get(contractMock.no) ?? 0, open.length)
    const order = counters.get(stageId) ?? 0
    counters.set(stageId, order + 1)
    return { ...contractMock, stageId, order }
  })
}
