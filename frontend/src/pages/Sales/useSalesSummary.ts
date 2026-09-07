import { useMemo } from 'react'

import type { SalesDeal } from '@/pages/Deals/useSalesDeals'

import { prevRange, resolveRange, type GroupBy, type PeriodType } from './periods'

/** 한 사람이 이 묶음에서 세운 매출. 선택한 그룹의 담당자 상세가 이 값을 씁니다. */
export interface OwnerShare {
  memberId: string
  name: string
  actual: number
  count: number
}

export interface SalesGroup {
  key: string
  target: number
  actual: number
  share: number
  rate: number
  contracts: SalesDeal[]
  /** 이 묶음을 누가 얼마나 세웠는지. 금액 내림차순입니다. */
  owners: OwnerShare[]
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
  /** 이 기간 전체를 누가 얼마나 세웠는지. 금액 내림차순입니다. */
  owners: OwnerShare[]
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

/**
 * 계약 목록을 담당자별로 갈라 놓습니다.
 *
 * 금액은 그룹 합계와 같은 규칙(확정만)으로 셉니다. 여기만 진행중까지 더하면 담당자
 * 금액을 합쳐도 위의 총액이 나오지 않아 두 숫자가 서로를 부정하게 됩니다.
 * 건수는 확정이 아닌 것까지 셉니다. 목록에 서 있는 줄 수와 같아야 하기 때문입니다.
 */
export function ownerShares(deals: SalesDeal[]): OwnerShare[] {
  const byMember = new Map<string, OwnerShare>()
  for (const deal of deals) {
    const found = byMember.get(deal.ownerMemberId)
    const share = found ?? { memberId: deal.ownerMemberId, name: deal.owner, actual: 0, count: 0 }
    if (deal.status === '확정') share.actual += deal.amount
    share.count += 1
    if (found === undefined) byMember.set(deal.ownerMemberId, share)
  }
  return [...byMember.values()].sort((a, b) => b.actual - a.actual)
}

/** 기간·그룹 기준에 맞춘 순수 집계. 화면과 검증 코드가 같은 계산을 씁니다. */
export function salesSummaryOf(
  deals: SalesDeal[],
  type: PeriodType,
  offset: number,
  by: GroupBy,
): SalesSummary {
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
        owners: ownerShares(contracts),
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
    owners: ownerShares(list),
  }
}

export default function useSalesSummary(
  deals: SalesDeal[],
  type: PeriodType,
  offset: number,
  by: GroupBy,
): SalesSummary {
  return useMemo(() => salesSummaryOf(deals, type, offset, by), [by, deals, offset, type])
}
