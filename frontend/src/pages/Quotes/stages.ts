// 견적 화면의 어휘입니다. 견적서 한 장이 작성에서 완료까지 지나는 다섯 단계를 둡니다.
// 계약의 stages.ts 와 같은 모양이고, 단계 이름만 다릅니다.
import type { QuoteStageId, Stage } from '@/types'

export interface QuoteStage extends Stage {
  id: QuoteStageId
}

export const QUOTE_STAGES: QuoteStage[] = [
  { id: 'draft', name: '견적작성', tone: 'gray' },
  { id: 'review', name: '견적검토', tone: 'blue' },
  { id: 'sent', name: '고객발송', tone: 'purple' },
  { id: 'negotiate', name: '조건협의', tone: 'orange' },
  { id: 'done', name: '견적완료', tone: 'green' },
]

export const stageById = (id: string): QuoteStage | undefined =>
  QUOTE_STAGES.find((stage) => stage.id === id)

/** 다음 견적번호. 올해 번호 중 가장 큰 것에 1 을 더합니다. */
export function nextQuoteNo(list: { no: string }[]): string {
  const year = new Date().getFullYear()
  const prefix = `FM-QT-${year}-`
  const last = list.reduce((max, q) => {
    if (!q.no.startsWith(prefix)) return max
    const n = Number(q.no.slice(prefix.length))
    return Number.isNaN(n) ? max : Math.max(max, n)
  }, 0)
  return `${prefix}${String(last + 1).padStart(4, '0')}`
}
