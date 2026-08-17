import Button from '@/components/Button'
import Drawer from '@/components/Drawer'
import StageChip from '@/components/StageChip'
import type { ColumnTone } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import type { PipelineContract } from './usePipelineContracts'

import styles from './PipelineContractForm.module.scss'

interface Props {
  contract: PipelineContract | null
  stage?: { name: string; tone: ColumnTone }
  loading: boolean
  error: string | null
  onRetry: () => void
  onEdit: () => void
  onDelete: () => void
  onClose: () => void
}

export default function PipelineContractDrawer({
  contract,
  stage,
  loading,
  error,
  onRetry,
  onEdit,
  onDelete,
  onClose,
}: Props) {
  const facts = contract
    ? [
        ['제품', contract.product],
        ['금액', wonFull(contract.amount)],
        ['담당 영업', contract.owner],
        ['고객 담당자', contract.contactName ?? '미지정'],
        ['지역', contract.region],
        ['계약일', fmtDot(parseISO(contract.date))],
      ]
    : []

  return (
    <Drawer
      title={contract?.org ?? '영업 건 상세'}
      sub={contract ? `${contract.no} · ${contract.title}` : undefined}
      meta={
        contract && (
          <>
            {stage && <StageChip tone={stage.tone}>{stage.name}</StageChip>}
            <span>{contract.kind}</span>
          </>
        )
      }
      footer={
        contract && !loading && !error ? (
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
          계약 상세를 불러오는 중입니다.
        </p>
      ) : contract ? (
        <>
          <dl className={styles.drawerFacts}>
            {facts.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className={label === '금액' || label === '계약일' ? 'tnum' : undefined}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {contract.memo ? (
            <p className={styles.memo}>{contract.memo}</p>
          ) : (
            <p className={styles.memoEmpty}>메모가 없습니다.</p>
          )}
        </>
      ) : (
        <p className={styles.drawerState}>계약 상세 정보가 없습니다.</p>
      )}
    </Drawer>
  )
}
