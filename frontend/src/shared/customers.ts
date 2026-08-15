// 시연용 합성 데이터입니다. 실제 고객·의료 데이터가 아닙니다.
//
// 이메일은 전부 @demo.test, 전화는 02-000-xxxx 로 두어 실재하는 연락처가
// 섞이지 않게 합니다. 날짜는 오늘 기준 offset(일) 이라 시연이 낡지 않습니다.

import { customerSeed } from '@/mocks'
import type { Customer, CustomerSeed, CustomerSource, CustomerStatus } from '@/types'

import { addDays, iso, parseISO, TODAY, TODAY_ISO } from '@/utils/date'

/** 필터 선택지. 데이터에서 뽑지 않고 여기 두는 값이라 순서가 항상 단계 순입니다. */
export const CUSTOMER_STATUSES: CustomerStatus[] = ['신규', '제안', '협의', '계약', '보류']

export const CUSTOMER_SOURCES: CustomerSource[] = [
  '소개',
  '박람회',
  '홈페이지',
  '콜드콜',
  '기존 거래',
]

export const CUSTOMER_OWNERS: string[] = [...new Set(customerSeed.map((c) => c.owner))].sort()

export function toCustomer(seed: CustomerSeed): Customer {
  const next = seed.nextOff === null ? null : iso(addDays(TODAY, seed.nextOff))
  return {
    ...seed,
    last: iso(addDays(TODAY, seed.lastOff)),
    next,
    created: iso(addDays(TODAY, seed.createdOff)),
    overdue: next === null || next < TODAY_ISO,
  }
}

export const customers: Customer[] = customerSeed.map(toCustomer)

/** "3일 전" / "오늘" / "2일 뒤" — 목록에서 날짜 옆에 붙는 보조 라벨입니다. */
export function relativeDayLabel(isoDate: string): string {
  const days = Math.round((parseISO(isoDate).getTime() - TODAY.getTime()) / 86_400_000)
  if (days === 0) return '오늘'
  if (days < 0) return `${-days}일 전`
  return `${days}일 뒤`
}
