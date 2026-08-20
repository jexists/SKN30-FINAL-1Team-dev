import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { Notice, NoticeResponse, PageResponse } from '@/types'
import { addDays, fmtDay, parseISO, TODAY } from '@/utils/date'

const PAGE_LIMIT = 100
const DAY = 86_400_000

function toNotice(item: NoticeResponse): Notice {
  const published = new Date(item.published_at)
  const localDate = new Date(published.getTime() + 9 * 60 * 60_000).toISOString()
  const date = localDate.slice(0, 10)
  return {
    id: item.id,
    tag: item.tag ?? (item.scope === 'personal' ? '지시' : '공지'),
    author: item.author_display_name,
    postedOff: Math.round((parseISO(date).getTime() - TODAY.getTime()) / DAY),
    postedAt: localDate.slice(11, 16),
    text: item.title,
    detail: item.body,
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

export function useNotices() {
  const [items, setItems] = useState<NoticeResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    void (async () => {
      try {
        const result: NoticeResponse[] = []
        let skip = 0
        while (!controller.signal.aborted) {
          const { data } = await client.get<PageResponse<NoticeResponse>>('/notices', {
            params: { skip, limit: PAGE_LIMIT },
            signal: controller.signal,
          })
          result.push(...data.items)
          if (!data.has_more || data.next_skip === null) break
          if (data.next_skip <= skip) throw new Error('invalid_pagination')
          skip = data.next_skip
        }
        if (!controller.signal.aborted) setItems(result)
      } catch (reason: unknown) {
        if (!controller.signal.aborted) {
          setItems([])
          setError(errorMessage(reason, '공지와 지시사항을 불러오지 못했습니다.'))
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    })()
    return () => controller.abort()
  }, [reloadKey])

  const mapped = items.map(toNotice)
  return {
    notices: mapped.filter((_, index) => items[index].scope === 'team'),
    directives: mapped.filter((_, index) => items[index].scope === 'personal'),
    loading,
    error,
    reload: useCallback(() => setReloadKey((value) => value + 1), []),
  }
}
