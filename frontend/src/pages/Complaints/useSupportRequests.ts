import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { transportMessage } from '@/api/errorMessage'
import { useScopeOwnerIds } from '@/shared/scope'
import type {
  TabbedPageResponse,
  SupportRequestCreateRequest,
  SupportRequestResponse,
  SupportResponseResponse,
  SupportStatusCode,
  SupportTransitionRequest,
} from '@/types'

function loadErrorMessage(error: unknown, detail = false): string {
  const fallback = `고객불만 ${detail ? '상세를' : '목록을'} 불러오지 못했습니다.`
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return '고객불만을 조회할 권한이 없습니다.'
  if (error.response?.status === 404) return '고객불만을 찾을 수 없습니다.'
  if (error.response?.status === 422) return '조회 조건을 처리하지 못했습니다.'
  return transportMessage(error) ?? fallback
}

export function mutationErrorMessage(error: unknown, action: string): string {
  const fallback = `${action}하지 못했습니다.`
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return `${action}할 권한이 없습니다.`
  if (error.response?.status === 404)
    return '고객불만을 찾을 수 없습니다. 목록을 새로고침해 주세요.'
  if (error.response?.status === 409)
    return '다른 변경이 먼저 반영되었습니다. 새로고침한 뒤 다시 시도해 주세요.'
  if (error.response?.status === 422) return '입력한 내용을 확인해 주세요.'
  return transportMessage(error) ?? fallback
}

export interface SupportQuery {
  q: string
  /** 고른 탭. 빈 문자열이면 전체입니다. */
  status: SupportStatusCode | ''
  skip: number
  limit: number
}

export default function useSupportRequests(openId: string | null, query: SupportQuery) {
  const [requests, setRequests] = useState<SupportRequestResponse[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [detail, setDetail] = useState<SupportRequestResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailReloadKey, setDetailReloadKey] = useState(0)

  const [pendingKey, setPendingKey] = useState<string | null>(null)
  const pendingRef = useRef(false)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const assigneeIds = useScopeOwnerIds()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    const needle = query.q.trim()
    void client
      .get<TabbedPageResponse<SupportRequestResponse>>('/support-requests', {
        params: {
          q: needle === '' ? undefined : needle.slice(0, 100),
          status_code: query.status === '' ? undefined : query.status,
          assignee_member_id: assigneeIds,
          skip: query.skip,
          limit: query.limit,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setRequests(data.items)
        setTotal(data.total)
        setCounts(data.counts)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(loadErrorMessage(caught))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [reloadKey, assigneeIds, query.q, query.status, query.skip, query.limit])

  useEffect(() => {
    setDetail(null)
    setDetailError(null)
    if (openId === null) {
      setDetailLoading(false)
      return
    }

    const controller = new AbortController()
    setDetailLoading(true)
    void client
      .get<SupportRequestResponse>(`/support-requests/${openId}`, { signal: controller.signal })
      .then(({ data }) => {
        if (!controller.signal.aborted) setDetail(data)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setDetailError(loadErrorMessage(caught, true))
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false)
      })

    return () => controller.abort()
  }, [openId, detailReloadKey])

  const createRequest = useCallback(async (payload: SupportRequestCreateRequest) => {
    const { data } = await client.post<SupportRequestResponse>('/support-requests', payload)
    // 새 불만이 이 쪽 첫 줄에 오는지는 발생 시각 순서가 정합니다. 목록에 끼워 넣지 않고
    // 다시 받아 서버가 놓는 자리를 따릅니다.
    setReloadKey((value) => value + 1)
    return data
  }, [])

  const transition = useCallback(
    async (request: SupportRequestResponse, statusCode: SupportStatusCode) => {
      if (pendingRef.current) return false
      pendingRef.current = true
      setPendingKey(`transition:${request.id}`)
      setMutationError(null)

      try {
        const payload: SupportTransitionRequest = {
          expected_status_code: request.status_code,
          status_code: statusCode,
        }
        const { data } = await client.post<SupportRequestResponse>(
          `/support-requests/${request.id}/transition`,
          payload,
        )
        setRequests((previous) => previous.map((item) => (item.id === data.id ? data : item)))
        setDetail(data)
        return true
      } catch (caught: unknown) {
        setMutationError(mutationErrorMessage(caught, '상태를 변경'))
        return false
      } finally {
        pendingRef.current = false
        setPendingKey(null)
      }
    },
    [],
  )

  const addResponse = useCallback(async (requestId: string, body: string) => {
    if (pendingRef.current) return false
    pendingRef.current = true
    setPendingKey(`response:${requestId}`)
    setMutationError(null)

    try {
      const { data } = await client.post<SupportResponseResponse>(
        `/support-requests/${requestId}/responses`,
        { body },
      )
      setDetail((previous) =>
        previous?.id === requestId
          ? { ...previous, responses: [...previous.responses, data] }
          : previous,
      )
      return true
    } catch (caught: unknown) {
      setMutationError(mutationErrorMessage(caught, '답변을 등록'))
      return false
    } finally {
      pendingRef.current = false
      setPendingKey(null)
    }
  }, [])

  return {
    requests,
    total,
    counts,
    loading,
    error,
    reload: () => setReloadKey((value) => value + 1),
    detail,
    detailLoading,
    detailError,
    reloadDetail: () => setDetailReloadKey((value) => value + 1),
    pendingKey,
    mutationError,
    clearMutationError: () => setMutationError(null),
    createRequest,
    transition,
    addResponse,
  }
}
