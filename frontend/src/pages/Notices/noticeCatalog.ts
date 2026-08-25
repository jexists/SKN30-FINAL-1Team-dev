// 공지관리 화면이 쓰는 어휘와 표 정의. 화면 이름과 판정 규칙을 한곳에 둡니다.
import type { StatusTone } from '@/components/StatusBadge'
import type { NoticeManageListResponse, NoticeType } from '@/types'
import { iso, TODAY } from '@/utils/date'

export const TYPE_TABS: { value: NoticeType; label: string }[] = [
  { value: 'NOTICE', label: '공지사항' },
  { value: 'DIRECTIVE', label: '팀장 지시사항' },
]

export function typeLabel(type: NoticeType): string {
  return type === 'DIRECTIVE' ? '팀장 지시사항' : '공지사항'
}

export const COLUMNS = [
  { id: 'sortOrder', header: '순서', width: 64 },
  { id: 'title', header: '제목', width: 300 },
  { id: 'tag', header: '태그', width: 96 },
  { id: 'targets', header: '수신자', width: 180 },
  { id: 'period', header: '게시기간', width: 200 },
  { id: 'state', header: '상태', width: 88 },
  { id: 'author', header: '작성자', width: 110 },
  { id: 'actions', header: '관리', width: 150 },
]

export const TABLE_WIDTH = COLUMNS.reduce((sum, column) => sum + column.width, 0)

export interface NoticeState {
  label: string
  tone: StatusTone
}

/**
 * 표에 세우는 상태. 서버가 대시보드에 내보내는 조건과 같은 순서로 봅니다.
 * 숨김이 가장 세고, 그다음이 아직 시작하지 않은 것, 끝난 것입니다.
 */
export function stateOf(row: NoticeManageListResponse, today: string = iso(TODAY)): NoticeState {
  if (row.is_hidden) return { label: '숨김', tone: 'neutral' }
  if (row.display_start_date > today) return { label: '예정', tone: 'blue' }
  if (row.display_end_date !== null && row.display_end_date < today) {
    return { label: '종료', tone: 'neutral' }
  }
  return { label: '게시중', tone: 'green' }
}

/** 게시기간 한 줄. 종료일이 없으면 무기한입니다. */
export function periodLabel(row: NoticeManageListResponse): string {
  return `${row.display_start_date} ~ ${row.display_end_date ?? '무기한'}`
}

/** 수신자 한 줄. 공지는 팀 전체가 봅니다. */
export function targetsLabel(row: NoticeManageListResponse): string {
  if (row.type === 'NOTICE') return '팀 전체'
  if (row.targets.length === 0) return '-'
  return row.targets.map((target) => target.display_name).join(', ')
}
