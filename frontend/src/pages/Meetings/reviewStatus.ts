// 업무보고서를 팀장이 어디까지 봤는지. 화면에 배지로 나오고 수정 잠금도 이걸로 가릅니다.
//
// 서버 status_code(draft/submitted/approved/rejected)에 content.on_hold 를 더해 다섯 단계로
// 폅니다. MeetingReport.status(ReportStatus)는 일일보고 집계가 '확정' 여부로 읽으므로
// 그대로 두고, 표시·잠금은 이 값만 씁니다.
import type { StatusTone } from '@/components/StatusBadge'
import type { ApiReportStatus, MeetingReview } from '@/types'

export const REVIEW_LABEL: Record<MeetingReview, string> = {
  writing: '작성중',
  submitted: '작성완료',
  approved: '확인완료',
  needsMore: '보충 필요',
  hold: '보류',
}

export const REVIEW_TONE: Record<MeetingReview, StatusTone> = {
  writing: 'blue',
  submitted: 'orange',
  approved: 'green',
  needsMore: 'red',
  hold: 'neutral',
}

export function reviewOf(code: ApiReportStatus, onHold: boolean): MeetingReview {
  // 확인이 끝난 보고서는 보류가 아닙니다. 보류 표시보다 확인완료가 앞섭니다.
  if (code === 'approved') return 'approved'
  if (onHold) return 'hold'
  if (code === 'draft') return 'writing'
  if (code === 'rejected') return 'needsMore'
  return 'submitted'
}
