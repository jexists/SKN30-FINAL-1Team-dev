import type { Notice, NoticeBrief, NoticeResponse } from '@/types'
import { addDays, fmtDay, parseISO, TODAY } from '@/utils/date'

const DAY = 86_400_000

/**
 * 목록에 걸리는 한 줄과 눌러서 받는 전문이 같은 함수를 씁니다. 전문에만 있는 본문·이미지는
 * 비워 두고, 드로어가 받아 온 뒤 채웁니다.
 */
type NoticeLike = NoticeBrief & Partial<Pick<NoticeResponse, 'scope' | 'body' | 'image_alt'>>

/** 종류는 서버가 준 type 이 먼저입니다. scope 는 type 이 없던 시절의 폴백입니다. */
function isDirective(item: NoticeLike): boolean {
  if (item.type !== undefined) return item.type === 'DIRECTIVE'
  return item.scope === 'personal'
}

export function toNotice(item: NoticeLike): Notice {
  const published = new Date(item.published_at)
  const localDate = new Date(published.getTime() + 9 * 60 * 60_000).toISOString()
  const date = localDate.slice(0, 10)
  return {
    id: item.id,
    tag: item.tag ?? (isDirective(item) ? '지시' : '공지'),
    author: item.author_display_name,
    postedOff: Math.round((parseISO(date).getTime() - TODAY.getTime()) / DAY),
    postedAt: localDate.slice(11, 16),
    text: item.title,
    detail: item.body ?? '',
    imageAlt: item.image_alt ?? undefined,
    due: item.due_text ?? item.due_at?.slice(0, 10),
    // 공지는 수신자가 없어 빈 목록입니다. 없는 것과 같게 두어 화면이 자리를 잡지 않게 합니다.
    recipients: item.targets.length === 0 ? undefined : item.targets.map((t) => t.display_name),
    // 내가 받은 지시일 때만 옵니다. 공지이거나 남에게 간 지시면 서버가 null 을 줍니다.
    myStatus: item.my_status ?? undefined,
  }
}

/**
 * 수신자를 한 줄에 담습니다. 티커는 한 줄짜리라 이름을 다 늘어놓으면 제목이 밀립니다.
 * 전부 필요한 자리(드로어)는 recipients 를 직접 씁니다.
 */
export function recipientLabel(recipients: string[]): string {
  const [first, ...rest] = recipients
  return rest.length === 0 ? first : `${first} 외 ${rest.length}명`
}

export function postedLabel(notice: Pick<Notice, 'postedOff' | 'postedAt'>): string {
  if (notice.postedOff === 0) return notice.postedAt
  if (notice.postedOff === -1) return '어제'
  return `${-notice.postedOff}일 전`
}

export function postedFull(notice: Notice): string {
  return `${fmtDay(addDays(TODAY, notice.postedOff))} ${notice.postedAt}`
}
