import type { Contract } from '@/types'

export const contracts: Contract[] = []

export function contractsIn(fromISO: string, toISO: string): Contract[] {
  return contracts.filter((contract) => contract.date >= fromISO && contract.date <= toISO)
}

export function confirmedTotal(list: Contract[]): number {
  return list.reduce(
    (sum, contract) => (contract.status === '확정' ? sum + contract.amount : sum),
    0,
  )
}
