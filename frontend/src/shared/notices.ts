// 공지 도메인. 시드는 mocks/ 에서 받습니다.
import { addDays, fmtDay, TODAY } from '@/utils/date'

import { directives, notices } from '@/mocks'
import type { Notice } from '@/types'

/**
 * 목록 오른쪽에 찍는 작성 시점. 오늘 올린 글만 시각까지 보여 줍니다.
 * 어제 이전은 시각을 알아도 할 일이 달라지지 않아 며칠 전인지만 남깁니다.
 */
export function postedLabel(n: Notice): string {
  if (n.postedOff === 0) return n.postedAt
  if (n.postedOff === -1) return '어제'
  return `${-n.postedOff}일 전`
}

/** 드로어 머리말에 쓰는 정확한 작성 일시 */
export function postedFull(n: Notice): string {
  return `${fmtDay(addDays(TODAY, n.postedOff))} ${n.postedAt}`
}

// 두 목록 모두 최근에 올린 것이 위로 옵니다.

export { directives, notices }
