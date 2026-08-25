// 영업 현황 목록. 영업 딜과 파이프라인 단계를 API에서 읽고 실제 UUID로 쓰기를 처리합니다.
import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import DataTable, { compareBy, type SortState } from '@/components/DataTable'
import ErrorToast from '@/components/ErrorToast'
import FilterSelect from '@/components/FilterSelect'
import { VisitIcon, PlusIcon, SearchIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import Pagination from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import StageChip from '@/components/StageChip'
import StageTabs from '@/components/StageTabs'
import { addDays, fmtDot, iso, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

import { dealColumns } from './columns'
import ViewToggle from './components/ViewToggle'
import SalesDealDrawer from './SalesDealDrawer'
import SalesDealForm from './SalesDealForm'
import useSalesDeals, { type SalesDeal } from './useSalesDeals'

import styles from '@/pages/listPage.module.scss'

const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

const DEFAULT_RANGE = '6'

export default function Deals() {
  const [openId, setOpenId] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const requestedPipelineId = params.get('pipeline') ?? ''
  const {
    pipelines,
    dealPipelineId,
    columns,
    cards,
    companies,
    products,
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
    canCreate,
    isCreating,
    isPending,
    createSalesDeal,
    updateSalesDeal,
    deleteSalesDeal,
  } = useSalesDeals(openId, requestedPipelineId || null, 'list')
  const { isManager } = useCurrentUser()
  // 팀원은 서버가 본인 데이터로 제한하므로 담당자 스코프를 요청에 싣지 않습니다.
  const showOwner = isManager

  const query = params.get('q') ?? ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const stage = params.get('stage') ?? ''
  const deferredQuery = useDeferredValue(query)

  const [sort, setSort] = useState<SortState>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(30)
  const [openFilter, setOpenFilter] = useState<'pipeline' | 'range' | null>(null)
  const [addingTo, setAddingTo] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const tableColumns = useMemo(
    () => dealColumns(columns).filter((column) => column.id !== 'owner' || showOwner),
    [columns, showOwner],
  )

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

  const fromISO = useMemo(() => {
    const months = Number(range)
    if (!months) return null
    return iso(addDays(TODAY, -Math.round(months * 30.4)))
  }, [range])

  const beforeStage = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    return cards.filter((card) => {
      if (fromISO !== null && card.date < fromISO) return false
      if (needle === '') return true
      return [card.no, card.org, card.product, card.owner, card.memo ?? '']
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [cards, deferredQuery, fromISO])

  const stageCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const card of beforeStage) counts.set(card.stageId, (counts.get(card.stageId) ?? 0) + 1)
    return counts
  }, [beforeStage])

  const matched = useMemo(() => {
    const activeStage = dealPipelineId ? stage : ''
    const rows =
      activeStage === '' ? beforeStage : beforeStage.filter((card) => card.stageId === activeStage)
    if (!sort) return rows
    const sign = sort.dir === 'asc' ? 1 : -1
    const compare = compareBy(tableColumns, sort.id)
    return [...rows].sort((a, b) => sign * compare(a, b))
  }, [beforeStage, dealPipelineId, sort, stage, tableColumns])

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

  const stageOf = (card: SalesDeal) =>
    columns.find((column) => column.id === card.stageId) ?? {
      id: card.stageId,
      name: card.stageName,
      tone: card.stageTone,
      outcome: card.status,
    }
  const selectedDeal = detail ?? cards.find((card) => card.id === openId) ?? null
  const selectedStage = selectedDeal ? stageOf(selectedDeal) : undefined
  const editingDeal = cards.find((card) => card.id === editingId)
  const deletingDeal = cards.find((card) => card.id === deletingId)
  const addingColumn = columns.find((column) => column.id === addingTo)
  const defaultColumn = columns.find((column) => column.id === stage) ?? columns[0]
  const isDeleting = deletingDeal ? isPending(deletingDeal.id) : false
  const isFiltered =
    query.trim() !== '' || requestedPipelineId !== '' || stage !== '' || range !== DEFAULT_RANGE

  // 첫 진입입니다. 툴바·탭·표가 차례로 나타나면 화면이 두세 번 들썩이므로
  // 화면 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && cards.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy={loading}>
        <h1 className="sr-only">영업 현황</h1>
        <ListPageSkeleton label="영업 현황을 불러오는 중입니다." tabs />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">영업 현황</h1>

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="고객사·제품·영업번호 검색"
          label="영업 딜 검색"
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

        <FilterSelect
          label="기간"
          value={range}
          options={RANGES}
          open={openFilter === 'range'}
          onOpenChange={(open) => setOpenFilter(open ? 'range' : null)}
          onChange={(value) => setParam('range', value, DEFAULT_RANGE)}
        />

        <div className={styles.actions}>
          <ViewToggle view="list" />
          <Button
            disabled={loading || !canCreate || !defaultColumn || isCreating}
            onClick={() => {
              if (!defaultColumn) return
              clearMutationError()
              setAddingTo(defaultColumn.id)
            }}
          >
            <PlusIcon width={15} height={15} />
            영업 딜 추가
          </Button>
        </div>
      </div>

      {dealPipelineId && (
        <StageTabs
          stages={columns}
          label="영업 단계"
          value={stage}
          countOf={(id) => stageCounts.get(id) ?? 0}
          total={beforeStage.length}
          onChange={(next) => setParam('stage', next)}
        />
      )}

      {mutationError && (
        <div role="alert">
          <p>{mutationError}</p>
          <Button
            variant="outline"
            onClick={() => {
              clearMutationError()
              reload()
            }}
          >
            목록 새로고침
          </Button>
        </div>
      )}

      {!error && loading && cards.length > 0 && (
        <InlineLoader label="목록을 새로고침하는 중입니다." />
      )}

      <ErrorToast message={error} onRetry={reload} />

      <DataTable
        rows={pageRows}
        columns={tableColumns}
        rowKey={(card) => card.id}
        handleColumn="org"
        sort={sort}
        onSort={onSort}
        onOpen={(card) => setOpenId(card.id)}
        caption="영업 현황 목록. 헤더를 눌러 정렬할 수 있습니다."
        renderCell={(id, card) => {
          if (id !== 'stage') return undefined
          const found = stageOf(card)
          return found ? <StageChip tone={found.tone}>{found.name}</StageChip> : null
        }}
        mini={(card) => {
          const found = stageOf(card)
          return {
            title: card.org,
            badge: found ? <StageChip tone={found.tone}>{found.name}</StageChip> : undefined,
            sub: card.product + ' · ' + card.kind,
            meta: [
              <span key="m1" className="tnum">
                {won(card.amount)}
              </span>,
              <span key="m2" className="tnum">
                {fmtDot(parseISO(card.date))}
              </span>,
              ...(showOwner ? [card.owner] : []),
            ],
          }
        }}
        empty={
          isFiltered ? (
            <>
              <SearchIcon width={34} height={34} strokeWidth={1.5} />
              <p>조건에 맞는 영업 딜이 없습니다.</p>
              <Button variant="outline" onClick={clearFilters}>
                검색·필터 초기화
              </Button>
            </>
          ) : (
            <>
              <VisitIcon width={34} height={34} strokeWidth={1.5} />
              <p>아직 등록한 영업 딜이 없습니다.</p>
            </>
          )
        }
      />

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
          deal={selectedDeal}
          stage={selectedStage}
          loading={detailLoading}
          error={detailError}
          onRetry={reloadDetail}
          onClose={() => setOpenId(null)}
          onEdit={() => {
            if (!selectedDeal) return
            clearMutationError()
            setEditingId(selectedDeal.id)
            setOpenId(null)
          }}
          onDelete={() => {
            if (!selectedDeal) return
            clearMutationError()
            setDeletingId(selectedDeal.id)
            setOpenId(null)
          }}
        />
      )}

      {addingColumn && (
        <SalesDealForm
          stageName={addingColumn.name}
          companies={companies}
          products={products}
          dealTypes={dealTypes}
          optionsLoading={loading}
          onClose={() => setAddingTo(null)}
          onSubmit={async (input) => {
            await createSalesDeal(input, addingColumn.id)
            setAddingTo(null)
          }}
        />
      )}

      {editingDeal && (
        <SalesDealForm
          deal={editingDeal}
          companies={companies}
          products={products}
          dealTypes={dealTypes}
          optionsLoading={loading}
          onClose={() => setEditingId(null)}
          onSubmit={async (input) => {
            await updateSalesDeal(editingDeal.id, input)
            setEditingId(null)
          }}
        />
      )}

      {deletingDeal && (
        <Modal
          title="영업 딜을 삭제할까요?"
          description={deletingDeal.no + ' · ' + deletingDeal.org + '. 되돌릴 수 없습니다.'}
          onClose={() => {
            if (!isDeleting) setDeletingId(null)
          }}
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                disabled={isDeleting}
                onClick={() => setDeletingId(null)}
              >
                취소
              </Button>
              <Button
                type="button"
                disabled={isDeleting}
                onClick={() => {
                  void deleteSalesDeal(deletingDeal.id)
                    .then(() => setDeletingId(null))
                    .catch(() => undefined)
                }}
              >
                {isDeleting ? '삭제 중…' : '삭제'}
              </Button>
            </>
          }
        >
          <p className={styles.confirm}>
            {deletingDeal.product} · {deletingDeal.owner}
          </p>
          {mutationError && <p role="alert">{mutationError}</p>}
        </Modal>
      )}
    </section>
  )
}
