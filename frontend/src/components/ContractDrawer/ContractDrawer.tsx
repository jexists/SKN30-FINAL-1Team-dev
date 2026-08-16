// 카드를 눌렀을 때 오른쪽에서 들어오는 요약 패널입니다.
// 관련 발주나 같은 고객사의 다른 계약까지는 여기 넣지 않습니다.
// 하단 "전체 보기" 로 /contracts/:no 로 넘깁니다.
import { useEffect, useId, useRef } from 'react'
import { Link } from 'react-router'

import { ChevronRightIcon, CloseIcon, TrashIcon } from '@/components/icons'
import StageChip from '@/components/StageChip'
import { contractPath } from '@/constants/routes'
import type { Contract, Stage } from '@/types'
import { fmtDot, parseISO } from '@/utils/date'
import { wonFull } from '@/utils/format'

import styles from './ContractDrawer.module.scss'

interface Props {
  contract: Contract
  /** 지금 이 계약이 놓인 단계 */
  stage: Stage | undefined
  onClose: () => void
  onEdit: () => void
  onDelete: () => void
}

export default function ContractDrawer({ contract, stage, onClose, onEdit, onDelete }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  // Modal 과 같은 처리입니다. Escape 로 닫고 배경은 스크롤을 멈추며,
  // 닫으면 눌렀던 카드로 포커스가 돌아갑니다.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    const previousOverflow = document.body.style.overflow
    const previouslyFocused = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus()
    }
  }, [onClose])

  useEffect(() => {
    bodyRef.current
      ?.querySelector<HTMLElement>('a, button, [tabindex]:not([tabindex="-1"])')
      ?.focus()
  }, [])

  return (
    <div className={styles.scrim} onPointerDown={onClose}>
      <aside
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <header className={styles.head}>
          <div>
            <p className={`${styles.no} tnum`}>{contract.no}</p>
            <h2 id={titleId}>{contract.org}</h2>
          </div>
          <button type="button" className={styles.close} onClick={onClose} aria-label="닫기">
            <CloseIcon />
          </button>
        </header>

        <div className={styles.body} ref={bodyRef}>
          <div className={styles.tags}>
            {stage && <StageChip tone={stage.tone}>{stage.name}</StageChip>}
            <span className={styles.kind}>{contract.kind}</span>
          </div>

          <p className={`${styles.amount} tnum`}>{wonFull(contract.amount)}</p>

          <dl className={styles.facts}>
            <div>
              <dt>제품</dt>
              <dd>{contract.product}</dd>
            </div>
            <div>
              <dt>지역</dt>
              <dd>{contract.region}</dd>
            </div>
            <div>
              <dt>담당 영업</dt>
              <dd>{contract.owner}</dd>
            </div>
            <div>
              <dt>계약일</dt>
              <dd className="tnum">{fmtDot(parseISO(contract.date))}</dd>
            </div>
          </dl>

          {contract.memo ? (
            <p className={styles.memo}>{contract.memo}</p>
          ) : (
            <p className={styles.memoEmpty}>메모가 없습니다.</p>
          )}

          <div className={styles.actions}>
            <button type="button" className={styles.action} onClick={onEdit}>
              수정
            </button>
            <button
              type="button"
              className={`${styles.action} ${styles.danger}`}
              onClick={onDelete}
            >
              <TrashIcon width={14} height={14} />
              삭제
            </button>
          </div>

          <Link className={styles.cta} to={contractPath(contract.no)}>
            전체 보기
            <ChevronRightIcon />
          </Link>
        </div>
      </aside>
    </div>
  )
}
