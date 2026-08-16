// 기간 하나를 회사별 또는 지역별로 접은 결과. 표와 차트가 이 하나를 나눠 씁니다.
//
// 숫자를 상수로 두지 않고 계약 목록에서 매번 파생시킵니다. 그래야 표의 합계와
// 오른쪽 목표 패널이 어긋날 수 없습니다.
import { useMemo } from 'react'

import { confirmedTotal, contractsIn } from '@/shared/contracts'
import { REGIONS } from '@/shared/regions'
import { monthlyTargetByOrg, targetFor, targetForRegion, totalTarget } from '@/shared/salesTargets'
import type { Contract } from '@/types'

import { prevRange, resolveRange, type GroupBy, type PeriodType } from './periods'

export interface SalesGroup {
  /** 회사명 또는 지역명 */
  key: string
  target: number
  /** 확정 계약 합계 */
  actual: number
  /** 전체 실적 대비 비중(%) */
  share: number
  /** 달성률(%). 목표가 0이면 0 입니다. */
  rate: number
  /** 펼쳤을 때 보여 줄 계약. 진행중·취소도 들어 있습니다. */
  contracts: Contract[]
}

export interface SalesSummary {
  groups: SalesGroup[]
  totals: {
    target: number
    actual: number
    /** 목표 − 실적. 양수면 그만큼 모자랍니다. */
    gap: number
    rate: number
    /** 계약 건수. 진행중·취소를 포함한 전체입니다. */
    count: number
  }
  prevActual: number
  /** 직전 같은 기간과의 실적 차이 */
  delta: number
}

/** 실적이 0인 기간에도 NaN 이 화면에 뜨지 않게 합니다. */
export const pct = (part: number, whole: number) => (whole > 0 ? (part / whole) * 100 : 0)

/**
 * 목표가 있는 축은 실적이 0이어도 자리를 지킵니다. 팔지 못한 회사·지역이 표에서
 * 사라지면 안 되기 때문입니다. 상품은 목표가 없으므로 그 기간에 판 것만 나옵니다.
 */
function keysFor(by: GroupBy): string[] {
  const orgs = Object.keys(monthlyTargetByOrg)
  // 첫 세팅에는 목표를 정해 둔 회사가 하나도 없습니다. 축을 세울 근거가 없으므로
  // 회사도 지역도 만들지 않습니다. 빈 계정에 병원 이름이 떠 있으면 안 됩니다.
  if (orgs.length === 0) return []
  if (by === 'region') return [...REGIONS]
  if (by === 'product') return []
  return orgs
}

function keyOf(contract: Contract, by: GroupBy): string {
  if (by === 'region') return contract.region
  if (by === 'product') return contract.product
  return contract.org
}

/** 상품에는 매출 목표가 없습니다. 없는 목표를 0으로 두고 달성률도 말하지 않습니다. */
function targetOf(key: string, by: GroupBy, fromISO: string, toISO: string): number {
  if (by === 'region') return targetForRegion(key, fromISO, toISO)
  if (by === 'product') return 0
  return targetFor(key, fromISO, toISO)
}

/** 기간은 type·offset 에서 곧바로 나옵니다(resolveRange 는 순수 함수). */
export default function useSalesSummary(
  type: PeriodType,
  offset: number,
  by: GroupBy,
): SalesSummary {
  return useMemo(() => {
    const range = resolveRange(type, offset)
    const list = contractsIn(range.fromISO, range.toISO)
    const actual = confirmedTotal(list)
    const target = totalTarget(range.fromISO, range.toISO)

    // 매핑에 없는 회사·지역이 있어도 계약이 집계에서 빠지지 않게 목록에서도 키를 모읍니다.
    const seen = new Set(keysFor(by))
    for (const c of list) seen.add(keyOf(c, by))

    const groups: SalesGroup[] = [...seen]
      .map((key) => {
        const mine = list.filter((c) => keyOf(c, by) === key)
        const groupActual = confirmedTotal(mine)
        const groupTarget = targetOf(key, by, range.fromISO, range.toISO)

        return {
          key,
          target: groupTarget,
          actual: groupActual,
          share: pct(groupActual, actual),
          rate: pct(groupActual, groupTarget),
          contracts: mine,
        }
      })
      .sort((a, b) => b.actual - a.actual)

    const prev = prevRange(type, offset)
    const prevActual = confirmedTotal(contractsIn(prev.fromISO, prev.toISO))

    return {
      groups,
      totals: {
        target,
        actual,
        gap: target - actual,
        rate: pct(actual, target),
        count: list.length,
      },
      prevActual,
      delta: actual - prevActual,
    }
  }, [type, offset, by])
}
