// 검색해서 고르는 입력들이 함께 쓰는 조회입니다.
//
// 열 때 한 쪽만 받고, 목록 끝까지 스크롤하면 다음 쪽을 이어 붙입니다. 검색어를 고치면
// 처음부터 다시 받습니다. 전건을 미리 받아 두지 않으므로 후보가 수천이어도 같은 값입니다.
import { useCallback, useEffect, useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { PAGE_SIZE } from '@/constants/pagination'
import useDebouncedValue from '@/hooks/useDebouncedValue'
import type { PageResponse } from '@/types'

interface Options {
  /** 목록이 닫혀 있으면 부르지 않습니다. */
  open: boolean
  /** 조회에 늘 붙는 조건. 값이 바뀌면 처음부터 다시 받습니다. */
  params?: Record<string, unknown>
  /** 거짓이면 조건이 아직 갖춰지지 않은 것이라 부르지 않습니다. */
  enabled?: boolean
  fallback: string
}

export default function useSearchPaging<T>(
  path: string,
  query: string,
  { open, params, enabled = true, fallback }: Options,
) {
  const [matches, setMatches] = useState<T[]>([])
  /** 조건에 맞는 전체 건수. 받아 온 건수가 아니라 서버가 센 값입니다. */
  const [total, setTotal] = useState(0)
  /** 다음에 이어받을 자리. null 이면 끝까지 받은 것입니다. */
  const [nextSkip, setNextSkip] = useState<number | null>(null)
  // 첫 렌더부터 참이어야 화면이 '없습니다' 를 잠깐 비추지 않습니다.
  const [loading, setLoading] = useState(open && enabled)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const settledQuery = useDebouncedValue(query.trim())
  // 객체는 렌더마다 새로 만들어집니다. 값이 같으면 다시 받지 않도록 문자열로 견줍니다.
  const paramsKey = JSON.stringify(params ?? {})
  // 이어받기가 최신 조건을 보게 합니다. 의존성에 넣으면 스크롤마다 첫 쪽을 다시 받습니다.
  const latest = useRef({ params, settledQuery })
  latest.current = { params, settledQuery }

  const fetchPage = useCallback(
    (skip: number, signal?: AbortSignal) => {
      const { params: current, settledQuery: needle } = latest.current
      return client
        .get<PageResponse<T>>(path, {
          params: {
            ...current,
            q: needle === '' ? undefined : needle.slice(0, 100),
            skip,
            limit: PAGE_SIZE,
          },
          signal,
        })
        .then(({ data }) => data)
    },
    [path],
  )

  useEffect(() => {
    if (!open || !enabled) return

    const controller = new AbortController()
    setLoading(true)
    setLoadError(null)

    void fetchPage(0, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        setMatches(page.items)
        setTotal(page.total)
        setNextSkip(page.has_more ? page.next_skip : null)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setMatches([])
        setTotal(0)
        setNextSkip(null)
        setLoadError(errorMessage(reason, fallback))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
    // fallback 은 호출부의 상수 문자열이라 의존할 필요가 없습니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPage, settledQuery, paramsKey, open, enabled, reloadKey])

  /** 목록 끝이 보일 때마다 불립니다. 이미 받는 중이면 아무 일도 하지 않습니다. */
  const loadMore = useCallback(() => {
    if (nextSkip === null || loadingMore || loading) return
    const skip = nextSkip
    setLoadingMore(true)

    void fetchPage(skip)
      .then((page) => {
        setMatches((previous) => [...previous, ...page.items])
        // 서버가 제자리를 가리키면 같은 쪽을 끝없이 다시 받습니다. 거기서 끊습니다.
        setNextSkip(
          page.has_more && page.next_skip !== null && page.next_skip > skip ? page.next_skip : null,
        )
      })
      .catch((reason: unknown) => {
        setNextSkip(null)
        setLoadError(errorMessage(reason, fallback))
      })
      .finally(() => setLoadingMore(false))
  }, [fetchPage, nextSkip, loadingMore, loading, fallback])

  return {
    matches,
    total,
    loading,
    loadingMore,
    loadError,
    hasMore: nextSkip !== null,
    loadMore,
    reload: () => setReloadKey((value) => value + 1),
  }
}
