import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type {
  NoticeCreateRequest,
  NoticeManageListResponse,
  NoticeManageResponse,
  NoticePatchRequest,
  NoticeType,
  PageResponse,
} from '@/types'

export interface NoticeQuery {
  type: NoticeType
  q: string
  skip: number
  limit: number
}

export default function useNotices({ type, q, skip, limit }: NoticeQuery) {
  const [notices, setNotices] = useState<NoticeManageListResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const needle = q.trim()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void client
      .get<PageResponse<NoticeManageListResponse>>('/notices/manage', {
        params: {
          type,
          q: needle === '' ? undefined : needle.slice(0, 100),
          skip,
          limit,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setNotices(data.items)
        setTotal(data.total)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(errorMessage(caught, '공지 목록을 불러오지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [type, needle, skip, limit, reloadKey])

  const reload = useCallback(() => setReloadKey((previous) => previous + 1), [])

  /** 수정 폼을 열 때 본문을 받아 옵니다. 목록에는 본문이 없습니다. */
  const loadNotice = useCallback(async (id: string) => {
    const { data } = await client.get<NoticeManageResponse>(`/notices/manage/${id}`)
    return data
  }, [])

  const addNotice = useCallback(
    async (payload: NoticeCreateRequest) => {
      const { data } = await client.post<NoticeManageResponse>('/notices', payload)
      // 새 글이 이 쪽에 속하는지는 노출 순서가 정합니다. 목록에 끼워 넣지 않고 다시 받아
      // 서버가 정한 자리에 놓습니다.
      reload()
      return data
    },
    [reload],
  )

  const editNotice = useCallback(
    async (id: string, patch: NoticePatchRequest) => {
      const { data } = await client.patch<NoticeManageResponse>(`/notices/${id}`, patch)
      reload()
      return data
    },
    [reload],
  )

  const removeNotice = useCallback(
    async (id: string) => {
      await client.delete(`/notices/${id}`)
      reload()
    },
    [reload],
  )

  const toggleHidden = useCallback(
    (row: NoticeManageListResponse) => editNotice(row.id, { is_hidden: !row.is_hidden }),
    [editNotice],
  )

  return {
    notices,
    total,
    loading,
    error,
    reload,
    loadNotice,
    addNotice,
    editNotice,
    removeNotice,
    toggleHidden,
  }
}
