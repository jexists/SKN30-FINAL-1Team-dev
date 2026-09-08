// 미팅 맥락과 선택한 딜은 항상 보여 주고, 추가 정보와 선택 목록만 펼칩니다.
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import type { AgendaItem } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'

import DealPicker from '../DealPicker'
import MeetingFacts from '../MeetingFacts'

import styles from './MeetingInfoPanel.module.scss'

interface Props {
  item: AgendaItem
  /** 이 회사에 걸린 영업 현황. 고른 것이 보고서와 AI 작성 근거에 함께 들어갑니다. */
  deals: SalesDeal[]
  dealsLoading: boolean
  dealsError: string | null
  onReloadDeals: () => void
  selectedDealIds: string[]
  fixedDealIds?: string[]
  onToggleDeal: (id: string) => void
  disabled: boolean
}

export default function MeetingInfoPanel({
  item,
  deals,
  dealsLoading,
  dealsError,
  onReloadDeals,
  selectedDealIds,
  fixedDealIds,
  onToggleDeal,
  disabled,
}: Props) {
  const selectedNames = selectedDealIds.map((id) => {
    const deal = deals.find((one) => one.id === id)
    return deal ? deal.title.trim() || deal.product || deal.no : '선택한 딜'
  })

  return (
    <div className={styles.root}>
      <section className={styles.block}>
        <div className={styles.context}>
          <strong>{item.hospital || '회사 미지정'}</strong>
          <span>
            {item.contact || '담당자 미지정'} · 미팅일 {fmtDot(parseISO(item.date))} {item.time}
          </span>
        </div>
        <details className={styles.disclosure}>
          <summary>추가 정보</summary>
          <MeetingFacts dept={item.dept} contact={item.contact} place={item.place} />
          {item.brief && <p className={styles.brief}>{item.brief}</p>}
        </details>
      </section>

      <details className={styles.disclosure}>
        <summary>
          <span className={styles.blockHead}>
            <span>관련 딜 선택</span>
            <span className={styles.count}>
              {selectedDealIds.length}건 선택
              {dealsLoading ? ' · 조회 중' : dealsError ? ' · 조회 오류' : ''}
            </span>
          </span>
          <span className={styles.selectedNames}>{selectedNames.join(' · ') || '딜 미지정'}</span>
        </summary>
        <DealPicker
          deals={deals}
          loading={dealsLoading}
          error={dealsError}
          onRetry={onReloadDeals}
          selected={selectedDealIds}
          fixed={fixedDealIds}
          onToggle={onToggleDeal}
          disabled={disabled}
        />
      </details>
    </div>
  )
}
