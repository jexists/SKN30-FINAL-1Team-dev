import { useMemo } from 'react'

import type { SalesDeal } from '@/pages/Deals/useSalesDeals'

import { prevRange, resolveRange, type GroupBy, type PeriodType } from './periods'

export interface SalesGroup {
  key: string
  target: number
  actual: number
  share: number
  rate: number
  contracts: SalesDeal[]
}

export interface SalesSummary {
  groups: SalesGroup[]
  totals: {
    target: number
    actual: number
    gap: number
    rate: number
    count: number
  }
  prevActual: number
  delta: number
}

export const pct = (part: number, whole: number) => (whole > 0 ? (part / whole) * 100 : 0)

function keyOf(deal: SalesDeal, by: GroupBy): string {
  if (by === 'region') return deal.region
  if (by === 'product') return deal.product
  return deal.org
}

// 아래 세 함수는 추세선(useSalesTrend)도 그대로 씁니다. 어느 날짜를 계약일로 볼지,
// 무엇을 계약으로 셀지가 두 곳에서 갈리면 막대와 추세선이 다른 금액을 말하게 됩니다.

export function contractDate(deal: SalesDeal): string {
  return deal.contractSignedOn ?? deal.closedOn ?? deal.date
}

export function isContract(deal: SalesDeal): boolean {
  return deal.contractNo !== null || deal.stagePhase === 'contract' || deal.stagePhase === 'closed'
}

export function actualOf(deals: SalesDeal[]): number {
  return deals.reduce((sum, deal) => (deal.status === '확정' ? sum + deal.amount : sum), 0)
}

export default function useSalesSummary(
  deals: SalesDeal[],
  type: PeriodType,
  offset: number,
  by: GroupBy,
): SalesSummary {
  return useMemo(() => {
    const range = resolveRange(type, offset)
    const list = deals.filter((deal) => {
      const date = contractDate(deal)
      return isContract(deal) && date >= range.fromISO && date <= range.toISO
    })
    const actual = actualOf(list)
    const keys = new Set(list.map((deal) => keyOf(deal, by)))
    const groups = [...keys]
      .map((key) => {
        const contracts = list.filter((deal) => keyOf(deal, by) === key)
        const groupActual = actualOf(contracts)
        return {
          key,
          target: 0,
          actual: groupActual,
          share: pct(groupActual, actual),
          rate: 0,
          contracts,
        }
      })
      .sort((a, b) => b.actual - a.actual)

    const previous = prevRange(type, offset)
    const prevActual = actualOf(
      deals.filter((deal) => {
        const date = contractDate(deal)
        return isContract(deal) && date >= previous.fromISO && date <= previous.toISO
      }),
    )

    return {
      groups,
      totals: {
        target: 0,
        actual,
        gap: 0,
        rate: 0,
        count: list.length,
      },
      prevActual,
      delta: actual - prevActual,
    }
  }, [by, deals, offset, type])
}
