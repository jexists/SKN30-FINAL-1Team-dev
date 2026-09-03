import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { transportMessage } from '@/api/errorMessage'
import { useScopeOwnerIds } from '@/shared/scope'
import type {
  ColumnTone,
  CustomerSourceCode,
  DocumentStatusResponse,
  PageResponse,
  SalesDealCreateRequest,
  SalesDealDocumentFields,
  SalesDealItemResponse,
  SalesDealMoveRequest,
  SalesDealParticipantResponse,
  SalesDealPatchRequest,
  SalesDealResponse,
  TabbedPageResponse,
  SalesDealStatus,
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

/**
 * 견적·계약 목록이 보는 국면입니다. 파이프라인 단계(phase_code)로 거르면 계약으로
 * 넘어간 딜이 견적현황에서 사라지므로, 그 국면의 상태가 붙었는지로 거릅니다.
 */
export type DealDocumentKind = 'quote' | 'contract'

const DOCUMENT_PARAMS: Record<DealDocumentKind, Record<string, unknown>> = {
  quote: { has_quote: true, date_basis: 'quote_issued' },
  contract: { has_contract: true, date_basis: 'contract_signed' },
}

/** 국면마다 상태 목록을 받는 곳이 다릅니다. */
const STATUS_PATH: Record<DealDocumentKind, string> = {
  quote: '/quote-statuses',
  contract: '/contract-statuses',
}

export interface SalesDealSaveInput {
  customerCompanyId: string
  productId: string
  /** 비우면 서버가 '회사명 제품명' 으로 채웁니다. */
  title: string | null
  amount: number
  dealTypeCode: string
  date: string
  memo: string | null
  /** 유입경로. 모를 수 있는 값이라 비워 둘 수 있습니다. */
  sourceCode: CustomerSourceCode | null
  /** 딜을 넣을 파이프라인 단계. 수정에서는 쓰지 않습니다. */
  stageId: string
  /** 미팅 대상자. 고객사에 속한 사람만 넣을 수 있습니다. */
  participantContactIds: string[]
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
  sourceCode: string | null
  customerCompanyId: string
  contactId: string | null
  contactName: string | null
  ownerMemberId: string
  productId: string | null
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
  quoteStatusId: string | null
  quoteStatusCode: string | null
  quoteStatusName: string | null
  quoteStatusTone: ColumnTone | null
  contractStatusId: string | null
  contractStatusCode: string | null
  contractStatusName: string | null
  contractStatusTone: ColumnTone | null
  quoteAmount: number | null
  contractAmount: number | null
  quoteDeliveryTerms: string | null
  contractPaymentTerms: string | null
  contractLateInterestTerms: string | null
  teamCompanyName: string | null
  teamBusinessNo: string | null
  companyBusinessNo: string | null
  items: SalesDealItemResponse[]
  participants: SalesDealParticipantResponse[]
  orderStatusCode: string | null
  orderStatusName: string | null
  orderStatusTone: ColumnTone | null
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
    title: deal.title,
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
    sourceCode: deal.source_code,
    customerCompanyId: deal.customer_company_id,
    contactId: deal.customer_contact_id,
    contactName: deal.customer_contact_name,
    ownerMemberId: deal.owner_member_id,
    productId: deal.product_id,
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
    quoteStatusId: deal.quote_status_id,
    quoteStatusCode: deal.quote_status_code,
    quoteStatusName: deal.quote_status_name,
    quoteStatusTone: deal.quote_status_tone,
    contractStatusId: deal.contract_status_id,
    contractStatusCode: deal.contract_status_code,
    contractStatusName: deal.contract_status_name,
    contractStatusTone: deal.contract_status_tone,
    quoteAmount: deal.quote_amount,
    contractAmount: deal.contract_amount,
    quoteDeliveryTerms: deal.quote_delivery_terms,
    contractPaymentTerms: deal.contract_payment_terms,
    contractLateInterestTerms: deal.contract_late_interest_terms,
    teamCompanyName: deal.team_company_name,
    teamBusinessNo: deal.team_business_no,
    companyBusinessNo: deal.customer_company_business_no,
    items: [...deal.items].sort((a, b) => a.position - b.position),
    participants: deal.participants,
    orderStatusCode: deal.order_status_code,
    orderStatusName: deal.order_status_name,
    orderStatusTone: deal.order_status_tone,
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
  documentKind?: DealDocumentKind,
  ownerIds?: readonly string[],
): Promise<SalesDeal[]> {
  const params = {
    ...(pipelineId ? { sales_pipeline_id: pipelineId } : {}),
    ...(documentKind ? DOCUMENT_PARAMS[documentKind] : {}),
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
  documentKind: DealDocumentKind | undefined,
  ownerIds: readonly string[] | undefined,
  query: SalesDealQuery,
): Promise<SalesDealPageResult> {
  const needle = query.q.trim()
  const tab = query.stageId === '' ? undefined : query.stageId
  const { data } = await client.get<TabbedPageResponse<SalesDealResponse>>('/sales-deals', {
    params: {
      ...(pipelineId ? { sales_pipeline_id: pipelineId } : {}),
      ...(documentKind ? DOCUMENT_PARAMS[documentKind] : {}),
      // 담당자를 고르면 그 사람만, 아니면 보기 범위를 따릅니다.
      owner_member_id: query.ownerMemberId === '' ? ownerIds : [query.ownerMemberId],
      q: needle === '' ? undefined : needle.slice(0, 100),
      // 견적·계약 탭은 그 국면의 상태입니다. 영업 목록만 파이프라인 단계로 거르고,
      // 파이프라인을 고르지 않으면 단계 탭이 뜨지 않으므로 단계도 걸지 않습니다.
      sales_pipeline_stage_id:
        documentKind === undefined && pipelineId && tab !== undefined ? tab : undefined,
      quote_status_id: documentKind === 'quote' ? tab : undefined,
      contract_status_id: documentKind === 'contract' ? tab : undefined,
      start_date: query.fromISO ?? undefined,
      skip: query.skip,
      limit: query.limit,
    },
    signal,
  })
  return { cards: data.items.map(toSalesDeal), total: data.total, counts: data.counts }
}

function toCreateRequest(input: SalesDealSaveInput, pipelineId: string): SalesDealCreateRequest {
  return {
    customer_company_id: input.customerCompanyId,
    customer_contact_id: null,
    product_id: input.productId,
    sales_pipeline_id: pipelineId,
    sales_pipeline_stage_id: input.stageId,
    deal_type_code: input.dealTypeCode,
    deal_amount: input.amount,
    opened_on: input.date,
    memo: input.memo,
    source_code: input.sourceCode,
    ...(input.title === null ? {} : { title: input.title }),
    participant_contact_ids: input.participantContactIds,
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
    source_code: input.sourceCode,
    ...(input.title === null ? {} : { title: input.title }),
    participant_contact_ids: input.participantContactIds,
  }
}

/** 파이프라인 칸의 기본값. 실제 기본 파이프라인 하나로 좁혀 봅니다. */
export const DEFAULT_PIPELINE = 'default'

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
  documentKind?: DealDocumentKind,
  query?: SalesDealQuery,
) {
  const [pipelines, setPipelines] = useState<SalesPipelineResponse[]>([])
  const [dealPipelineId, setDealPipelineId] = useState<string | null>(null)
  const [stagePipelineId, setStagePipelineId] = useState<string | null>(null)
  const [columns, setColumns] = useState<SalesDealColumn[]>([])
  const [cards, setCards] = useState<SalesDeal[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<Record<string, number>>({})
  // 견적·계약 상태. 이름과 색은 서버가 정합니다. 그 국면을 보는 화면(견적현황·계약현황)
  // 은 탭이 바로 쓰므로 처음에 받고, 영업현황·보드는 서류 모달을 열 때만 필요하므로
  // `loadDocumentStatuses` 로 그때 받습니다.
  const [quoteStatuses, setQuoteStatuses] = useState<DocumentStatusResponse[]>([])
  const [contractStatuses, setContractStatuses] = useState<DocumentStatusResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [detail, setDetail] = useState<SalesDeal | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailReloadKey, setDetailReloadKey] = useState(0)

  const pendingRef = useRef(new Set<string>())
  // 이미 받았거나 받는 중인 상태 목록. 모달을 여닫을 때마다 다시 부르지 않습니다.
  const documentStatusRef = useRef<Partial<Record<DealDocumentKind, Promise<void>>>>({})
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
        // 파이프라인을 고르지 않은 목록은 기본 파이프라인을 봅니다. 전체는 골라야 봅니다.
        const filteredPipelineId =
          mode === 'board' || requestedPipelineId === DEFAULT_PIPELINE
            ? stagePipeline?.id
            : requested?.id

        const [stageItems, dealItems, documentStatusItems] = await Promise.all([
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
            : fetchAllSalesDeals(controller.signal, filteredPipelineId, documentKind, ownerIds),
          // 탭이 이 국면의 상태로 서므로 화면과 함께 받습니다. 국면을 보지 않는 화면은
          // 받지 않습니다.
          documentKind
            ? client
                .get<DocumentStatusResponse[]>(STATUS_PATH[documentKind], {
                  signal: controller.signal,
                })
                .then((response) => response.data)
            : Promise.resolve([]),
        ])

        if (controller.signal.aborted) return
        setPipelines(pipelineItems)
        setDealPipelineId(filteredPipelineId ?? null)
        setStagePipelineId(stagePipeline?.id ?? null)
        setColumns(stageItems.map(toColumn))
        if (!paging) setCards(dealItems)
        if (documentKind === 'quote') setQuoteStatuses(documentStatusItems)
        if (documentKind === 'contract') setContractStatuses(documentStatusItems)
        setOptionsReady(true)
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(requestErrorMessage(caught, '목록'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [mode, documentKind, reloadKey, requestedPipelineId, ownerIds, paging])

  // 목록 한 쪽. 파이프라인을 정한 뒤에 부릅니다. 정하기 전에 부르면 전체 파이프라인의
  // 딜이 잠깐 보였다가 바뀝니다.
  useEffect(() => {
    if (!paging || !optionsReady) return
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    void fetchSalesDealPage(controller.signal, dealPipelineId, documentKind, ownerIds, {
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
    documentKind,
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

  /**
   * 서류 모달이 쓸 상태 목록을 그때 받습니다.
   *
   * 견적·계약 모달은 열릴 때의 목록으로 첫 상태를 정하므로, 모달을 세우기 전에 이
   * 약속이 끝나야 합니다. 실패해도 되돌려주고 모달은 뜨며, 상태 칸이 비어 저장이
   * 막힙니다.
   */
  const loadDocumentStatuses = useCallback(async (kind: DealDocumentKind) => {
    documentStatusRef.current[kind] ??= client
      .get<DocumentStatusResponse[]>(STATUS_PATH[kind])
      .then(({ data }) => {
        if (kind === 'quote') setQuoteStatuses(data)
        else setContractStatuses(data)
      })
      .catch(() => {
        documentStatusRef.current[kind] = undefined
        setMutationError('견적·계약 상태 목록을 불러오지 못했습니다. 다시 시도해 주세요.')
      })
    await documentStatusRef.current[kind]
  }, [])

  const syncSalesDeals = useCallback(async () => {
    try {
      // 범위를 빠뜨리면 고치자마자 화면이 조용히 팀 전체로 되돌아갑니다.
      setCards(await fetchAllSalesDeals(undefined, dealPipelineId, documentKind, ownerIds))
    } catch {
      setMutationError('변경은 저장됐지만 최신 목록을 불러오지 못했습니다. 새로고침해 주세요.')
    }
  }, [dealPipelineId, documentKind, ownerIds])

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
    (input: SalesDealSaveInput) =>
      runMutation('create', '영업 딜을 등록', async () => {
        if (stagePipelineId === null) throw new Error('사용할 영업 파이프라인이 없습니다.')
        const { data } = await client.post<SalesDealResponse>(
          '/sales-deals',
          toCreateRequest(input, stagePipelineId),
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

  /**
   * 견적·계약 값을 저장합니다. 둘 다 딜의 컬럼이라 딜 수정과 같은 곳으로 갑니다.
   * 상태를 처음 넣으면 서버가 딜을 그 국면의 첫 단계로 옮깁니다.
   */
  const saveDealDocument = useCallback(
    (id: string, fields: SalesDealDocumentFields, action: string) =>
      runMutation(id, action, async () => {
        const { data } = await client.patch<SalesDealResponse>('/sales-deals/' + id, fields)
        const updated = toSalesDeal(data)
        setCards((previous) => previous.map((card) => (card.id === id ? updated : card)))
        setDetail((previous) => (previous?.id === id ? updated : previous))
        return updated
      }),
    [runMutation],
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
    quoteStatuses,
    contractStatuses,
    loadDocumentStatuses,
    // 이 화면이 보는 국면의 상태. 탭이 씁니다.
    documentStatuses:
      documentKind === 'quote'
        ? quoteStatuses
        : documentKind === 'contract'
          ? contractStatuses
          : [],
    createSalesDeal,
    updateSalesDeal,
    saveDealDocument,
    deleteSalesDeal,
    moveSalesDeal,
  }
}
