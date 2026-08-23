import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import ContractForm from '@/components/ContractForm'
import DataTable, { compareBy, type SortState } from '@/components/DataTable'
import FilterSelect from '@/components/FilterSelect'
import { ContractIcon, SearchIcon } from '@/components/icons'
import Pagination from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import StageChip from '@/components/StageChip'
import StageTabs from '@/components/StageTabs'
import SalesDealDrawer from '@/pages/Deals/SalesDealDrawer'
import useSalesDeals, { type SalesDeal } from '@/pages/Deals/useSalesDeals'
import { addDays, fmtDot, iso, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

import { CONTRACT_COLUMNS } from './columns'

import styles from '@/pages/listPage.module.scss'

const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

const DEFAULT_RANGE = '6'

export default function Contracts() {
  const [openId, setOpenId] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()

  // 일정 등록에서 '계약서 작성 화면으로 이동' 을 고르면 이 표를 달고 옵니다.
  // 목록만 띄우면 다시 추가를 눌러야 하므로, 작성 폼까지 열어 둡니다.
  const createOpen = params.get('new') === '1'
  const closeCreate = () => {
    const next = new URLSearchParams(params)
    next.delete('new')
    // 뒤로 가기가 방금 닫은 폼을 다시 열지 않게 기록을 남기지 않습니다.
    setParams(next, { replace: true })
  }

  const requestedPipelineId = params.get('pipeline') ?? ''
  const {
    pipelines,
    dealPipelineId,
    columns: pipelineStages,
    cards: contracts,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
  } = useSalesDeals(openId, requestedPipelineId || null, 'list', 'contract')
  const { isManager } = useCurrentUser()

  const query = params.get('q') ?? ''
  const owner = isManager ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const stage = params.get('stage') ?? ''
  const deferredQuery = useDeferredValue(query)

  const [sort, setSort] = useState<SortState>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [openFilter, setOpenFilter] = useState<'pipeline' | 'owner' | 'range' | null>(null)

  const pipelineOptions = useMemo(
    () => [
      { value: '', label: '파이프라인 전체' },
      ...pipelines.map((pipeline) => ({
        value: pipeline.id,
        label: pipeline.name + (pipeline.status_code === 'archived' ? ' (보관)' : ''),
      })),
    ],
    [pipelines],
  )

  const contractStages = useMemo(
    () => pipelineStages.filter((item) => item.phase === 'contract'),
    [pipelineStages],
  )
  const columns = useMemo(
    () => CONTRACT_COLUMNS.filter((column) => column.id !== 'owner' || isManager),
    [isManager],
  )
  const ownerOptions = useMemo(
    () => [
      { value: '', label: '담당 전체' },
      ...[...new Set(contracts.map((item) => item.owner))]
        .sort()
        .map((name) => ({ value: name, label: name })),
    ],
    [contracts],
  )

  const setParam = useCallback(
    (key: string, value: string, fallback = '') => {
      const next = new URLSearchParams(params)
      if (value === fallback) next.delete(key)
      else next.set(key, value)
      setParams(next, { replace: true })
      setPage(1)
    },
    [params, setParams],
  )

  const fromISO = useMemo(() => {
    const months = Number(range)
    if (!months) return null
    return iso(addDays(TODAY, -Math.round(months * 30.4)))
  }, [range])

  const setPipeline = useCallback(
    (value: string) => {
      const next = new URLSearchParams(params)
      if (value === '') next.delete('pipeline')
      else next.set('pipeline', value)
      next.delete('stage')
      setParams(next, { replace: true })
      setPage(1)
    },
    [params, setParams],
  )

  const beforeStage = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    return contracts.filter((contract) => {
      if (owner !== '' && contract.owner !== owner) return false
      if (fromISO !== null && (contract.contractSignedOn ?? contract.date) < fromISO) return false
      if (needle === '') return true
      return [
        contract.contractNo ?? contract.no,
        contract.org,
        contract.product,
        contract.owner,
        contract.memo ?? '',
      ]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [contracts, deferredQuery, fromISO, owner])

  const stageCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const contract of beforeStage)
      counts.set(contract.stageId, (counts.get(contract.stageId) ?? 0) + 1)
    return counts
  }, [beforeStage])

  const matched = useMemo(() => {
    const activeStage = dealPipelineId ? stage : ''
    const rows =
      activeStage === ''
        ? beforeStage
        : beforeStage.filter((contract) => contract.stageId === activeStage)
    if (!sort) return rows
    const sign = sort.dir === 'asc' ? 1 : -1
    const compare = compareBy(columns, sort.id)
    return [...rows].sort((a, b) => sign * compare(a, b))
  }, [beforeStage, columns, dealPipelineId, sort, stage])

  const pageCount = Math.max(1, Math.ceil(matched.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = useMemo(
    () => matched.slice((safePage - 1) * pageSize, safePage * pageSize),
    [matched, pageSize, safePage],
  )

  const onSort = useCallback((id: string) => {
    setSort((previous) => {
      if (previous?.id !== id) return { id, dir: 'asc' }
      if (previous.dir === 'asc') return { id, dir: 'desc' }
      return null
    })
  }, [])

  const clearFilters = useCallback(() => {
    setParams(new URLSearchParams(), { replace: true })
    setPage(1)
  }, [setParams])

  const stageOf = (contract: SalesDeal) =>
    pipelineStages.find((item) => item.id === contract.stageId) ?? {
      id: contract.stageId,
      name: contract.stageName,
      tone: contract.stageTone,
      outcome: contract.status,
      phase: contract.stagePhase,
    }
  const selectedContract = detail ?? contracts.find((contract) => contract.id === openId) ?? null
  const selectedStage = selectedContract ? stageOf(selectedContract) : undefined
  const isFiltered =
    query.trim() !== '' ||
    owner !== '' ||
    requestedPipelineId !== '' ||
    stage !== '' ||
    range !== DEFAULT_RANGE

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">계약 현황</h1>

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="고객사·제품·계약번호 검색"
          label="계약 검색"
          onChange={(next) => setParam('q', next)}
        />

        <FilterSelect
          label="파이프라인"
          value={dealPipelineId ?? ''}
          options={pipelineOptions}
          open={openFilter === 'pipeline'}
          onOpenChange={(open) => setOpenFilter(open ? 'pipeline' : null)}
          onChange={setPipeline}
        />

        {isManager && (
          <FilterSelect
            label="담당 영업"
            value={owner}
            options={ownerOptions}
            open={openFilter === 'owner'}
            onOpenChange={(open) => setOpenFilter(open ? 'owner' : null)}
            onChange={(value) => setParam('owner', value)}
          />
        )}

        <FilterSelect
          label="기간"
          value={range}
          options={RANGES}
          open={openFilter === 'range'}
          onOpenChange={(open) => setOpenFilter(open ? 'range' : null)}
          onChange={(value) => setParam('range', value, DEFAULT_RANGE)}
        />
      </div>

      {dealPipelineId && (
        <StageTabs
          stages={contractStages}
          label="계약 단계"
          value={stage}
          countOf={(id) => stageCounts.get(id) ?? 0}
          total={beforeStage.length}
          onChange={(next) => setParam('stage', next)}
        />
      )}

      {error ? (
        <div role="alert">
          <p>{error}</p>
          <Button variant="outline" onClick={reload}>
            다시 시도
          </Button>
        </div>
      ) : loading && contracts.length === 0 ? (
        <p role="status">계약 현황을 불러오는 중입니다.</p>
      ) : (
        <DataTable
          rows={pageRows}
          columns={columns}
          rowKey={(contract) => contract.id}
          handleColumn="org"
          sort={sort}
          onSort={onSort}
          onOpen={(contract) => setOpenId(contract.id)}
          caption="계약 목록. 헤더를 눌러 정렬할 수 있습니다."
          renderCell={(id, contract) => {
            if (id !== 'stage') return undefined
            const found = stageOf(contract)
            return <StageChip tone={found.tone}>{found.name}</StageChip>
          }}
          mini={(contract) => {
            const found = stageOf(contract)
            return {
              title: contract.org,
              badge: <StageChip tone={found.tone}>{found.name}</StageChip>,
              sub: contract.product + ' · ' + contract.kind,
              meta: [
                <span key="m1" className="tnum">
                  {won(contract.amount)}
                </span>,
                <span key="m2" className="tnum">
                  {contract.contractSignedOn
                    ? fmtDot(parseISO(contract.contractSignedOn))
                    : '계약일 미정'}
                </span>,
                ...(isManager ? [contract.owner] : []),
              ],
            }
          }}
          empty={
            isFiltered ? (
              <>
                <SearchIcon width={34} height={34} strokeWidth={1.5} />
                <p>조건에 맞는 계약이 없습니다.</p>
                <Button variant="outline" onClick={clearFilters}>
                  검색·필터 초기화
                </Button>
              </>
            ) : (
              <>
                <ContractIcon width={34} height={34} strokeWidth={1.5} />
                <p>현재 계약 단계인 영업 딜이 없습니다.</p>
              </>
            )
          }
        />
      )}

      {!error && loading && contracts.length > 0 && <p role="status">목록을 새로고침 중입니다.</p>}

      {!error && !loading && matched.length > 0 && (
        <Pagination
          page={safePage}
          pageCount={pageCount}
          pageSize={pageSize}
          total={matched.length}
          unit="건"
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size)
            setPage(1)
          }}
        />
      )}

      {openId && (
        <SalesDealDrawer
          deal={selectedContract}
          stage={selectedStage}
          loading={detailLoading}
          error={detailError}
          onRetry={reloadDetail}
          onClose={() => setOpenId(null)}
        />
      )}

      {createOpen && <ContractForm onClose={closeCreate} onSubmit={closeCreate} />}
    </section>
  )
}
