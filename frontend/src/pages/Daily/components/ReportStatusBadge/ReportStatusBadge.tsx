import StatusBadge, { type StatusTone } from '@/components/StatusBadge'
import type { MeetingStatusLabel } from '@/pages/Meetings/reviewStatus'
import type { ReportStatus } from '@/types'

interface Props {
  /** null 이면 아직 쓰지 않은 날입니다. 미팅 줄은 '작성중'·'작성완료' 둘뿐입니다. */
  status: ReportStatus | MeetingStatusLabel | '수정중' | null
}

const TONE: Record<ReportStatus | MeetingStatusLabel | '수정중', StatusTone> = {
  작성중: 'blue',
  수정중: 'blue',
  // 미팅 기록은 팀장 검토를 안 거칩니다. 승인까지 끝난 '확정'과 같은 초록이면
  // 목록에서 둘이 구분되지 않고, 회색은 '미작성' 자리라 보라로 갈라 둡니다.
  작성완료: 'purple',
  '검토 대기': 'orange',
  확정: 'green',
  반려: 'red',
}

export default function ReportStatusBadge({ status }: Props) {
  if (status === null) return <StatusBadge label="미작성" />
  return <StatusBadge label={status} tone={TONE[status]} />
}
