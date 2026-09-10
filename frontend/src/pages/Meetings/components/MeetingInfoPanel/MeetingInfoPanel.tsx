// 미팅 맥락과 연결할 딜을 나란한 두 판으로 펼쳐 둡니다. 판마다 제 머리와 제 조작을 답니다.
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import type { AgendaItem } from '@/types'
import Button from '@/components/Button'
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
  onCreateDeal?: () => void
  onOpenDetail: () => void
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
  onCreateDeal,
  onOpenDetail,
  disabled,
}: Props) {
  return (
    <div className={styles.root}>
      <div className={styles.cols}>
        <section className={styles.block}>
          <div className={styles.head}>
            <h2>미팅 정보</h2>
            {item.stage && <span className={styles.pill}>{item.stage}</span>}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={styles.headAction}
              onClick={onOpenDetail}
            >
              자세히 보기
            </Button>
          </div>
          <div className={styles.context}>
            <strong>{item.hospital || '회사 미지정'}</strong>
            <span>
              {item.contact || '담당자 미지정'} · 미팅일 {fmtDot(parseISO(item.date))} {item.time}
            </span>
          </div>
          <MeetingFacts dept={item.dept} contact={item.contact} place={item.place} />
          {item.brief && <p className={styles.brief}>{item.brief}</p>}
        </section>

        <section className={styles.block}>
          <div className={styles.head}>
            <h2>관련 딜</h2>
            <span className={styles.count}>
              {selectedDealIds.length}건 선택
              {dealsLoading ? ' · 조회 중' : dealsError ? ' · 조회 오류' : ''}
            </span>
            {onCreateDeal && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={styles.headAction}
                disabled={disabled || dealsLoading || !item.customerCompanyId}
                onClick={onCreateDeal}
              >
                새 딜 생성
              </Button>
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
    </div>
  )
}
