import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import type {
  ContractCreateRequest,
  ContractKind,
  ContractKindCode,
  ContractMoveRequest,
  ContractPatchRequest,
  ContractResponse,
  ContractStatus,
  CustomerCompanyResponse,
  PageResponse,
  PipelineOutcomeCode,
  PipelineStageResponse,
  ProductResponse,
} from '@/types'
import { parseISO, TODAY } from '@/utils/date'

import type { BoardColumn, BoardContract } from './board'

const PAGE_LIMIT = 100

const STATUS_BY_OUTCOME: Record<PipelineOutcomeCode, ContractStatus> = {
  in_progress: '진행중',
  confirmed: '확정',
  cancelled: '취소',
}

const KIND_BY_CODE: Record<ContractKindCode, ContractKind> = {
  new_installation: '신규 도입',
  expansion: '증설',
  renewal: '갱신',
  maintenance: '유지보수',
  consumables_supply: '소모품 공급',
}

const CODE_BY_KIND: Record<ContractKind, ContractKindCode> = {
  '신규 도입': 'new_installation',
  증설: 'expansion',
  갱신: 'renewal',
  유지보수: 'maintenance',
  '소모품 공급': 'consumables_supply',
}

const REGION_LABEL: Record<string, string> = {
  seoul: '서울',
  gyeonggi: '경기',
  incheon: '인천',
  chungnam: '충남',
}

export interface PipelineOption {
  id: string
  name: string
}

export interface PipelineContractSaveInput {
  customerCompanyId: string
  productId: string
  amount: number
  kind: ContractKind
  date: string
  memo: string | null
}

export interface PipelineContract extends BoardContract {
  /** API 요청에 쓰는 내부 UUID. contract_no 대신 이 값을 식별자로 사용합니다. */
  id: string
  customerCompanyId: string
  contactId: string | null
  contactName: string | null
  ownerMemberId: string
  productId: string | null
  title: string
  description: string | null
  endsOn: string | null
  warrantyTerms: string | null
  expectedDeliveryAt: string | null
  createdAt: string
  updatedAt: string
}

function requestErrorMessage(error: unknown, target: '목록' | '상세'): string {
  if (!isAxiosError(error)) return '계약 ' + target + '을 불러오지 못했습니다.'
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return '계약 ' + target + '을 조회할 권한이 없습니다.'
  if (error.response?.status === 404) return '계약을 찾을 수 없습니다. 목록을 다시 불러오세요.'
  if (error.response?.status === 422) return '계약 ' + target + ' 조회 조건을 처리하지 못했습니다.'
  return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

function mutationErrorMessage(error: unknown, action: string): string {
  if (!isAxiosError(error)) return action + '하지 못했습니다.'
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 403) return action + '할 권한이 없습니다.'
  if (error.response?.status === 404) return '계약을 찾을 수 없습니다. 목록을 새로고침해 주세요.'
  if (error.response?.status === 409)
    return '다른 변경이 먼저 반영되었습니다. 목록을 새로고침한 뒤 다시 시도해 주세요.'
  if (error.response?.status === 422) return '입력한 값이나 이동할 위치를 확인해 주세요.'
  return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

function toColumn(stage: PipelineStageResponse): BoardColumn {
  return {
    id: stage.id,
    name: stage.name,
    tone: stage.tone,
    outcome: STATUS_BY_OUTCOME[stage.outcome_code],
  }
}

function regionLabel(code: string | null): string {
  if (code === null) return '미지정'
  return REGION_LABEL[code] ?? code
}

function toContract(contract: ContractResponse): PipelineContract {
  return {
    id: contract.id,
    no: contract.contract_no,
    org: contract.customer_company_name,
    product: contract.product_name ?? '상품 미지정',
    amount: contract.amount,
    kind: KIND_BY_CODE[contract.contract_type],
    status: STATUS_BY_OUTCOME[contract.stage_outcome_code],
    signedOff: Math.round(
      (parseISO(contract.contract_date).getTime() - TODAY.getTime()) / 86_400_000,
    ),
    owner: contract.owner_display_name,
    date: contract.contract_date,
    region: regionLabel(contract.customer_company_region_code),
    memo: contract.memo ?? undefined,
    stageId: contract.stage_id,
    order: contract.position,
    customerCompanyId: contract.customer_company_id,
    contactId: contract.contact_id,
    contactName: contract.contact_name,
    ownerMemberId: contract.owner_member_id,
    productId: contract.product_id,
    title: contract.title,
    description: contract.description,
    endsOn: contract.ends_on,
    warrantyTerms: contract.warranty_terms,
    expectedDeliveryAt: contract.expected_delivery_at,
    createdAt: contract.created_at,
    updatedAt: contract.updated_at,
  }
}

async function fetchAllPage<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  // ponytail: 현재 UI의 건수·정렬은 전건 기준입니다. 데이터가 커지면 서버 집계·정렬로 바꿉니다.
  const items: T[] = []
  let skip = 0

  while (!signal?.aborted) {
    const { data } = await client.get<PageResponse<T>>(path, {
      params: { skip, limit: PAGE_LIMIT },
      signal,
    })
    items.push(...data.items)
    if (!data.has_more || data.next_skip === null) break
    if (data.next_skip <= skip) throw new Error('invalid_pagination')
    skip = data.next_skip
  }

  return items
}

async function fetchAllContracts(signal?: AbortSignal): Promise<PipelineContract[]> {
  const items = await fetchAllPage<ContractResponse>('/contracts', signal)
  return items.map(toContract)
}

function toCreateRequest(input: PipelineContractSaveInput, stageId: string): ContractCreateRequest {
  return {
    customer_company_id: input.customerCompanyId,
    contact_id: null,
    product_id: input.productId,
    stage_id: stageId,
    contract_type: CODE_BY_KIND[input.kind],
    amount: input.amount,
    contract_date: input.date,
    memo: input.memo,
  }
}

function toPatchRequest(
  input: PipelineContractSaveInput,
  currentCustomerCompanyId: string | undefined,
): ContractPatchRequest {
  return {
    customer_company_id: input.customerCompanyId,
    ...(currentCustomerCompanyId !== undefined &&
      currentCustomerCompanyId !== input.customerCompanyId && { contact_id: null }),
    product_id: input.productId,
    contract_type: CODE_BY_KIND[input.kind],
    amount: input.amount,
    contract_date: input.date,
    memo: input.memo,
  }
}

export default function usePipelineContracts(openId: string | null) {
  const [columns, setColumns] = useState<BoardColumn[]>([])
  const [cards, setCards] = useState<PipelineContract[]>([])
  const [companies, setCompanies] = useState<PipelineOption[]>([])
  const [products, setProducts] = useState<PipelineOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [detail, setDetail] = useState<PipelineContract | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailReloadKey, setDetailReloadKey] = useState(0)

  const pendingRef = useRef(new Set<string>())
  const [pendingKeys, setPendingKeys] = useState<ReadonlySet<string>>(() => new Set())
  const [mutationError, setMutationError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    setLoading(true)
    setError(null)

    void Promise.all([
      client.get<PipelineStageResponse[]>('/pipeline-stages', { signal: controller.signal }),
      fetchAllContracts(controller.signal),
      fetchAllPage<CustomerCompanyResponse>('/customer-companies', controller.signal),
      fetchAllPage<ProductResponse>('/products', controller.signal),
    ])
      .then(([stageResponse, contractItems, companyItems, productItems]) => {
        if (controller.signal.aborted) return
        setColumns(stageResponse.data.map(toColumn))
        setCards(contractItems)
        setCompanies(companyItems.map(({ id, name }) => ({ id, name })))
        setProducts(productItems.map(({ id, name }) => ({ id, name })))
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(requestErrorMessage(caught, '목록'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [reloadKey])

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
      .get<ContractResponse>('/contracts/' + openId, { signal: controller.signal })
      .then(({ data }) => {
        if (!controller.signal.aborted) setDetail(toContract(data))
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

  const syncContracts = useCallback(async () => {
    try {
      setCards(await fetchAllContracts())
    } catch {
      setMutationError('변경은 저장됐지만 최신 목록을 불러오지 못했습니다. 새로고침해 주세요.')
    }
  }, [])

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

  const createContract = useCallback(
    (input: PipelineContractSaveInput, stageId: string) =>
      runMutation('create', '계약을 등록', async () => {
        const { data } = await client.post<ContractResponse>(
          '/contracts',
          toCreateRequest(input, stageId),
        )
        const created = toContract(data)
        setCards((previous) => [created, ...previous])
        await syncContracts()
        return created
      }),
    [runMutation, syncContracts],
  )

  const updateContract = useCallback(
    (id: string, input: PipelineContractSaveInput) =>
      runMutation(id, '계약을 수정', async () => {
        const currentCustomerCompanyId = cards.find((card) => card.id === id)?.customerCompanyId
        const { data } = await client.patch<ContractResponse>(
          '/contracts/' + id,
          toPatchRequest(input, currentCustomerCompanyId),
        )
        const updated = toContract(data)
        setCards((previous) => previous.map((card) => (card.id === id ? updated : card)))
        setDetail((previous) => (previous?.id === id ? updated : previous))
        await syncContracts()
        return updated
      }),
    [cards, runMutation, syncContracts],
  )

  const deleteContract = useCallback(
    (id: string) =>
      runMutation(id, '계약을 삭제', async () => {
        await client.delete('/contracts/' + id)
        setCards((previous) => previous.filter((card) => card.id !== id))
        setDetail((previous) => (previous?.id === id ? null : previous))
        await syncContracts()
      }),
    [runMutation, syncContracts],
  )

  const moveContract = useCallback(
    (id: string, expectedStageId: string, stageId: string, position: number) =>
      runMutation(id, '계약을 이동', async () => {
        const payload: ContractMoveRequest = {
          expected_stage_id: expectedStageId,
          stage_id: stageId,
          position,
        }
        const { data } = await client.post<ContractResponse>('/contracts/' + id + '/move', payload)
        const moved = toContract(data)
        setCards((previous) => previous.map((card) => (card.id === id ? moved : card)))
        setDetail((previous) => (previous?.id === id ? moved : previous))
        await syncContracts()
        return moved
      }),
    [runMutation, syncContracts],
  )

  const isPending = useCallback((id: string) => pendingKeys.has(id), [pendingKeys])

  return {
    columns,
    cards,
    companies,
    products,
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
    createContract,
    updateContract,
    deleteContract,
    moveContract,
  }
}
