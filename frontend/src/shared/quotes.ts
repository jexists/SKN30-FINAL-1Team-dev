// 시드의 상대 일수를 실제 날짜로 바꿉니다. 발주(shared/orders.ts)와 같은 방식입니다.
import { quoteSeed } from '@/mocks'
import type { Quote } from '@/types'
import { addDays, iso, TODAY, TODAY_ISO } from '@/utils/date'

export const quotes: Quote[] = quoteSeed
  .map((seed) => ({
    ...seed,
    date: iso(addDays(TODAY, seed.issuedOff)),
    validUntil: iso(addDays(TODAY, seed.issuedOff + seed.validDays)),
  }))
  .sort((a, b) => b.date.localeCompare(a.date))

/** 유효기한이 지난 견적. 아직 완료되지 않은 건만 따집니다. */
export const isExpired = (quote: Quote): boolean =>
  quote.stageId !== 'done' && quote.validUntil < TODAY_ISO
