import type { Notice, NoticeBrief, NoticeResponse } from '@/types'
import { addDays, fmtDay, parseISO, TODAY } from '@/utils/date'

const DAY = 86_400_000

/**
 * 목록에 걸리는 한 줄과 눌러서 받는 전문이 같은 함수를 씁니다. 전문에만 있는 본문·이미지는
 * 비워 두고, 드로어가 받아 온 뒤 채웁니다.
 */
type NoticeLike = NoticeBrief & Partial<Pick<NoticeResponse, 'scope' | 'body' | 'image_alt'>>

export function toNotice(item: NoticeLike, scope?: NoticeResponse['scope']): Notice {
  const published = new Date(item.published_at)
  const localDate = new Date(published.getTime() + 9 * 60 * 60_000).toISOString()
  const date = localDate.slice(0, 10)
  return {
    id: item.id,
    tag: item.tag ?? ((item.scope ?? scope) === 'personal' ? '지시' : '공지'),
    author: item.author_display_name,
    postedOff: Math.round((parseISO(date).getTime() - TODAY.getTime()) / DAY),
    postedAt: localDate.slice(11, 16),
    text: item.title,
    detail: item.body ?? '',
    imageAlt: item.image_alt ?? undefined,
    due: item.due_text ?? item.due_at?.slice(0, 10),
  }
}

export function postedLabel(notice: Pick<Notice, 'postedOff' | 'postedAt'>): string {
  if (notice.postedOff === 0) return notice.postedAt
  if (notice.postedOff === -1) return '어제'
  return `${-notice.postedOff}일 전`
}

export function postedFull(notice: Notice): string {
  return `${fmtDay(addDays(TODAY, notice.postedOff))} ${notice.postedAt}`
}
