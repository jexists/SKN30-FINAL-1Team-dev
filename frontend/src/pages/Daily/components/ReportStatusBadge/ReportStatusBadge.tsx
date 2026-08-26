import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import type { ReportStatus } from '@/types'

interface Props {
  /** null 이면 아직 쓰지 않은 날입니다. */
  status: ReportStatus | null
}

const TONE: Record<ReportStatus, StatusTone> = {
  작성중: 'blue',
  '검토 대기': 'orange',
  확정: 'green',
  반려: 'red',
}

export default function ReportStatusBadge({ status }: Props) {
  if (status === null) return <StatusBadge label="미작성" />
  return <StatusBadge label={status} tone={TONE[status]} />
}
