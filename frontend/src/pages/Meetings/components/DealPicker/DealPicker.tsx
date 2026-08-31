// 이 미팅이 어느 영업 현황에 대한 것인지 고릅니다.
//
// 한 자리에서 여러 딜을 이야기하는 일이 흔해 체크박스로 둡니다. 고른 딜은 보고서에
// 저장되고, 그대로 AI 가 읽는 작성 근거가 됩니다.
import { useId } from 'react'

import Button from '@/components/Button'
import { SkeletonBlocks } from '@/components/Skeleton'
import StageChip from '@/components/StageChip'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { won } from '@/utils/format'

import styles from './DealPicker.module.scss'

interface Props {
  deals: SalesDeal[]
  loading: boolean
  error: string | null
  onRetry: () => void
  /** 고른 딜의 id */
  selected: string[]
  /** 보고서 행이 이미 생긴 딜은 연결을 바꿀 수 없어 선택을 풀 수 없습니다. */
  fixed?: string[]
  onToggle: (id: string) => void
  disabled: boolean
}

export default function DealPicker({
  deals,
  loading,
  error,
  onRetry,
  selected,
  fixed = [],
  onToggle,
  disabled,
}: Props) {
  const fixedHintId = useId()

  if (loading) {
    return <SkeletonBlocks label="영업 현황을 불러오는 중입니다." count={3} height={52} />
  }

  if (error) {
    return (
      <div className={styles.error} role="alert">
        <p>{error}</p>
        <Button variant="outline" size="sm" type="button" onClick={onRetry}>
          다시 시도
        </Button>
      </div>
    )
  }

  if (deals.length === 0) {
    return <p className={styles.empty}>이 회사에 연결된 영업 현황이 없습니다.</p>
  }

  return (
    <ul className={styles.list}>
      {deals.map((deal) => (
        <li key={deal.id}>
          <label className={styles.row}>
            <input
              type="checkbox"
              className={styles.check}
              checked={selected.includes(deal.id)}
              disabled={disabled || fixed.includes(deal.id)}
              aria-describedby={fixed.includes(deal.id) ? `${fixedHintId}-${deal.id}` : undefined}
              onChange={() => onToggle(deal.id)}
            />

            <span className={styles.body}>
              <span className={styles.head}>
                <span className={styles.no}>{deal.no}</span>
                <StageChip tone={deal.stageTone}>{deal.stageName}</StageChip>
              </span>
              {/* 제목이 비어 있는 딜이 있습니다. 그때는 제품이 그 자리를 대신합니다. */}
              <span className={styles.title}>{deal.title.trim() || deal.product}</span>
              <span className={['tnum', styles.amount].join(' ')}>{won(deal.amount)}</span>
            </span>
          </label>
          {fixed.includes(deal.id) && (
            <p id={`${fixedHintId}-${deal.id}`} className={styles.empty}>
              저장된 보고서가 있어 선택을 해제할 수 없습니다.
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}
