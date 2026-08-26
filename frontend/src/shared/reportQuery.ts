// 자리를 정해 놓고 묻는 보고서 조회입니다.
//
// 예전에는 보고서를 통째로 받아 두고 화면마다 그 배열을 뒤졌습니다. 목록이 한 쪽만
// 오는 지금 그 방식은 페이지 밖의 보고서를 못 찾고, 못 찾으면 같은 기간·같은 일정에
// 보고서를 하나 더 만들게 합니다. 그래서 찾을 것이 정해진 곳(그 날, 그 기간, 그 일정)은
// 조건을 그대로 서버에 넘기고 한 쪽만 받습니다.
import { isAxiosError } from 'axios'
import { useEffect, useRef, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { PAGE_SIZE } from '@/constants/pagination'
import type { PageResponse, ReportResponse } from '@/types'

export type ReportQuery = Record<string, unknown>

/** 없는 번호. 화면이 "찾을 수 없습니다" 로 받아야 하므로 에러와 갈라 둡니다. */
const isNotFound = (reason: unknown) => isAxiosError(reason) && reason.response?.status === 404

/**
 * 한 쪽만 받습니다. 자리가 정해진 조회라 한 쪽을 넘을 일이 없습니다.
 *
 * ponytail: 한 주의 일일보고서나 한 달의 주간보고서처럼 자리 수가 정해진 조회만
 * 씁니다. 자리가 30 을 넘길 수 있는 조회는 useSearchPaging 으로 더보기를 붙이세요.
 */
export async function fetchReportPage(
  params: ReportQuery,
  signal?: AbortSignal,
): Promise<ReportResponse[]> {
  const { data } = await client.get<PageResponse<ReportResponse>>('/reports', {
    params: { limit: PAGE_SIZE, ...params },
    signal,
  })
  return data.items
}

/** 한 건만 봅니다. 목록 밖의 보고서도 열려야 하므로 주소의 번호로 직접 묻습니다. */
export async function fetchReport(id: string, signal?: AbortSignal): Promise<ReportResponse> {
  const { data } = await client.get<ReportResponse>(`/reports/${id}`, { signal })
  return data
}

/** `params` 가 null 이면 부르지 않습니다. 아직 물을 것이 정해지지 않은 동안입니다. */
export function useReportQuery(params: ReportQuery | null, fallback: string) {
  const [items, setItems] = useState<ReportResponse[]>([])
  const [loading, setLoading] = useState(params !== null)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  // 객체는 렌더마다 새로 만들어집니다. 값이 같으면 다시 받지 않도록 문자열로 견줍니다.
  const key = JSON.stringify(params)
  const latest = useRef(params)
  latest.current = params

  useEffect(() => {
    const asked = latest.current
    if (asked === null) {
      setItems([])
      setLoading(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void fetchReportPage(asked, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) setItems(rows)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setItems([])
        setError(errorMessage(reason, fallback))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
    // fallback 은 호출부의 상수 문자열이라 의존할 필요가 없습니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, reloadKey])

  return { items, loading, error, reload: () => setReloadKey((value) => value + 1) }
}

/**
 * 주소가 가리키는 보고서 한 건.
 *
 * 목록에서 찾으면 그 보고서가 첫 쪽 밖일 때 "찾을 수 없습니다" 가 뜹니다. 링크를
 * 받아 바로 들어오는 길이라 목록을 거치지 않고 번호로 묻습니다.
 */
export function useReportDetail(id: string | undefined, fallback: string) {
  const [item, setItem] = useState<ReportResponse | null>(null)
  const [loading, setLoading] = useState(id !== undefined)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (id === undefined) {
      setItem(null)
      setLoading(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void fetchReport(id, controller.signal)
      .then((row) => {
        if (!controller.signal.aborted) setItem(row)
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return
        setItem(null)
        // 없는 번호는 화면이 "찾을 수 없습니다" 로 받습니다. 에러로 덮지 않습니다.
        if (isNotFound(reason)) return
        setError(errorMessage(reason, fallback))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
    // fallback 은 호출부의 상수 문자열이라 의존할 필요가 없습니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, reloadKey])

  return { item, loading, error, reload: () => setReloadKey((value) => value + 1) }
}
