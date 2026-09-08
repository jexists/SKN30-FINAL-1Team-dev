// 고객 상세 안에서 그 회사에 걸린 영업 현황을 세로로 늘어놓습니다.
//
// 딜은 회사에 걸리므로 같은 회사의 다른 담당자를 열어도 같은 목록이 나옵니다. 지금 연
// 고객이 그 딜의 대표 담당자인 줄만 '담당' 을 달고 맨 위로 올려, 회사 맥락은 남기되
// 이 사람이 무엇을 들고 있는지가 먼저 보이게 합니다.
//
// 줄을 누르면 영업현황으로 넘어가 그 딜 상세가 열립니다. 여기서 딜을 고치지는 않습니다.
import { Link } from 'react-router'

import Button from '@/components/Button'
import { SkeletonBlocks } from '@/components/Skeleton'
import StageChip from '@/components/StageChip'
import { dealDetailPath } from '@/constants/routes'
import { COMPANY_DEAL_LIMIT } from '@/hooks/useCompanyDeals'
import type { SalesDeal } from '@/pages/Deals/useSalesDeals'
import { fmtDot, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import styles from './CustomerDrawer.module.scss'

interface Props {
  deals: SalesDeal[]
  loading: boolean
  error: string | null
  onRetry: () => void
  /** 지금 연 고객. 이 사람이 대표 담당자인 딜을 표시하고 위로 올리는 기준입니다. */
  contactId: string
}

export default function CustomerDeals({ deals, loading, error, onRetry, contactId }: Props) {
  if (loading) {
    return <SkeletonBlocks label="영업 현황을 불러오는 중입니다." count={2} height={58} />
  }

  if (error) {
    return (
      <div className={styles.dealError} role="alert">
        <p>{error}</p>
        <Button variant="outline" size="sm" type="button" onClick={onRetry}>
          다시 시도
        </Button>
      </div>
    )
  }

  if (deals.length === 0) {
    return <p className={styles.muted}>이 회사에 연결된 영업 현황이 없습니다.</p>
  }

  // 서버가 준 순서를 그대로 두고 담당 건만 앞으로 당깁니다. sort 는 제자리에서 바꾸므로
  // 훅이 들고 있는 배열을 건드리지 않게 복사한 뒤 정렬합니다.
  const mine = (deal: SalesDeal) => deal.contactId === contactId
  const ordered = [...deals].sort((a, b) => Number(mine(b)) - Number(mine(a)))

  return (
    <>
      <div className={styles.stack}>
        {ordered.map((deal) => (
          <Link key={deal.id} className={styles.link} to={dealDetailPath(deal.id)}>
            <span className={styles.dealBody}>
              {/* 제목이 비어 있는 딜이 있습니다. 그때는 제품이 그 자리를 대신합니다. */}
              <strong>{deal.title.trim() || deal.product}</strong>
              <small className="tnum">
                {deal.no} · {wonFull(deal.amount)} · {fmtDot(parseISO(deal.date))}
              </small>
            </span>
            <span className={styles.dealSide}>
              {mine(deal) && <i className={styles.pill}>담당</i>}
              <StageChip tone={deal.stageTone}>{deal.stageName}</StageChip>
            </span>
          </Link>
        ))}
      </div>
      {deals.length === COMPANY_DEAL_LIMIT && (
        <p className={styles.dealMore}>
          최근 {COMPANY_DEAL_LIMIT}건까지 보여줍니다. 나머지는 영업현황에서 확인하세요.
        </p>
      )}
    </>
  )
}
