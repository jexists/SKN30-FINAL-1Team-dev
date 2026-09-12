// 딜 보고서 카드의 머리. 작성 화면과 완료 화면이 같은 것을 씁니다.
//
// 딜 번호는 아래 본문 제목과 같은 세로축에서 시작하고, 판정 배지는 줄 끝에 섭니다.
import { Link } from 'react-router'

import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import { dealDetailPath } from '@/constants/routes'

import styles from './DealCardHeader.module.scss'

export interface DealBadge {
  label: string
  tone: StatusTone
  title?: string
}

interface Props {
  dealId: string
  /** 딜 번호. SL-V2-020-03 처럼 사람이 부르는 이름입니다. */
  label: string
  note?: string
  badge: DealBadge
  /** 작성 중에는 쓰던 것을 잃지 않게 새 탭으로 엽니다. */
  newTab?: boolean
}

export default function DealCardHeader({ dealId, label, note, badge, newTab = false }: Props) {
  return (
    <header className={styles.header}>
      <Link
        className={styles.identity}
        to={dealDetailPath(dealId)}
        target={newTab ? '_blank' : undefined}
        rel={newTab ? 'noreferrer' : undefined}
        aria-label={`${label} 딜 상세${newTab ? ' 새 탭에서' : ''} 열기`}
      >
        <span className={styles.dealText}>
          <strong className={styles.dealLine}>{label}</strong>
          {note && <span className={styles.dealTitle}>{note}</span>}
        </span>
      </Link>

      <span className={styles.result} title={badge.title}>
        <StatusBadge label={badge.label} tone={badge.tone} />
      </span>
    </header>
  )
}
