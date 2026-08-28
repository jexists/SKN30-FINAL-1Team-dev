import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { transportMessage } from '@/api/errorMessage'
import { useScopeOwnerIds } from '@/shared/scope'
import type {
  ApiPurchaseOrder,
  OrderCreateRequest,
  OrderMoveRequest,
  OrderPatchRequest,
  OrderPageResponse,
  OrderResponse,
  PageResponse,
  PurchaseOrderStatusResponse,
} from '@/types'
import { parseISO, TODAY } from '@/utils/date'

export interface OrderDraftItem {
  productId: string
  qty: number
  price: number
}

export interface OrderDraft {
  salesDealId: string
  supplier: string
  stageCode: string
  ordered: string
  due: string
  expect: string
  requestDepartment: string
  cooperationDepartment: string
  /** 납품예상 거래처. 딜의 고객사와 다를 수 있어 따로 받습니다. */
  expectedCustomerCompanyId: string
  memo: string | null
  items: OrderDraftItem[]
}

const offsetOf = (dateISO: string) =>
  Math.round((parseISO(dateISO).getTime() - TODAY.getTime()) / 86_400_000)

export function toOrder(order: OrderResponse): ApiPurchaseOrder {
  return {
    id: order.id,
    no: order.order_no,
    salesDealId: order.sales_deal_id,
    salesDeal: order.deal_no,
    // 공용 발주 표시 로직이 contract 필드 이름을 사용합니다.
    contract: order.deal_no,
    customerCompanyId: order.customer_company_id,
    hospital: order.customer_company_name,
    ownerMemberId: order.owner_member_id,
    owner: order.owner_display_name,
    supplier: order.supplier_name,
    status: order.stage_name,
    stageCode: order.stage_code,
    stageTone: order.stage_tone,
    stageOutcomeCode: order.stage_outcome_code,
    stagePosition: order.stage_position,
    memo: order.memo ?? '',
    items: [...order.items]
      .sort((a, b) => a.position - b.position)
      .map((item) => ({
        id: item.id,
        productId: item.product_id,
        product: item.product_name,
        qty: item.quantity,
        price: item.unit_price,
        position: item.position,
      })),
    ordered: order.ordered_on,
    due: order.due_on,
    expect: order.expected_receipt_on,
    requestDepartment: order.request_department,
    cooperationDepartment: order.cooperation_department,
    createdByMemberId: order.created_by_member_id,
    createdBy: order.created_by_display_name,
    expectedCustomerCompanyId: order.expected_customer_company_id,
    expectedCustomerCompany: order.expected_customer_company_name,
    orderedOff: offsetOf(order.ordered_on),
    dueOff: offsetOf(order.due_on),
    expectOff: offsetOf(order.expected_receipt_on),
    createdAt: order.created_at,
    updatedAt: order.updated_at,
  }
}

function toWriteRequest(draft: OrderDraft): OrderPatchRequest {
  return {
    sales_deal_id: draft.salesDealId,
    supplier_name: draft.supplier,
    ordered_on: draft.ordered,
    due_on: draft.due,
    expected_receipt_on: draft.expect,
    request_department: draft.requestDepartment,
    cooperation_department: draft.cooperationDepartment,
    expected_customer_company_id: draft.expectedCustomerCompanyId,
    memo: draft.memo,
    items: draft.items.map((item) => ({
      product_id: item.productId,
      quantity: item.qty,
      unit_price: item.price,
    })),
  }
}

function requestErrorMessage(error: unknown, target: '목록' | '상세'): string {
  const fallback = `발주 ${target}을 불러오지 못했습니다.`
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return `발주 ${target}을 조회할 권한이 없습니다.`
  if (error.response?.status === 404) return '발주를 찾을 수 없습니다.'
  if (error.response?.status === 422) return `발주 ${target} 조회 조건을 처리하지 못했습니다.`
  return transportMessage(error) ?? fallback
}

function mutationErrorMessage(error: unknown, action: string): string {
  const fallback = `${action}하지 못했습니다.`
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return `${action}할 권한이 없습니다.`
  if (error.response?.status === 404) return '발주를 찾을 수 없습니다. 목록을 새로고침해 주세요.'
  if (error.response?.status === 409)
    return '다른 변경이 먼저 반영되었습니다. 목록을 새로고침한 뒤 다시 시도해 주세요.'
  if (error.response?.status === 422) return '입력한 값과 발주 상태를 확인해 주세요.'
  return transportMessage(error) ?? fallback
}

export interface OrderQuery {
  q: string
  /** 고른 공급처. 빈 문자열이면 전체입니다. */
  supplier: string
  /** 발주일 하한. null 이면 제한 없음입니다. */
  fromISO: string | null
  /** 고른 상태 탭. 빈 문자열이면 전체입니다. */
  status: string
  skip: number
  limit: number
}

export default function useOrderList(detailNo?: string, query?: OrderQuery) {
  const [orders, setOrders] = useState<ApiPurchaseOrder[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [suppliers, setSuppliers] = useState<string[]>([])
  const [statuses, setStatuses] = useState<PurchaseOrderStatusResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [detail, setDetail] = useState<ApiPurchaseOrder | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailReloadKey, setDetailReloadKey] = useState(0)

  const pendingRef = useRef(new Set<string>())
  const [pendingKeys, setPendingKeys] = useState<ReadonlySet<string>>(() => new Set())
  const [mutationError, setMutationError] = useState<string | null>(null)
  const ownerIds = useScopeOwnerIds()

  // 조회 조건을 낱개로 펼쳐 둡니다. 아래 목록 효과가 객체가 아니라 값 하나하나를 보게
  // 해야, 화면이 조건 객체를 새로 만들 때마다 다시 받지 않습니다.
  const listing = query !== undefined
  const {
    q: queryText = '',
    supplier: querySupplier = '',
    status: queryStatus = '',
    fromISO: queryFrom = null,
    skip: querySkip = 0,
    limit: queryLimit = 30,
  } = query ?? {}

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void client
      .get<PurchaseOrderStatusResponse[]>('/purchase-order-statuses', {
        signal: controller.signal,
      })
      .then(({ data: statusItems }) => {
        if (controller.signal.aborted) return
        setStatuses(statusItems)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(requestErrorMessage(caught, '목록'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [reloadKey])

  // 목록은 조건이 바뀔 때마다 한 쪽씩 받습니다. 위의 선택지 목록과 나눠 두어야 검색어를
  // 한 글자 칠 때마다 제품·딜을 다시 받지 않습니다.
  useEffect(() => {
    if (!listing) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    const needle = queryText.trim()
    void client
      .get<OrderPageResponse>('/orders', {
        params: {
          q: needle === '' ? undefined : needle.slice(0, 100),
          supplier_name: querySupplier === '' ? undefined : querySupplier,
          stage_code: queryStatus === '' ? undefined : queryStatus,
          start_date: queryFrom ?? undefined,
          // 발주에는 담당자 칸이 따로 없어 서버가 딜의 담당자로 거릅니다.
          owner_member_id: ownerIds,
          skip: querySkip,
          limit: queryLimit,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setOrders(data.items.map(toOrder))
        setTotal(data.total)
        setCounts(data.counts)
        setSuppliers(data.suppliers)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(requestErrorMessage(caught, '목록'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [
    reloadKey,
    ownerIds,
    listing,
    queryText,
    querySupplier,
    queryStatus,
    queryFrom,
    querySkip,
    queryLimit,
  ])

  // 번호로 서버에 직접 묻습니다. 목록에서 찾으면 그 발주가 현재 페이지 밖일 때 상세가
  // 열리지 않습니다. 목록과 상세가 같은 모델이라 이 한 번으로 상세까지 받습니다.
  useEffect(() => {
    setDetail(null)
    setDetailError(null)
    if (detailNo === undefined) {
      setDetailLoading(false)
      return
    }

    const controller = new AbortController()
    setDetailLoading(true)
    void client
      .get<PageResponse<OrderResponse>>('/orders', {
        params: { order_no: detailNo, limit: 1 },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (!controller.signal.aborted) setDetail(data.items[0] ? toOrder(data.items[0]) : null)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setDetailError(requestErrorMessage(caught, '상세'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false)
      })

    return () => controller.abort()
  }, [detailNo, detailReloadKey])

  const reload = useCallback(() => setReloadKey((value) => value + 1), [])
  const reloadDetail = useCallback(() => setDetailReloadKey((value) => value + 1), [])
  const clearMutationError = useCallback(() => setMutationError(null), [])

  const runMutation = useCallback(
    async <T>(key: string, action: string, request: () => Promise<T>): Promise<T> => {
      if (pendingRef.current.has(key)) throw new Error('이미 요청을 처리하고 있습니다.')
      pendingRef.current.add(key)
      setPendingKeys(new Set(pendingRef.current))
      setMutationError(null)
      try {
        return await request()
      } catch (caught: unknown) {
        const message = mutationErrorMessage(caught, action)
        setMutationError(message)
        throw new Error(message)
      } finally {
        pendingRef.current.delete(key)
        setPendingKeys(new Set(pendingRef.current))
      }
    },
    [],
  )

  const addOrder = useCallback(
    (draft: OrderDraft) =>
      runMutation('create', '발주를 등록', async () => {
        const request: OrderCreateRequest = {
          ...toWriteRequest(draft),
          stage_code: draft.stageCode,
        }
        const { data } = await client.post<OrderResponse>('/orders', request)
        const created = toOrder(data)
        setOrders((previous) => [created, ...previous])
        return created
      }),
    [runMutation],
  )

  const updateOrder = useCallback(
    (id: string, draft: OrderDraft) =>
      runMutation(id, '발주를 수정', async () => {
        const { data } = await client.patch<OrderResponse>(`/orders/${id}`, toWriteRequest(draft))
        const updated = toOrder(data)
        setOrders((previous) => previous.map((order) => (order.id === id ? updated : order)))
        setDetail((previous) => (previous?.id === id ? updated : previous))
        return updated
      }),
    [runMutation],
  )

  const setStatus = useCallback(
    (id: string, expectedStageCode: string, stageCode: string) =>
      runMutation(id, '발주 상태를 변경', async () => {
        const request: OrderMoveRequest = {
          expected_stage_code: expectedStageCode,
          stage_code: stageCode,
        }
        const { data } = await client.post<OrderResponse>(`/orders/${id}/move`, request)
        const updated = toOrder(data)
        setOrders((previous) => previous.map((order) => (order.id === id ? updated : order)))
        setDetail((previous) => (previous?.id === id ? updated : previous))
        return updated
      }),
    [runMutation],
  )

  const removeOrder = useCallback(
    (id: string) =>
      runMutation(id, '발주를 삭제', async () => {
        await client.delete(`/orders/${id}`)
        setOrders((previous) => previous.filter((order) => order.id !== id))
        setDetail((previous) => (previous?.id === id ? null : previous))
      }),
    [runMutation],
  )

  const findOrderById = useCallback(
    (id: string) => orders.find((order) => order.id === id),
    [orders],
  )
  const findOrderByNo = useCallback(
    (no: string) => orders.find((order) => order.no === no),
    [orders],
  )
  const isPending = useCallback((id: string) => pendingKeys.has(id), [pendingKeys])

  return {
    orders,
    total,
    counts,
    statuses,
    suppliers,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
    mutationError,
    clearMutationError,
    isCreating: pendingKeys.has('create'),
    isPending,
    findOrderById,
    findOrderByNo,
    addOrder,
    updateOrder,
    setStatus,
    removeOrder,
  }
}
