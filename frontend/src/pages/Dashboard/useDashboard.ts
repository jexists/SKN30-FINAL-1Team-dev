// 대시보드의 조회를 한곳에 둡니다.
//
// 진입할 때는 /api/dashboard 한 번만 부릅니다. 화면에 바로 서는 숫자와 오늘 일정이
// 거기 다 있습니다. 드로어는 눌러야 열리므로 각자 열릴 때 자기 목록을 받아 옵니다.
// 첫 응답에 목록까지 실어 보내면 열지도 않을 드로어의 데이터를 매번 나르게 됩니다.
import { useCallback, useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import { toSalesDeal, type SalesDeal } from '@/pages/Deals/useSalesDeals'
import { toOrder } from '@/pages/Orders/useOrderList'
import { activityToAgenda, seedAgenda } from '@/shared/agenda'
import { useScopeOwnerIds } from '@/shared/scope'
import type {
  ApiPurchaseOrder,
  DashboardResponse,
  NoticeResponse,
  OrderResponse,
  PageResponse,
  SalesDealResponse,
  SupportRequestResponse,
} from '@/types'
import { addDays, iso, parseISO, TODAY } from '@/utils/date'

const PAGE_LIMIT = 30
/** 티커가 한 번에 세 줄씩 넘깁니다. 넉넉히 받아 두면 화살표로 최근 것을 훑을 수 있습니다. */
const NOTICE_LIMIT = 10
/** 화면 문구가 "30일 이내"입니다. 서버는 기준 일수를 스스로 정하지 않습니다. */
export const RENEWAL_WITHIN_DAYS = 30

/** 오늘을 왼쪽에서 셋째 칸에 두어 지난 이틀과 앞으로의 나흘이 함께 보이게 합니다. */
export const weekStart = (offset: number) => addDays(TODAY, -2 + offset * 7)

/** 한 쪽만 받습니다. 더 있으면 next_skip 이 다음 쪽을 가리킵니다. */
function fetchPage<T>(
  path: string,
  signal: AbortSignal,
  skip: number,
  params?: Record<string, unknown>,
): Promise<PageResponse<T>> {
  return client
    .get<PageResponse<T>>(path, {
      params: { skip, limit: PAGE_LIMIT, ...params },
      signal,
    })
    .then(({ data }) => data)
}

/** 다음 쪽의 skip. 더 없으면 null 입니다. 서버가 제자리를 가리키면 무한 반복이라 끊습니다. */
function nextSkipOf<T>(page: PageResponse<T>, skip: number): number | null {
  if (!page.has_more || page.next_skip === null) return null
  if (page.next_skip <= skip) throw new Error('invalid_pagination')
  return page.next_skip
}

export default function useDashboard(weekOffset: number) {
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const ownerIds = useScopeOwnerIds()

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void client
      .get<DashboardResponse>('/dashboard', {
        params: {
          weekly_start_date: iso(weekStart(weekOffset)),
          owner_member_id: ownerIds,
          notice_limit: NOTICE_LIMIT,
          renewal_within_days: RENEWAL_WITHIN_DAYS,
        },
        signal: controller.signal,
      })
      .then(({ data: next }) => {
        if (controller.signal.aborted) return
        setData(next)
        // 하루 목록을 보는 쪽이 같은 날을 다시 받지 않도록 받은 것을 그대로 심습니다.
        seedAgenda(next.date, next.today_activities.map(activityToAgenda))
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setData(null)
          setError(errorMessage(reason, '대시보드를 불러오지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [weekOffset, ownerIds, reloadKey])

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])
  return { data, loading, error, reload }
}

/**
 * 드로어가 열릴 때만 부르는 조회. 둘 다 모양이 같아 한 훅으로 둡니다.
 *
 * `enabled` 가 거짓이면 아무것도 부르지 않습니다. 드로어를 닫아 두는 동안이 그렇습니다.
 */
function useDrawerList<T>(
  enabled: boolean,
  fetch: (signal: AbortSignal, skip: number) => Promise<PageResponse<T>>,
  fallback: string,
) {
  const [items, setItems] = useState<T[]>([])
  const [total, setTotal] = useState(0)
  /** 다음에 이어받을 자리. null 이면 끝까지 받은 것입니다. */
  const [nextSkip, setNextSkip] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  // 열 때는 첫 쪽만 받습니다. 나머지는 사용자가 더 보자고 할 때 이어받습니다.
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void fetch(controller.signal, 0)
      .then((page) => {
        if (controller.signal.aborted) return
        setItems(page.items)
        setTotal(page.total)
        setNextSkip(nextSkipOf(page, 0))
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setItems([])
          setTotal(0)
          setNextSkip(null)
          setError(errorMessage(reason, fallback))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
    // fetch 는 호출부에서 매 렌더 새로 만들어집니다. 여기서 의존하면 계속 다시 받습니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, reloadKey])

  // 버튼 onClick 에만 물리므로 메모하지 않습니다.
  const loadMore = async () => {
    if (nextSkip === null || loadingMore) return
    const skip = nextSkip
    setLoadingMore(true)
    setError(null)
    try {
      const page = await fetch(new AbortController().signal, skip)
      setItems((previous) => [...previous, ...page.items])
      setTotal(page.total)
      setNextSkip(nextSkipOf(page, skip))
    } catch (reason: unknown) {
      setError(errorMessage(reason, fallback))
    } finally {
      setLoadingMore(false)
    }
  }

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])
  return { items, total, loading, loadingMore, error, hasMore: nextSkip !== null, loadMore, reload }
}

export function useSupportList(enabled: boolean) {
  const assigneeIds = useScopeOwnerIds()
  return useDrawerList<SupportRequestResponse>(
    enabled,
    (signal, skip) =>
      fetchPage<SupportRequestResponse>('/support-requests', signal, skip, {
        assignee_member_id: assigneeIds,
      }),
    'C/S 대응요청을 불러오지 못했습니다.',
  )
}

/** 계약갱신 예정. 기준일과 창은 서버가 카드에 쓴 것과 같은 값을 보냅니다. */
export function useRenewalList(enabled: boolean, fromISO: string) {
  const ownerIds = useScopeOwnerIds()
  return useDrawerList<SalesDealResponse>(
    enabled,
    (signal, skip) =>
      fetchPage<SalesDealResponse>('/sales-deals', signal, skip, {
        outcome_code: 'confirmed',
        contract_ends_from: fromISO,
        contract_ends_to: iso(addDays(parseISO(fromISO), RENEWAL_WITHIN_DAYS)),
        owner_member_id: ownerIds,
      }),
    '계약갱신 예정을 불러오지 못했습니다.',
  )
}

/** 공지 한 건의 전문. 티커에는 제목만 있어 본문은 눌렀을 때 받습니다. */
export function useNoticeDetail(noticeId: string | null) {
  const [body, setBody] = useState<NoticeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (noticeId === null) {
      setBody(null)
      setError(null)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void client
      .get<NoticeResponse>(`/notices/${noticeId}`, { signal: controller.signal })
      .then(({ data }) => {
        if (!controller.signal.aborted) setBody(data)
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setBody(null)
          setError(errorMessage(reason, '전문을 불러오지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [noticeId, reloadKey])

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])
  return { body, loading, error, reload }
}

/**
 * 일정 한 건에 딸린 영업과 발주. 일정을 눌러 상세를 열 때만 받아 옵니다.
 *
 * 예전에는 딜과 발주를 전건으로 받아 두고 화면에서 걸러 냈습니다. 열어 보지도 않을
 * 일정 때문에 진입할 때마다 두 목록을 통째로 나르는 셈이었습니다.
 */
export function useRelatedDeal(salesDealId: string | null) {
  const [deal, setDeal] = useState<SalesDeal | null>(null)
  const [orders, setOrders] = useState<ApiPurchaseOrder[]>([])
  // 화면의 "관련 발주 N건" 은 받아 둔 개수가 아니라 서버가 센 전체입니다. 한 쪽만 받아
  // 두고 받은 개수를 세면 더 있는데도 30건이라고 적게 됩니다.
  const [orderTotal, setOrderTotal] = useState(0)
  const [orderNextSkip, setOrderNextSkip] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    if (salesDealId === null) {
      setDeal(null)
      setOrders([])
      setOrderTotal(0)
      setOrderNextSkip(null)
      setError(null)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void Promise.all([
      client.get<SalesDealResponse>(`/sales-deals/${salesDealId}`, { signal: controller.signal }),
      fetchPage<OrderResponse>('/orders', controller.signal, 0, { sales_deal_id: salesDealId }),
    ])
      .then(([dealResponse, orderPage]) => {
        if (controller.signal.aborted) return
        setDeal(toSalesDeal(dealResponse.data))
        setOrders(orderPage.items.map(toOrder))
        setOrderTotal(orderPage.total)
        setOrderNextSkip(nextSkipOf(orderPage, 0))
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setDeal(null)
          setOrders([])
          setOrderTotal(0)
          setOrderNextSkip(null)
          setError(errorMessage(reason, '관련 영업·발주를 불러오지 못했습니다.'))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [salesDealId, reloadKey])

  const loadMoreOrders = async () => {
    if (salesDealId === null || orderNextSkip === null || loadingMore) return
    const skip = orderNextSkip
    setLoadingMore(true)
    setError(null)
    try {
      const page = await fetchPage<OrderResponse>('/orders', new AbortController().signal, skip, {
        sales_deal_id: salesDealId,
      })
      setOrders((previous) => [...previous, ...page.items.map(toOrder)])
      setOrderTotal(page.total)
      setOrderNextSkip(nextSkipOf(page, skip))
    } catch (reason: unknown) {
      setError(errorMessage(reason, '관련 발주를 더 불러오지 못했습니다.'))
    } finally {
      setLoadingMore(false)
    }
  }

  const reload = useCallback(() => setReloadKey((key) => key + 1), [])
  return {
    deal,
    orders,
    orderTotal,
    hasMoreOrders: orderNextSkip !== null,
    loadingMoreOrders: loadingMore,
    loadMoreOrders,
    loading,
    error,
    reload,
  }
}
