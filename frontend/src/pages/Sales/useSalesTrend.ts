// 같은 기간 단위로 뒤로 몇 칸을 훑어 매출 흐름을 만듭니다.
//
// 화면이 이미 받아 둔 계약 목록만 씁니다. 기간마다 서버를 부르면 탭을 누를 때마다
// 대여섯 번 왕복하게 되는데, 계약 건수 규모에서는 클라이언트 합산이 더 쌉니다.
import { useMemo } from 'react'

import type { SalesDeal } from '@/pages/Deals/useSalesDeals'

import { resolveRange, type PeriodType } from './periods'
import { actualOf, contractDate, isContract } from './useSalesSummary'

export interface TrendPoint {
  /** 현재 기간이 0, 직전이 -1 */
  offset: number
  /** "2026년 8월" 처럼 기간 이름. 짚어 볼 때 뜹니다. */
  label: string
  /** "8월" 처럼 막대 밑에 적을 짧은 이름 */
  short: string
  actual: number
  isCurrent: boolean
}

/**
 * 상·하반기와 년 탭은 한 칸이 1년입니다. 여섯 칸이면 6년치라 표본이 옛날 얘기가
 * 되므로 네 칸만 봅니다.
 */
export function trendCount(type: PeriodType): number {
  return type === 'week' || type === 'month' || type === 'quarter' ? 6 : 4
}

// 단위를 PERIOD_LABEL 로 조립하면 "최근 6주간", "최근 4상반기" 처럼 말이 안 됩니다.
const TREND_UNIT: Record<PeriodType, string> = {
  week: '주',
  month: '개월',
  quarter: '분기',
  h1: '개 상반기',
  h2: '개 하반기',
  year: '년',
}

/** "최근 6개월" 처럼 막대 위에 적을 문구 */
export function trendCaption(type: PeriodType): string {
  return `최근 ${trendCount(type)}${TREND_UNIT[type]}`
}

/**
 * 막대 밑에 붙는 짧은 이름. 여섯 칸이 한 줄에 서야 해서 전체 이름을 쓸 수 없습니다.
 * 어느 해인지는 캡션과 짚어보기가 말하므로 여기서는 칸을 가르는 데만 씁니다.
 */
function shortLabel(type: PeriodType, fromISO: string): string {
  const [year, month] = fromISO.split('-')
  const m = Number(month)

  switch (type) {
    case 'week':
      return `${m}.${Number(fromISO.slice(8))}`
    case 'month':
      return `${m}월`
    case 'quarter':
      return `${Math.floor((m - 1) / 3) + 1}분기`
    // 상·하반기와 년 탭은 한 칸이 1년이라 연도가 곧 칸 이름입니다.
    default:
      return year
  }
}

/** offset 을 끝으로 count 칸을 과거에서 현재 순서로 돌려줍니다. */
export default function useSalesTrend(
  deals: SalesDeal[],
  type: PeriodType,
  offset: number,
): TrendPoint[] {
  return useMemo(() => {
    const count = trendCount(type)
    const contracts = deals.filter(isContract)

    return Array.from({ length: count }, (_, i) => {
      const at = offset - (count - 1 - i)
      const range = resolveRange(type, at)
      const inRange = contracts.filter((deal) => {
        const date = contractDate(deal)
        return date >= range.fromISO && date <= range.toISO
      })

      return {
        offset: at,
        label: range.label,
        short: shortLabel(type, range.fromISO),
        actual: actualOf(inRange),
        isCurrent: at === offset,
      }
    })
  }, [deals, offset, type])
}
