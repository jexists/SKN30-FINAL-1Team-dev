// 영업 보드의 어휘입니다. 컬럼이 무엇이고, 시드 계약이 어느 컬럼에서 시작하며,
// 카드를 옮겼을 때 계약의 status 가 무엇이 되는지를 여기서 정합니다.
//
// 컬럼을 타입 유니온으로 두지 않은 이유: 화면에서 컬럼을 추가·삭제할 수 있어야 해서
// 컬럼 집합이 코드가 아니라 데이터입니다. 대신 컬럼마다 outcome 을 들고 있어
// 어느 컬럼에 놓이든 계약의 status 는 늘 정해집니다.
//
// 계약현황(/contracts)은 같은 계약을 계약 고유 5단계로 따로 봅니다. 두 화면은
// 단계 어휘가 다르므로 목록도 따로 들고 있습니다.
import { contracts } from '@/shared/contracts'
import { orders } from '@/shared/orders'
import type { ColumnTone, Contract, ContractStatus, Stage, StagedContract } from '@/types'

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
  /** 이 컬럼에 놓인 계약의 status. 매출로 잡히는지가('확정') 여기서 갈립니다. */
  outcome: ContractStatus
}

/** 보드가 다루는 계약. 계약에 보드 전용 자리 정보가 붙습니다. */
export interface BoardContract extends StagedContract {
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

/**
 * 진행 스텝바가 쓰는 단계 차례. 취소는 흐름 밖이라 빠집니다.
 * 컬럼은 화면에서 늘고 줄 수 있어 기본 컬럼에서 그때그때 뽑습니다.
 */
export const STAGE_ORDER: string[] = DEFAULT_COLUMNS.filter((c) => c.id !== 'lost').map((c) => c.id)

export const STAGE_NAMES: string[] = DEFAULT_COLUMNS.filter((c) => c.id !== 'lost').map(
  (c) => c.name,
)

/** 이 단계가 몇 번째 칸인지. 모르는 단계·취소는 -1 입니다. */
export const stageIndexOf = (stageId: string): number => STAGE_ORDER.indexOf(stageId)

/** 새로 만든 컬럼의 기본 성격. 확정·취소는 사람이 따로 정해야 하므로 진행중으로 둡니다. */
export const NEW_COLUMN_OUTCOME: ContractStatus = '진행중'

/**
 * 카드를 놓을 자리의 표식. `<컬럼 id>:<끼워 넣을 자리>` 를 담습니다.
 * 카드 하나가 곧 자리 하나라, 어떤 카드 위에 놓으면 그 카드 앞에 들어갑니다.
 */
export const DROP_ATTR = 'data-drop-slot'

export const slotKey = (columnId: string, index: number) => `${columnId}:${index}`

export function parseSlot(key: string): { columnId: string; index: number } | null {
  const at = key.lastIndexOf(':')
  if (at < 0) return null
  const index = Number(key.slice(at + 1))
  return Number.isNaN(index) ? null : { columnId: key.slice(0, at), index }
}

/** 진행중 계약이 처음 놓일 컬럼. 뒤로 갈수록 계약에 가깝습니다. */
const PIPELINE = ['needs', 'demo', 'quote', 'sent', 'reviewing']

/** 납품까지 끝난 발주가 걸린 계약번호. 확정 건을 계약 완료와 납품 완료로 가릅니다. */
const DELIVERED_CONTRACTS = new Set(
  orders.filter((o) => o.status === '납품 완료').map((o) => o.contract),
)

/**
 * 시드에는 확정·진행중·취소 세 가지밖에 없어 진행중 건을 앞 다섯 컬럼에 나눠 놓습니다.
 * 협의를 시작한 지 오래된 건일수록 뒤 단계에 있다고 봅니다.
 *
 * 무작위가 아니라 날짜 순서로 나눕니다. 시연할 때마다 보드가 달라지면 곤란합니다.
 */
function stageOf(contract: Contract, rankAmongOpen: number, openCount: number): string {
  if (contract.status === '확정') {
    return DELIVERED_CONTRACTS.has(contract.no) ? 'delivered' : 'won'
  }
  if (contract.status === '취소') return 'lost'
  const bucket = Math.floor((rankAmongOpen / Math.max(openCount, 1)) * PIPELINE.length)
  return PIPELINE[Math.min(bucket, PIPELINE.length - 1)]
}

/** 시드를 보드 카드로 바꿉니다. 컬럼 안에서는 계약일 내림차순입니다. */
export function initialCards(): BoardContract[] {
  // contracts 는 이미 계약일 내림차순이라 그 안에서의 순번이 곧 최신순 순번입니다.
  const open = contracts.filter((c) => c.status === '진행중')
  const rank = new Map(open.map((c, index) => [c.no, index]))

  const counters = new Map<string, number>()

  return contracts.map((contract) => {
    const stageId = stageOf(contract, rank.get(contract.no) ?? 0, open.length)
    const order = counters.get(stageId) ?? 0
    counters.set(stageId, order + 1)
    return { ...contract, stageId, order }
  })
}

/** 다음 계약번호. 올해 번호 중 가장 큰 것에 1 을 더합니다. */
export function nextContractNo(list: BoardContract[]): string {
  const year = new Date().getFullYear()
  const prefix = `FM-CT-${year}-`
  const last = list.reduce((max, c) => {
    if (!c.no.startsWith(prefix)) return max
    const n = Number(c.no.slice(prefix.length))
    return Number.isNaN(n) ? max : Math.max(max, n)
  }, 0)
  return `${prefix}${String(last + 1).padStart(4, '0')}`
}
