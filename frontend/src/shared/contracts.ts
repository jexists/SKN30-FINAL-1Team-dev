import type { Contract, ContractKind } from '@/types'

export const contracts: Contract[] = []
export const KINDS: ContractKind[] = ['신규 도입', '증설', '갱신', '유지보수', '소모품 공급']
export const OWNERS: string[] = []
export const ORGS: string[] = []
export const PRODUCTS: string[] = []

export function contractsIn(fromISO: string, toISO: string): Contract[] {
  return contracts.filter((contract) => contract.date >= fromISO && contract.date <= toISO)
}

export function confirmedTotal(list: Contract[]): number {
  return list.reduce(
    (sum, contract) => (contract.status === '확정' ? sum + contract.amount : sum),
    0,
  )
}
