import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { useScopeOwnerIds } from '@/shared/scope'
import type {
  CustomerContactResponse,
  PageResponse,
  SupportRequestCreateRequest,
  SupportRequestResponse,
  SupportResponseResponse,
  SupportStatusCode,
  SupportTransitionRequest,
} from '@/types'

const PAGE_LIMIT = 100

export interface ContactOption {
  id: string
  label: string
}

async function fetchAll<T>(
  path: string,
  signal: AbortSignal,
  extraParams?: Record<string, unknown>,
): Promise<T[]> {
  // ponytail: 탭 건수는 전건 기준입니다. 데이터가 커지면 서버 집계 API로 바꿉니다.
  const items: T[] = []
  let skip = 0

  while (!signal.aborted) {
    const { data } = await client.get<PageResponse<T>>(path, {
      params: { skip, limit: PAGE_LIMIT, ...extraParams },
      signal,
    })
    items.push(...data.items)
    if (!data.has_more || data.next_skip === null) break
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }

  return items
}

function loadErrorMessage(error: unknown, detail = false): string {
  if (!isAxiosError(error)) return `고객불만 ${detail ? '상세를' : '목록을'} 불러오지 못했습니다.`
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return '고객불만을 조회할 권한이 없습니다.'
  if (error.response?.status === 404) return '고객불만을 찾을 수 없습니다.'
  if (error.response?.status === 422) return '조회 조건을 처리하지 못했습니다.'
  return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

export function mutationErrorMessage(error: unknown, action: string): string {
  if (!isAxiosError(error)) return `${action}하지 못했습니다.`
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return `${action}할 권한이 없습니다.`
  if (error.response?.status === 404)
    return '고객불만을 찾을 수 없습니다. 목록을 새로고침해 주세요.'
  if (error.response?.status === 409)
    return '다른 변경이 먼저 반영되었습니다. 새로고침한 뒤 다시 시도해 주세요.'
  if (error.response?.status === 422) return '입력한 내용을 확인해 주세요.'
  return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

export default function useSupportRequests(openId: string | null) {
  const [requests, setRequests] = useState<SupportRequestResponse[]>([])
  const [contacts, setContacts] = useState<ContactOption[]>([])
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

    void Promise.all([
      fetchAll<SupportRequestResponse>('/support-requests', controller.signal, {
        assignee_member_id: assigneeIds,
      }),
      // 고객은 불만을 등록할 때 고르는 목록입니다. 보기 범위로 좁히면 팀원이 맡은
      // 고객의 불만을 접수할 수 없게 됩니다.
      fetchAll<CustomerContactResponse>('/customer-contacts', controller.signal),
    ])
      .then(([requestItems, contactItems]) => {
        if (controller.signal.aborted) return
        setRequests(requestItems)
        setContacts(
          contactItems.map((contact) => ({
            id: contact.id,
            label: `${contact.company_name} · ${contact.name}`,
          })),
        )
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(loadErrorMessage(caught))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [reloadKey, assigneeIds])

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
    setRequests((previous) => [data, ...previous])
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
    contacts,
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
