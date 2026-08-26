import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { transportMessage } from '@/api/errorMessage'
import { useScopeOwnerIds } from '@/shared/scope'
import type {
  PageResponse,
  SalesDealCreateRequest,
  SalesDealMoveRequest,
  SalesDealPatchRequest,
  SalesDealResponse,
  TabbedPageResponse,
  SalesDealStatus,
  SalesDealTypeResponse,
  SalesPipelineOutcomeCode,
  SalesPipelinePhaseCode,
  SalesPipelineResponse,
  SalesPipelineStageResponse,
} from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import type { BoardColumn, BoardDeal } from './board'

const PAGE_LIMIT = 30

const STATUS_BY_OUTCOME: Record<SalesPipelineOutcomeCode, SalesDealStatus> = {
  in_progress: '진행중',
  confirmed: '확정',
  cancelled: '취소',
}

const REGION_LABEL: Record<string, string> = {
  seoul: '서울',
  gyeonggi: '경기',
  incheon: '인천',
  chungnam: '충남',
}

export interface SalesDealSaveInput {
  customerCompanyId: string
  productId: string
  amount: number
  dealTypeCode: string
  date: string
  memo: string | null
}

export interface SalesDealColumn extends BoardColumn {
  phase: SalesPipelinePhaseCode
}

export interface SalesDeal extends BoardDeal {
  id: string
  pipelineId: string
  pipelineName: string
  pipelineStatus: SalesPipelineResponse['status_code']
  stageCode: string
  stageName: string
  stageTone: SalesPipelineStageResponse['tone']
  stagePhase: SalesPipelinePhaseCode
  stageOrder: number
  dealTypeCode: string
  customerCompanyId: string
  contactId: string | null
  contactName: string | null
  ownerMemberId: string
  productId: string | null
  title: string
  description: string | null
  closedOn: string | null
  quoteNo: string | null
  quoteIssuedOn: string | null
  quoteValidUntil: string | null
  contractNo: string | null
  contractSignedOn: string | null
  contractEndsOn: string | null
  warrantyTerms: string | null
  expectedDeliveryAt: string | null
  createdAt: string
  updatedAt: string
}

function requestErrorMessage(error: unknown, target: '목록' | '상세'): string {
  const fallback = '영업 딜 ' + target + '을 불러오지 못했습니다.'
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return '영업 딜 ' + target + '을 조회할 권한이 없습니다.'
  if (error.response?.status === 404) return '영업 딜을 찾을 수 없습니다. 목록을 다시 불러오세요.'
  if (error.response?.status === 422)
    return '영업 딜 ' + target + ' 조회 조건을 처리하지 못했습니다.'
  return transportMessage(error) ?? fallback
}

function mutationErrorMessage(error: unknown, action: string): string {
  const fallback = action + '하지 못했습니다.'
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return action + '할 권한이 없습니다.'
  if (error.response?.status === 404) return '영업 딜을 찾을 수 없습니다. 목록을 새로고침해 주세요.'
  if (error.response?.status === 409)
    return '다른 변경이 먼저 반영되었습니다. 목록을 새로고침한 뒤 다시 시도해 주세요.'
  if (error.response?.status === 422) return '입력한 값이나 이동할 위치를 확인해 주세요.'
  return transportMessage(error) ?? fallback
}

function toColumn(stage: SalesPipelineStageResponse): SalesDealColumn {
  return {
    id: stage.id,
    name: stage.name,
    tone: stage.tone,
    outcome: STATUS_BY_OUTCOME[stage.outcome_code],
    phase: stage.phase_code,
  }
}

function regionLabel(code: string | null): string {
  if (code === null) return '미지정'
  return REGION_LABEL[code] ?? code
}

export function toSalesDeal(deal: SalesDealResponse): SalesDeal {
  return {
    id: deal.id,
    no: deal.deal_no,
    org: deal.customer_company_name,
    product: deal.product_name ?? '상품 미지정',
    amount: deal.deal_amount,
    kind: deal.deal_type_name,
    status: STATUS_BY_OUTCOME[deal.sales_pipeline_stage_outcome_code],
    signedOff: Math.round((parseISO(deal.opened_on).getTime() - TODAY.getTime()) / 86_400_000),
    owner: deal.owner_display_name,
    date: deal.opened_on,
    region: regionLabel(deal.customer_company_region_code),
    memo: deal.memo ?? undefined,
    stageId: deal.sales_pipeline_stage_id,
    order: deal.stage_position,
    pipelineId: deal.sales_pipeline_id,
    pipelineName: deal.sales_pipeline_name,
    pipelineStatus: deal.sales_pipeline_status_code,
    stageCode: deal.sales_pipeline_stage_code,
    stageName: deal.sales_pipeline_stage_name,
    stageTone: deal.sales_pipeline_stage_tone,
    stagePhase: deal.sales_pipeline_stage_phase_code,
    stageOrder: deal.sales_pipeline_stage_position,
    dealTypeCode: deal.deal_type_code,
    customerCompanyId: deal.customer_company_id,
    contactId: deal.customer_contact_id,
    contactName: deal.customer_contact_name,
    ownerMemberId: deal.owner_member_id,
    productId: deal.product_id,
    title: deal.title,
    description: deal.description,
    closedOn: deal.closed_on,
    quoteNo: deal.quote_no,
    quoteIssuedOn: deal.quote_issued_on,
    quoteValidUntil: deal.quote_valid_until,
    contractNo: deal.contract_no,
    contractSignedOn: deal.contract_signed_on,
    contractEndsOn: deal.contract_ends_on,
    warrantyTerms: deal.warranty_terms,
    expectedDeliveryAt: deal.expected_delivery_at,
    createdAt: deal.created_at,
    updatedAt: deal.updated_at,
  }
}

async function fetchAllPage<T>(
  path: string,
  signal?: AbortSignal,
  params?: Record<string, unknown>,
): Promise<T[]> {
  // ponytail: 현재 UI의 건수·정렬은 전건 기준입니다. 데이터가 커지면 서버 집계·정렬로 바꿉니다.
  const items: T[] = []
  let skip = 0

  while (!signal?.aborted) {
    const { data } = await client.get<PageResponse<T>>(path, {
      params: { ...params, skip, limit: PAGE_LIMIT },
      signal,
    })
    items.push(...data.items)
    if (!data.has_more || data.next_skip === null) break
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }

  return items
}

async function fetchAllSalesDeals(
  signal?: AbortSignal,
  pipelineId?: string | null,
  phaseCode?: SalesPipelinePhaseCode,
  ownerIds?: readonly string[],
): Promise<SalesDeal[]> {
  const params = {
    ...(pipelineId ? { sales_pipeline_id: pipelineId } : {}),
    ...(phaseCode ? { phase_code: phaseCode } : {}),
    ...(ownerIds ? { owner_member_id: ownerIds } : {}),
  }
  return (await fetchAllPage<SalesDealResponse>('/sales-deals', signal, params)).map(toSalesDeal)
}

export interface SalesDealQuery {
  q: string
  /** 고른 단계 탭. 빈 문자열이면 전체입니다. */
  stageId: string
  /** 담당자. 빈 문자열이면 전체입니다. */
  ownerMemberId: string
  /** 시작일 하한. null 이면 제한 없음입니다. */
  fromISO: string | null
  skip: number
  limit: number
}

interface SalesDealPageResult {
  cards: SalesDeal[]
  total: number
  counts: Record<string, number>
}

async function fetchSalesDealPage(
  signal: AbortSignal,
  pipelineId: string | null | undefined,
  phaseCode: SalesPipelinePhaseCode | undefined,
  ownerIds: readonly string[] | undefined,
  query: SalesDealQuery,
): Promise<SalesDealPageResult> {
  const needle = query.q.trim()
  const { data } = await client.get<TabbedPageResponse<SalesDealResponse>>('/sales-deals', {
    params: {
      ...(pipelineId ? { sales_pipeline_id: pipelineId } : {}),
      ...(phaseCode ? { phase_code: phaseCode } : {}),
      // 담당자를 고르면 그 사람만, 아니면 보기 범위를 따릅니다.
      owner_member_id: query.ownerMemberId === '' ? ownerIds : [query.ownerMemberId],
      q: needle === '' ? undefined : needle.slice(0, 100),
      // 파이프라인을 고르지 않으면 단계 탭이 뜨지 않으므로 단계도 걸지 않습니다.
      sales_pipeline_stage_id: pipelineId && query.stageId !== '' ? query.stageId : undefined,
      start_date: query.fromISO ?? undefined,
      skip: query.skip,
      limit: query.limit,
    },
    signal,
  })
  return { cards: data.items.map(toSalesDeal), total: data.total, counts: data.counts }
}

function toCreateRequest(
  input: SalesDealSaveInput,
  pipelineId: string,
  stageId: string,
): SalesDealCreateRequest {
  return {
    customer_company_id: input.customerCompanyId,
    customer_contact_id: null,
    product_id: input.productId,
    sales_pipeline_id: pipelineId,
    sales_pipeline_stage_id: stageId,
    deal_type_code: input.dealTypeCode,
    deal_amount: input.amount,
    opened_on: input.date,
    memo: input.memo,
  }
}

function toPatchRequest(
  input: SalesDealSaveInput,
  currentCustomerCompanyId: string | undefined,
  currentProductId: string | null | undefined,
  currentDealTypeCode: string | undefined,
): SalesDealPatchRequest {
  return {
    customer_company_id: input.customerCompanyId,
    ...(currentCustomerCompanyId !== undefined &&
      currentCustomerCompanyId !== input.customerCompanyId && { customer_contact_id: null }),
    ...(currentProductId !== input.productId && { product_id: input.productId }),
    ...(currentDealTypeCode !== input.dealTypeCode && { deal_type_code: input.dealTypeCode }),
    deal_amount: input.amount,
    opened_on: input.date,
    memo: input.memo,
  }
}

/**
 * `query` 를 주면 목록을 한 쪽씩 받습니다. 주지 않으면 전건을 받습니다.
 *
 * 칸반과 매출 요약은 열 머리의 합계·기간별 집계를 전건 위에서 계산하므로 아직 전건이
 * 필요합니다. 목록 화면만 쪽으로 끊습니다.
 */
export default function useSalesDeals(
  openId: string | null,
  requestedPipelineId: string | null,
  mode: 'list' | 'board',
  phaseCode?: SalesPipelinePhaseCode,
  query?: SalesDealQuery,
) {
  const [pipelines, setPipelines] = useState<SalesPipelineResponse[]>([])
  const [dealPipelineId, setDealPipelineId] = useState<string | null>(null)
  const [stagePipelineId, setStagePipelineId] = useState<string | null>(null)
  const [columns, setColumns] = useState<SalesDealColumn[]>([])
  const [cards, setCards] = useState<SalesDeal[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [dealTypes, setDealTypes] = useState<SalesDealTypeResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [detail, setDetail] = useState<SalesDeal | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailReloadKey, setDetailReloadKey] = useState(0)

  const pendingRef = useRef(new Set<string>())
  const [pendingKeys, setPendingKeys] = useState<ReadonlySet<string>>(() => new Set())
  const [mutationError, setMutationError] = useState<string | null>(null)
  const ownerIds = useScopeOwnerIds()
  const [optionsReady, setOptionsReady] = useState(false)

  // 조회 조건을 낱개로 펼쳐 둡니다. 아래 효과가 객체가 아니라 값 하나하나를 보게 해야,
  // 화면이 조건 객체를 새로 만들 때마다 다시 받지 않습니다.
  const paging = query !== undefined
  const {
    q: queryText = '',
    stageId: queryStageId = '',
    ownerMemberId: queryOwnerId = '',
    fromISO: queryFrom = null,
    skip: querySkip = 0,
    limit: queryLimit = 30,
  } = query ?? {}

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void client
      .get<SalesPipelineResponse[]>('/sales-pipelines', { signal: controller.signal })
      .then(async ({ data: pipelineItems }) => {
        const requested = pipelineItems.find(({ id }) => id === requestedPipelineId)
        const fallback =
          pipelineItems.find(
            ({ is_default, status_code }) => is_default && status_code === 'published',
          ) ??
          pipelineItems.find(({ status_code }) => status_code === 'published') ??
          pipelineItems[0]
        const stagePipeline = requested ?? fallback
        const filteredPipelineId = mode === 'board' ? stagePipeline?.id : requested?.id

        const [stageItems, dealItems, dealTypeItems] = await Promise.all([
          stagePipeline
            ? client
                .get<SalesPipelineStageResponse[]>(`/sales-pipelines/${stagePipeline.id}/stages`, {
                  signal: controller.signal,
                })
                .then((response) => response.data)
            : Promise.resolve([]),
          // 조회 조건을 받은 목록 화면은 아래 효과가 한 쪽만 받습니다. 여기서 전건을
          // 받는 것은 칸반과 매출 요약처럼 전건 집계가 필요한 쪽뿐입니다.
          paging
            ? Promise.resolve([])
            : fetchAllSalesDeals(controller.signal, filteredPipelineId, phaseCode, ownerIds),
          client
            .get<SalesDealTypeResponse[]>('/sales-deal-types', { signal: controller.signal })
            .then((response) => response.data),
        ])

        if (controller.signal.aborted) return
        setPipelines(pipelineItems)
        setDealPipelineId(filteredPipelineId ?? null)
        setStagePipelineId(stagePipeline?.id ?? null)
        setColumns(stageItems.map(toColumn))
        if (!paging) setCards(dealItems)
        setDealTypes(dealTypeItems)
        setOptionsReady(true)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(requestErrorMessage(caught, '목록'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [mode, phaseCode, reloadKey, requestedPipelineId, ownerIds, paging])

  // 목록 한 쪽. 파이프라인을 정한 뒤에 부릅니다. 정하기 전에 부르면 전체 파이프라인의
  // 딜이 잠깐 보였다가 바뀝니다.
  useEffect(() => {
    if (!paging || !optionsReady) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void fetchSalesDealPage(controller.signal, dealPipelineId, phaseCode, ownerIds, {
      q: queryText,
      stageId: queryStageId,
      ownerMemberId: queryOwnerId,
      fromISO: queryFrom,
      skip: querySkip,
      limit: queryLimit,
    })
      .then(({ cards: pageCards, total: pageTotal, counts: pageCounts }) => {
        if (controller.signal.aborted) return
        setCards(pageCards)
        setTotal(pageTotal)
        setCounts(pageCounts)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(requestErrorMessage(caught, '목록'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [
    paging,
    optionsReady,
    dealPipelineId,
    phaseCode,
    ownerIds,
    reloadKey,
    queryText,
    queryStageId,
    queryOwnerId,
    queryFrom,
    querySkip,
    queryLimit,
  ])

  useEffect(() => {
    if (openId === null) {
      setDetail(null)
      setDetailError(null)
      setDetailLoading(false)
      return
    }

    const controller = new AbortController()
    setDetail(null)
    setDetailError(null)
    setDetailLoading(true)

    void client
      .get<SalesDealResponse>('/sales-deals/' + openId, { signal: controller.signal })
      .then(({ data }) => {
        if (!controller.signal.aborted) setDetail(toSalesDeal(data))
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setDetailError(requestErrorMessage(caught, '상세'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false)
      })

    return () => controller.abort()
  }, [openId, detailReloadKey])

  const reload = useCallback(() => setReloadKey((value) => value + 1), [])
  const reloadDetail = useCallback(() => setDetailReloadKey((value) => value + 1), [])
  const clearMutationError = useCallback(() => setMutationError(null), [])

  const syncSalesDeals = useCallback(async () => {
    try {
      // 범위를 빠뜨리면 고치자마자 화면이 조용히 팀 전체로 되돌아갑니다.
      setCards(await fetchAllSalesDeals(undefined, dealPipelineId, phaseCode, ownerIds))
    } catch {
      setMutationError('변경은 저장됐지만 최신 목록을 불러오지 못했습니다. 새로고침해 주세요.')
    }
  }, [dealPipelineId, phaseCode, ownerIds])

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

  const createSalesDeal = useCallback(
    (input: SalesDealSaveInput, stageId: string) =>
      runMutation('create', '영업 딜을 등록', async () => {
        if (stagePipelineId === null) throw new Error('사용할 영업 파이프라인이 없습니다.')
        const { data } = await client.post<SalesDealResponse>(
          '/sales-deals',
          toCreateRequest(input, stagePipelineId, stageId),
        )
        const created = toSalesDeal(data)
        setCards((previous) => [created, ...previous])
        await syncSalesDeals()
        return created
      }),
    [runMutation, stagePipelineId, syncSalesDeals],
  )

  const updateSalesDeal = useCallback(
    (id: string, input: SalesDealSaveInput) =>
      runMutation(id, '영업 딜을 수정', async () => {
        const current = cards.find((card) => card.id === id)
        const { data } = await client.patch<SalesDealResponse>(
          '/sales-deals/' + id,
          toPatchRequest(
            input,
            current?.customerCompanyId,
            current?.productId,
            current?.dealTypeCode,
          ),
        )
        const updated = toSalesDeal(data)
        setCards((previous) => previous.map((card) => (card.id === id ? updated : card)))
        setDetail((previous) => (previous?.id === id ? updated : previous))
        await syncSalesDeals()
        return updated
      }),
    [cards, runMutation, syncSalesDeals],
  )

  const deleteSalesDeal = useCallback(
    (id: string) =>
      runMutation(id, '영업 딜을 삭제', async () => {
        await client.delete('/sales-deals/' + id)
        setCards((previous) => previous.filter((card) => card.id !== id))
        setDetail((previous) => (previous?.id === id ? null : previous))
        await syncSalesDeals()
      }),
    [runMutation, syncSalesDeals],
  )

  const moveSalesDeal = useCallback(
    (id: string, expectedStageId: string, stageId: string, position: number) =>
      runMutation(id, '영업 딜을 이동', async () => {
        const payload: SalesDealMoveRequest = {
          expected_sales_pipeline_stage_id: expectedStageId,
          sales_pipeline_stage_id: stageId,
          stage_position: position,
        }
        const { data } = await client.post<SalesDealResponse>(
          '/sales-deals/' + id + '/move',
          payload,
        )
        const moved = toSalesDeal(data)
        setCards((previous) => previous.map((card) => (card.id === id ? moved : card)))
        setDetail((previous) => (previous?.id === id ? moved : previous))
        await syncSalesDeals()
        return moved
      }),
    [runMutation, syncSalesDeals],
  )

  const activePipeline = pipelines.find(({ id }) => id === stagePipelineId)
  const isPending = useCallback((id: string) => pendingKeys.has(id), [pendingKeys])

  return {
    pipelines,
    dealPipelineId,
    stagePipelineId,
    activePipeline,
    columns,
    cards,
    total,
    counts,
    dealTypes,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
    mutationError,
    clearMutationError,
    canCreate: activePipeline?.status_code === 'published' && columns.length > 0,
    isCreating: pendingKeys.has('create'),
    isPending,
    createSalesDeal,
    updateSalesDeal,
    deleteSalesDeal,
    moveSalesDeal,
  }
}
