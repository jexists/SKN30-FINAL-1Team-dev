// 미팅 보고서가 어디까지 왔는지. 화면에 배지로 나오고 수정 잠금도 이걸로 가릅니다.
//
// 미팅 보고서는 팀장이 확정·반려하는 결재 문서가 아니라 일일보고서를 만들기 위한
// 기록입니다. 그래서 화면은 '작성중 / 작성완료' 둘(쓴 것이 없으면 '미작성')만 말합니다.
// 서버의 status_code(draft/submitted/approved/rejected)와 POST /reports/{id}/review 는
// 그대로 두고 여기서 읽는 말만 좁혔습니다.
//
// MeetingReport.status는 일일보고 집계가 '확정' 여부로 읽으므로 그대로 두고,
// 표시·잠금은 이 값만 씁니다.
import type { StatusTone } from '@/components/StatusBadge'
import type { ApiReportStatus, MeetingReview } from '@/types'

/** 미팅 보고서 화면 어휘. 검토 단계가 없으므로 쓰는 중과 다 쓴 것 둘뿐입니다. */
export type MeetingStatusLabel = '작성중' | '작성완료'

export const MEETING_STATUS_TONE: Record<MeetingStatusLabel, StatusTone> = {
  작성중: 'blue',
  작성완료: 'green',
}

/**
 * status_code 를 화면 말로. draft 만 '작성중'이고 나머지는 모두 '작성완료'입니다.
 * rejected·changes_requested 는 검토를 걷어내기 전 자료에만 남아 있어 함께 흡수합니다.
 */
export function meetingStatusLabel(code: ApiReportStatus): MeetingStatusLabel {
  return code === 'draft' ? '작성중' : '작성완료'
}

/**
 * 서버 값을 그대로 편 다섯 단계. 이제 화면 배지는 위 meetingStatusLabel 이 그리고,
 * 이 값은 수정 잠금 판정(approved)에만 남았습니다.
 */
export function reviewOf(code: ApiReportStatus, onHold: boolean): MeetingReview {
  // 확인이 끝난 보고서는 보류가 아닙니다. 보류 표시보다 확인완료가 앞섭니다.
  if (code === 'approved') return 'approved'
  if (onHold) return 'hold'
  if (code === 'draft') return 'writing'
  if (code === 'rejected' || code === 'changes_requested') return 'needsMore'
  return 'submitted'
}
