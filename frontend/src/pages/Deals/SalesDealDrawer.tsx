import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import StageChip from '@/components/StageChip'
import type { ColumnTone } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import type { SalesDeal } from './useSalesDeals'

import styles from './SalesDealForm.module.scss'

interface Props {
  deal: SalesDeal | null
  stage?: { name: string; tone: ColumnTone }
  loading: boolean
  error: string | null
  onRetry: () => void
  onEdit?: () => void
  onDelete?: () => void
  onClose: () => void
}

export default function SalesDealDrawer({
  deal,
  stage,
  loading,
  error,
  onRetry,
  onEdit,
  onDelete,
  onClose,
}: Props) {
  const readOnly = deal?.pipelineStatus === 'archived'
  const facts = deal
    ? [
        ['파이프라인', deal.pipelineName],
        ['제품', deal.product],
        ['금액', wonFull(deal.amount)],
        ['담당 영업', deal.owner],
        ['고객 담당자', deal.contactName ?? '미지정'],
        ['지역', deal.region],
        ['영업 시작일', fmtDot(parseISO(deal.date))],
      ]
    : []

  return (
    <Drawer
      title={deal?.org ?? '영업 딜 상세'}
      sub={deal ? `${deal.no} · ${deal.title}` : undefined}
      meta={
        deal && (
          <>
            {stage && <StageChip tone={stage.tone}>{stage.name}</StageChip>}
            <span>{deal.kind}</span>
          </>
        )
      }
      footer={
        deal && !loading && !error && !readOnly && onEdit && onDelete ? (
          <>
            <Button variant="outline" onClick={onEdit}>
              수정
            </Button>
            <Button variant="outline" onClick={onDelete}>
              삭제
            </Button>
          </>
        ) : undefined
      }
      onClose={onClose}
    >
      {error ? (
        <div className={styles.drawerState} role="alert">
          <p>{error}</p>
          <Button variant="outline" onClick={onRetry}>
            다시 시도
          </Button>
        </div>
      ) : loading ? (
        <p className={styles.drawerState} role="status">
          영업 딜 상세를 불러오는 중입니다.
        </p>
      ) : deal ? (
        <>
          {readOnly && <p className={styles.memoEmpty}>보관된 파이프라인 · 읽기 전용</p>}
          <dl className={styles.drawerFacts}>
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className={label === '금액' || label === '영업 시작일' ? 'tnum' : undefined}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {deal.memo ? (
            <p className={styles.memo}>{deal.memo}</p>
          ) : (
            <p className={styles.memoEmpty}>메모가 없습니다.</p>
          )}
        </>
      ) : (
        <p className={styles.drawerState}>영업 딜 상세 정보가 없습니다.</p>
      )}
    </Drawer>
  )
}
