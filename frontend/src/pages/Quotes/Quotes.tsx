import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import DataTable, { compareBy, type SortState } from '@/components/DataTable'
import ErrorToast from '@/components/ErrorToast'
import FilterSelect from '@/components/FilterSelect'
import { QuoteIcon, SearchIcon } from '@/components/icons'
import Pagination from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import StageChip from '@/components/StageChip'
import StageTabs from '@/components/StageTabs'
import SalesDealDrawer from '@/pages/Deals/SalesDealDrawer'
import useSalesDeals, { type SalesDeal } from '@/pages/Deals/useSalesDeals'
import { addDays, fmtDot, fmtDotShort, iso, parseISO, TODAY, TODAY_ISO } from '@/utils/date'
import { won } from '@/utils/format'

import { QUOTE_COLUMNS } from './columns'
import QuoteForm from './components/QuoteForm'

import styles from '@/pages/listPage.module.scss'

const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

const DEFAULT_RANGE = '6'

export default function Quotes() {
  const [openId, setOpenId] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()

  // 일정 등록에서 '견적서 작성 화면으로 이동' 을 고르면 이 표를 달고 옵니다.
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
    cards: quotes,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
  } = useSalesDeals(openId, requestedPipelineId || null, 'list', 'quote')
  const { isManager } = useCurrentUser()

  const query = params.get('q') ?? ''
  const owner = isManager ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const stage = params.get('stage') ?? ''
  const deferredQuery = useDeferredValue(query)

  const [sort, setSort] = useState<SortState>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(30)
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

  const quoteStages = useMemo(
    () => pipelineStages.filter((item) => item.phase === 'quote'),
    [pipelineStages],
  )
  const columns = useMemo(
    () => QUOTE_COLUMNS.filter((column) => column.id !== 'owner' || isManager),
    [isManager],
  )
  const ownerOptions = useMemo(
    () => [
      { value: '', label: '담당 전체' },
      ...[...new Set(quotes.map((item) => item.owner))]
        .sort()
        .map((name) => ({ value: name, label: name })),
    ],
    [quotes],
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
    return quotes.filter((quote) => {
      if (owner !== '' && quote.owner !== owner) return false
      if (fromISO !== null && (quote.quoteIssuedOn ?? quote.date) < fromISO) return false
      if (needle === '') return true
      return [quote.quoteNo ?? quote.no, quote.org, quote.product, quote.owner, quote.memo ?? '']
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [deferredQuery, fromISO, owner, quotes])

  const stageCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const quote of beforeStage) counts.set(quote.stageId, (counts.get(quote.stageId) ?? 0) + 1)
    return counts
  }, [beforeStage])

  const matched = useMemo(() => {
    const activeStage = dealPipelineId ? stage : ''
    const rows =
      activeStage === ''
        ? beforeStage
        : beforeStage.filter((quote) => quote.stageId === activeStage)
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

  const stageOf = (quote: SalesDeal) =>
    pipelineStages.find((item) => item.id === quote.stageId) ?? {
      id: quote.stageId,
      name: quote.stageName,
      tone: quote.stageTone,
      outcome: quote.status,
      phase: quote.stagePhase,
    }
  const selectedQuote = detail ?? quotes.find((quote) => quote.id === openId) ?? null
  const selectedStage = selectedQuote ? stageOf(selectedQuote) : undefined
  const isFiltered =
    query.trim() !== '' ||
    owner !== '' ||
    requestedPipelineId !== '' ||
    stage !== '' ||
    range !== DEFAULT_RANGE

  // 첫 진입입니다. 툴바·탭·표가 차례로 나타나면 화면이 두세 번 들썩이므로
  // 화면 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && quotes.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy={loading}>
        <h1 className="sr-only">견적 현황</h1>
        <ListPageSkeleton label="견적 현황을 불러오는 중입니다." tabs />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">견적 현황</h1>

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="고객사·제품·견적번호 검색"
          label="견적 검색"
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
          stages={quoteStages}
          label="견적 단계"
          value={stage}
          countOf={(id) => stageCounts.get(id) ?? 0}
          total={beforeStage.length}
          onChange={(next) => setParam('stage', next)}
        />
      )}

      {!error && loading && quotes.length > 0 && (
        <InlineLoader label="목록을 새로고침하는 중입니다." />
      )}

      <ErrorToast message={error} onRetry={reload} />

      <DataTable
        rows={pageRows}
        columns={columns}
        rowKey={(quote) => quote.id}
        handleColumn="org"
        sort={sort}
        onSort={onSort}
        onOpen={(quote) => setOpenId(quote.id)}
        caption="견적 목록. 헤더를 눌러 정렬할 수 있습니다."
        renderCell={(id, quote) => {
          if (id === 'stage') {
            const found = stageOf(quote)
            return <StageChip tone={found.tone}>{found.name}</StageChip>
          }
          if (id !== 'validUntil' || !quote.quoteValidUntil || quote.quoteValidUntil >= TODAY_ISO)
            return undefined
          return (
            <span className={styles.late}>
              {fmtDotShort(parseISO(quote.quoteValidUntil))}
              <i>만료</i>
            </span>
          )
        }}
        mini={(quote) => {
          const found = stageOf(quote)
          const expired = !!quote.quoteValidUntil && quote.quoteValidUntil < TODAY_ISO
          return {
            title: quote.org,
            badge: <StageChip tone={found.tone}>{found.name}</StageChip>,
            sub: quote.product + ' · ' + quote.kind,
            meta: [
              <span key="m1" className="tnum">
                {won(quote.amount)}
              </span>,
              <span key="m2" className="tnum">
                {quote.quoteIssuedOn ? fmtDot(parseISO(quote.quoteIssuedOn)) : '견적일 미정'}
              </span>,
              expired ? (
                <i key="m3" className={styles.lateOnly}>
                  만료
                </i>
              ) : quote.quoteValidUntil ? (
                <span key="m4" className="tnum">
                  ~{fmtDotShort(parseISO(quote.quoteValidUntil))}
                </span>
              ) : (
                <span key="m5">유효기한 미정</span>
              ),
            ],
          }
        }}
        empty={
          isFiltered ? (
            <>
              <SearchIcon width={34} height={34} strokeWidth={1.5} />
              <p>조건에 맞는 견적이 없습니다.</p>
              <Button variant="outline" onClick={clearFilters}>
                검색·필터 초기화
              </Button>
            </>
          ) : (
            <>
              <QuoteIcon width={34} height={34} strokeWidth={1.5} />
              <p>현재 견적 단계인 영업 딜이 없습니다.</p>
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
          deal={selectedQuote}
          stage={selectedStage}
          loading={detailLoading}
          error={detailError}
          onRetry={reloadDetail}
          onClose={() => setOpenId(null)}
        />
      )}

      {createOpen && <QuoteForm onClose={closeCreate} onSubmit={closeCreate} />}
    </section>
  )
}
