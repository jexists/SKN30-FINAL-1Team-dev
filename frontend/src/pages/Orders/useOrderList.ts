import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { transportMessage } from '@/api/errorMessage'
import { useScopeOwnerIds } from '@/shared/scope'
import type {
  ApiPurchaseOrder,
  OrderCreateRequest,
  OrderMoveRequest,
  OrderPatchRequest,
  OrderResponse,
  PageResponse,
  ProductResponse,
  PurchaseOrderStatusResponse,
  SalesDealResponse,
} from '@/types'
import { parseISO, TODAY } from '@/utils/date'

const PAGE_LIMIT = 100

export interface OrderOption {
  id: string
  name: string
}

export interface OrderSalesDealOption {
  id: string
  no: string
  customerCompanyName: string
}

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
    orderedOff: offsetOf(order.ordered_on),
    dueOff: offsetOf(order.due_on),
    expectOff: offsetOf(order.expected_receipt_on),
    createdAt: order.created_at,
    updatedAt: order.updated_at,
  }
}

async function fetchAllPage<T>(
  path: string,
  signal?: AbortSignal,
  extraParams?: Record<string, unknown>,
): Promise<T[]> {
  // ponytail: 현재 화면의 필터·탭 건수는 전건 기준입니다. 데이터가 커지면 서버 집계로 바꿉니다.
  const items: T[] = []
  let skip = 0

  while (!signal?.aborted) {
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

async function fetchAllOrders(
  signal?: AbortSignal,
  ownerIds?: readonly string[],
): Promise<ApiPurchaseOrder[]> {
  // 발주에는 담당자 칸이 따로 없어 서버가 딜의 담당자로 거릅니다.
  return (await fetchAllPage<OrderResponse>('/orders', signal, { owner_member_id: ownerIds })).map(
    toOrder,
  )
}

function toWriteRequest(draft: OrderDraft): OrderPatchRequest {
  return {
    sales_deal_id: draft.salesDealId,
    supplier_name: draft.supplier,
    ordered_on: draft.ordered,
    due_on: draft.due,
    expected_receipt_on: draft.expect,
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

export default function useOrderList(detailNo?: string) {
  const [orders, setOrders] = useState<ApiPurchaseOrder[]>([])
  const [products, setProducts] = useState<OrderOption[]>([])
  const [salesDeals, setSalesDeals] = useState<OrderSalesDealOption[]>([])
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

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void Promise.all([
      fetchAllOrders(controller.signal, ownerIds),
      // 제품과 딜은 발주를 등록할 때 고르는 목록입니다. 보기 범위로 좁히면 팀원이 맡은
      // 딜의 발주를 넣을 수 없게 됩니다.
      fetchAllPage<ProductResponse>('/products', controller.signal),
      fetchAllPage<SalesDealResponse>('/sales-deals', controller.signal),
      client
        .get<PurchaseOrderStatusResponse[]>('/purchase-order-statuses', {
          signal: controller.signal,
        })
        .then((response) => response.data),
    ])
      .then(([orderItems, productItems, dealItems, statusItems]) => {
        if (controller.signal.aborted) return
        setOrders(orderItems)
        setProducts(productItems.map(({ id, name }) => ({ id, name })))
        setSalesDeals(
          dealItems
            .filter((salesDeal) => salesDeal.sales_pipeline_status_code === 'published')
            .map((salesDeal) => ({
              id: salesDeal.id,
              no: salesDeal.deal_no,
              customerCompanyName: salesDeal.customer_company_name,
            })),
        )
        setStatuses(statusItems)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(requestErrorMessage(caught, '목록'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [reloadKey, ownerIds])

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

  const suppliers = useMemo(
    () => [...new Set(orders.map((order) => order.supplier))].sort(),
    [orders],
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
    products,
    salesDeals,
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
