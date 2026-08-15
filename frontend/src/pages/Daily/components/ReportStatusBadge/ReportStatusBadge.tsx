import type { ReportStatus } from '@/types'

import styles from './ReportStatusBadge.module.scss'

interface Props {
  /** null 이면 아직 쓰지 않은 날입니다. */
  status: ReportStatus | null
}

const TONE: Record<ReportStatus, string> = {
  작성중: 'isDraft',
  '검토 대기': 'isPending',
  확정: 'isDone',
  반려: 'isRejected',
}

export default function ReportStatusBadge({ status }: Props) {
  if (status === null) return <span className={styles.badge}>미작성</span>
  return <span className={`${styles.badge} ${styles[TONE[status]]}`}>{status}</span>
}
