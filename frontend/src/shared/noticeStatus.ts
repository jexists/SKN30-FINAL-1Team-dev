// 팀장 지시사항의 이행 여부.
//
// 팀원은 대시보드에서 자기 몫을 처리하고, 팀장은 공지관리 화면에서 누가 어떻게 했는지
// 봅니다. 두 화면이 같은 말을 써야 하므로 라벨과 호출을 여기에 모읍니다.
import { client } from '@/api/client'
import type { StatusTone } from '@/components/StatusBadge'
import type {
  NoticeResponse,
  NoticeStatusRequest,
  NoticeTargetResponse,
  NoticeTargetStatus,
} from '@/types'

export interface StatusLabel {
  label: string
  tone: StatusTone
}

const STATUS: Record<NoticeTargetStatus, StatusLabel> = {
  pending: { label: '대기', tone: 'neutral' },
  done: { label: '이행', tone: 'green' },
  not_done: { label: '미이행', tone: 'red' },
}

export function statusLabel(status: NoticeTargetStatus): StatusLabel {
  return STATUS[status]
}

/** 수신자 명단의 이행 진행도 한 줄. 예: '이행 2/3' */
export function progressLabel(targets: NoticeTargetResponse[]): string {
  const done = targets.filter((target) => target.status_code === 'done').length
  return `이행 ${done}/${targets.length}`
}

/**
 * 명단 전체를 한 배지로 줄인 상태.
 *
 * 미이행이 하나라도 있으면 그것부터 보여 줍니다. 팀장이 먼저 알아야 하는 것은 몇 명이
 * 했는지가 아니라 못 한 사람이 있는지입니다.
 */
export function rollupLabel(targets: NoticeTargetResponse[]): StatusLabel {
  if (targets.length === 0) return { label: '수신자 없음', tone: 'neutral' }
  if (targets.some((target) => target.status_code === 'not_done')) {
    return { label: '미이행', tone: 'red' }
  }
  if (targets.every((target) => target.status_code === 'done')) {
    return { label: '완료', tone: 'green' }
  }
  return { label: '진행중', tone: 'orange' }
}

/** 담당자가 자기 몫의 이행 여부를 남깁니다. 미이행이면 사유가 필요합니다. */
export async function setNoticeStatus(
  noticeId: string,
  statusCode: NoticeStatusRequest['status_code'],
  reason: string | null,
): Promise<NoticeResponse> {
  const payload: NoticeStatusRequest = { status_code: statusCode, reason }
  const { data } = await client.post<NoticeResponse>(`/notices/${noticeId}/status`, payload)
  return data
}
