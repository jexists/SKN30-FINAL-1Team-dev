// 계약 화면의 어휘입니다. 계약서 한 장이 초안에서 서명까지 지나는 다섯 단계를 둡니다.
//
// 영업 파이프라인(니즈 검증 → 납품 완료)은 영업현황(/deals)이 갖습니다. 여기는
// 계약서 자체의 진행이라 취소 칸을 두지 않습니다. 엎어진 건은 영업현황에서 봅니다.
//
// 영업현황의 board.ts 와 달리 단계 집합은 데이터가 아니라 상수입니다. 계약서가 지나는
// 절차라 화면에서 늘리고 줄일 것이 아닙니다.
import { contracts } from '@/shared/contracts'
import type { Contract, ContractStatus, Stage, StagedContract } from '@/types'

export interface ContractStage extends Stage {
  /** 이 단계에 놓인 계약의 status. 매출로 잡히는지가('확정') 여기서 갈립니다. */
  outcome: ContractStatus
}

export const CONTRACT_STAGES: ContractStage[] = [
  { id: 'draft', name: '초안작성', tone: 'gray', outcome: '진행중' },
  { id: 'review', name: '계약검토', tone: 'blue', outcome: '진행중' },
  { id: 'negotiate', name: '고객협의', tone: 'orange', outcome: '진행중' },
  { id: 'signing', name: '고객서명', tone: 'purple', outcome: '진행중' },
  { id: 'done', name: '계약완료', tone: 'green', outcome: '확정' },
]

export const stageById = (id: string): ContractStage | undefined =>
  CONTRACT_STAGES.find((stage) => stage.id === id)

/** 아직 서명 전인 단계. 진행중 계약을 여기에 나눠 놓습니다. */
const OPEN_STAGES = CONTRACT_STAGES.filter((stage) => stage.id !== 'done').map((s) => s.id)

/**
 * 시드에는 확정·진행중·취소 세 가지밖에 없어 서명 전 건을 앞 네 단계에 나눠 놓습니다.
 * 협의를 시작한 지 오래된 건일수록 뒤 단계에 있다고 봅니다.
 *
 * 무작위가 아니라 날짜 순서로 나눕니다. 시연할 때마다 목록이 달라지면 곤란합니다.
 */
function stageOf(contract: Contract, rankAmongOpen: number, openCount: number): string {
  if (contract.status === '확정') return 'done'
  const bucket = Math.floor((rankAmongOpen / Math.max(openCount, 1)) * OPEN_STAGES.length)
  return OPEN_STAGES[Math.min(bucket, OPEN_STAGES.length - 1)]
}

/** 시드를 목록의 초기 상태로. 계약일 내림차순은 contracts 가 이미 지키고 있습니다. */
export function initialContracts(): StagedContract[] {
  // 취소된 건도 계약서는 썼으므로 서명 전 단계에 함께 섞입니다.
  const open = contracts.filter((c) => c.status !== '확정')
  const rank = new Map(open.map((c, index) => [c.no, index]))

  return contracts.map((contract) => ({
    ...contract,
    stageId: stageOf(contract, rank.get(contract.no) ?? 0, open.length),
  }))
}

/** 다음 계약번호. 올해 번호 중 가장 큰 것에 1 을 더합니다. */
export function nextContractNo(list: StagedContract[]): string {
  const year = new Date().getFullYear()
  const prefix = `FM-CT-${year}-`
  const last = list.reduce((max, c) => {
    if (!c.no.startsWith(prefix)) return max
    const n = Number(c.no.slice(prefix.length))
    return Number.isNaN(n) ? max : Math.max(max, n)
  }, 0)
  return `${prefix}${String(last + 1).padStart(4, '0')}`
}
