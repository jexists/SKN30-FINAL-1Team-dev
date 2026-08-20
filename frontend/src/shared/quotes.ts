import type { Quote } from '@/types'
import { TODAY_ISO } from '@/utils/date'

export const quotes: Quote[] = []
export const isExpired = (quote: Quote): boolean =>
  quote.stageId !== 'done' && quote.validUntil < TODAY_ISO
