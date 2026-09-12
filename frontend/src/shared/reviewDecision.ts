// 팀장 검토 화면이 쓰는 보고서 상태 어휘.
//
// 서버의 status_code 는 그대로 두고 라벨만 세 가지로 좁혀 읽습니다. 팀장이 하는 일은
// "제출된 것을 확정하거나 반려한다" 뿐이라 검토대기·확정·반려 말고는 고를 것이 없습니다.
//
// 지금 이 어휘를 부르는 화면은 없습니다. 미팅 보고서는 팀장이 확정·반려하는 문서가
// 아니라 일일보고서를 만들기 위한 기록이어서 대시보드의 검토 드로어 연결을 끊었고,
// 그 드로어가 이 파일의 유일한 사용처였습니다. 일일·주간·월간 보고서의 검토 흐름에
// 그대로 쓸 수 있어 서버의 POST /reports/{id}/review 와 함께 남겨 둡니다.
//
// pages/Meetings/reviewStatus.ts 는 작성자가 자기 미팅 보고서를 볼 때 쓰는 어휘
// (작성중·작성완료)라 따로 둡니다. 같은 status_code 를 보는 사람이 다릅니다.
import type { StatusTone } from '@/components/StatusBadge'
import { client } from '@/api/client'
import type { ApiReportStatus, ReportResponse, ReportReviewRequest } from '@/types'

export interface ReviewLabel {
  label: string
  tone: StatusTone
}

const REVIEW: Record<ApiReportStatus, ReviewLabel> = {
  draft: { label: '작성중', tone: 'blue' },
  submitted: { label: '검토대기', tone: 'orange' },
  approved: { label: '확정', tone: 'green' },
  // 반려는 changes_requested 로 들어옵니다. rejected 는 지금 쓰지 않지만, 예전에 만든
  // 보고서가 그 값을 들고 있을 수 있어 같은 말로 읽습니다.
  changes_requested: { label: '반려', tone: 'red' },
  rejected: { label: '반려', tone: 'red' },
}

export function reviewLabel(status: ApiReportStatus): ReviewLabel {
  return REVIEW[status]
}

/** 팀장이 지금 확정·반려할 수 있는 보고서인지. 제출된 것만 검토합니다. */
export function isReviewable(status: ApiReportStatus): boolean {
  return status === 'submitted'
}

/**
 * 보고서를 확정하거나 반려합니다.
 *
 * 반려에는 사유가 필요합니다. 무엇을 고쳐야 하는지 없이 돌려보내면 팀원이 같은 것을
 * 그대로 다시 냅니다. 서버도 같은 조건으로 거절합니다.
 */
export async function reviewReport(
  reportId: string,
  submissionId: string | null,
  decision: ReportReviewRequest['decision'],
  reason: string | null,
): Promise<ReportResponse> {
  const payload: ReportReviewRequest = {
    decision,
    reason,
    expected_status_code: 'submitted',
    expected_submission_id: submissionId,
  }
  const { data } = await client.post<ReportResponse>(`/reports/${reportId}/review`, payload)
  return data
}
