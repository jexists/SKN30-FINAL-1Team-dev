// 왼쪽 첫 번째 탭. 누구와 만난 자리였고 어떤 영업 건에 대한 것인지를 봅니다.
//
// 참고 자료 열이라 카드로도 실선으로도 나누지 않고 제목과 여백으로만 묶습니다.
// 화면에서 떠 있는 면은 오른쪽 보고서 하나뿐이어야 지금 무엇을 고치는 중인지
// 헷갈리지 않습니다.
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
  return (
    <div className={styles.root}>
      <section className={styles.block}>
        <MeetingFacts
          hospital={item.hospital}
          dept={item.dept}
          contact={item.contact}
          place={item.place}
          when={`${fmtDot(parseISO(item.date))} ${item.time}`}
        />

        {item.brief && <p className={styles.brief}>{item.brief}</p>}
      </section>

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h2>영업 현황</h2>
          {selectedDealIds.length > 0 && (
            <span className={styles.count}>{selectedDealIds.length}건 선택</span>
          )}
        </div>

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
      </section>
    </div>
  )
}
