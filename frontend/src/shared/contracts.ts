// 시연용 합성 계약 데이터입니다. 매출 분석 화면의 모든 숫자가 여기서 파생됩니다.
//
// 날짜는 다른 시드와 같은 방식으로 오늘 기준 상대 일수(signedOff)를 씁니다. 고정
// 날짜를 박아 두면 시간이 지날수록 "이번 달"이 비어 버립니다. 최근 24개월에 걸쳐
// 흩어 두어 주간·월·분기·반기·년 어느 탭을 열어도 볼 것이 있습니다.
import { addDays, iso, TODAY } from '@/utils/date'

import { contractSeed } from '@/mocks'

import { regionOf } from './regions'
import type { Contract } from '@/types'

export const contracts: Contract[] = contractSeed
  .map((seed) => ({
    ...seed,
    date: iso(addDays(TODAY, seed.signedOff)),
    region: regionOf(seed.org),
  }))
  .sort((a, b) => b.date.localeCompare(a.date))

/** 기간 안에 계약일이 들어오는 계약. 양 끝을 포함합니다. */
export function contractsIn(fromISO: string, toISO: string): Contract[] {
  return contracts.filter((c) => c.date >= fromISO && c.date <= toISO)
}

/** 매출 실적으로 잡는 것은 확정 계약뿐입니다. 진행중·취소는 목록에만 남습니다. */
export function confirmedTotal(list: Contract[]): number {
  return list.reduce((sum, c) => (c.status === '확정' ? sum + c.amount : sum), 0)
}
