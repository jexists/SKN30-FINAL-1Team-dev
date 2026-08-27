import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import useTeamMembers from '@/hooks/useTeamMembers'
import Button from '@/components/Button'
import DataTable from '@/components/DataTable'
import ErrorToast from '@/components/ErrorToast'
import FilterSelect from '@/components/FilterSelect'
import { PlusIcon, QuoteIcon, SearchIcon } from '@/components/icons'
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import { chipOr } from '@/components/StageChip'
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
  // 드로어에서 연 견적 수정. 목록의 '견적 작성'(createOpen)과 달리 딜이 정해져 있습니다.
  const [editingQuote, setEditingQuote] = useState<SalesDeal | null>(null)
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
  const { isManager } = useCurrentUser()
  // 담당자 선택지. 받아 둔 목록에서 뽑으면 지금 쪽에 있는 사람만 나옵니다.
  const { members: teamMembers } = useTeamMembers(isManager)

  const query = params.get('q') ?? ''
  const owner = isManager ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const stage = params.get('stage') ?? ''
  const deferredQuery = useDeferredValue(query)

  const [page, setPage] = useState(1)
  const [openFilter, setOpenFilter] = useState<'pipeline' | 'owner' | 'range' | null>(null)

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

  const dealQuery = useMemo(
    () => ({
      q: deferredQuery,
      stageId: stage,
      ownerMemberId: owner,
      fromISO,
      skip: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    }),
    [deferredQuery, stage, owner, fromISO, page],
  )

  const {
    pipelines,
    dealPipelineId,
    columns: pipelineStages,
    cards: pageRows,
    total,
    counts,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
    documentStatuses,
    saveDealDocument,
  } = useSalesDeals(openId, requestedPipelineId || null, 'list', 'quote', dealQuery)
  // 정렬 API가 붙기 전에 현재 쪽만 정렬하면 전체 순서를 오해하게 됩니다.
  const columns = useMemo(
    () =>
      QUOTE_COLUMNS.filter((column) => column.id !== 'owner' || isManager).map((column) => ({
        ...column,
        sortable: false,
      })),
    [isManager],
  )
  const ownerOptions = useMemo(
    () => [
      { value: '', label: '담당 전체' },
      ...teamMembers.map((item) => ({ value: item.id, label: item.display_name })),
    ],
    [teamMembers],
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

  // 단계 탭 옆 건수는 서버가 셉니다. 고른 단계는 빼고 센 값이라 탭을 바꿔도 다른 단계
  // 숫자가 0 으로 죽지 않습니다.
  const stageCounts = useMemo(() => new Map(Object.entries(counts)), [counts])
  const stageTotal = useMemo(
    () => [...stageCounts.values()].reduce((sum, count) => sum + count, 0),
    [stageCounts],
  )

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // 헤더 정렬을 끄므로 누를 일이 없습니다. 고객 목록과 같은 처리입니다.
  const ignoreSort = useCallback(() => undefined, [])

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
  const selectedQuote = detail ?? pageRows.find((quote) => quote.id === openId) ?? null
  const selectedStage = selectedQuote ? stageOf(selectedQuote) : undefined
  const isFiltered =
    query.trim() !== '' ||
    owner !== '' ||
    requestedPipelineId !== '' ||
    stage !== '' ||
    range !== DEFAULT_RANGE

  // 첫 진입입니다. 툴바·탭·표가 차례로 나타나면 화면이 두세 번 들썩이므로
  // 화면 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && pageRows.length === 0 && !error) {
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

        <div className={styles.actions}>
          <Button disabled={loading} onClick={() => setParam('new', '1')}>
            <PlusIcon width={15} height={15} />
            견적 작성
          </Button>
        </div>
      </div>

      {/* 견적 상태는 파이프라인과 무관한 팀 설정이라 파이프라인을 고르지 않아도 뜹니다. */}
      {documentStatuses.length > 0 && (
        <StageTabs
          stages={documentStatuses}
          label="견적 상태"
          value={stage}
          countOf={(id) => stageCounts.get(id) ?? 0}
          total={stageTotal}
          onChange={(next) => setParam('stage', next)}
        />
      )}

      {!error && loading && pageRows.length > 0 && (
        <InlineLoader label="목록을 새로고침하는 중입니다." />
      )}

      <ErrorToast message={error} onRetry={reload} />

      <DataTable
        rows={pageRows}
        columns={columns}
        rowKey={(quote) => quote.id}
        handleColumn="org"
        sort={null}
        onSort={ignoreSort}
        onOpen={(quote) => setOpenId(quote.id)}
        caption="견적 목록. 헤더를 눌러 정렬할 수 있습니다."
        renderCell={(id, quote) => {
          if (id === 'stage') return chipOr(quote.quoteStatusTone, quote.quoteStatusName)
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
          const expired = !!quote.quoteValidUntil && quote.quoteValidUntil < TODAY_ISO
          return {
            title: quote.org,
            badge: chipOr(quote.quoteStatusTone, quote.quoteStatusName),
            sub: quote.title,
            meta: [
              <span key="m1" className="tnum">
                {quote.quoteAmount === null ? '견적금액 미정' : won(quote.quoteAmount)}
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
              <p>아직 견적을 작성한 영업 딜이 없습니다.</p>
              <Button onClick={() => setParam('new', '1')}>견적 작성</Button>
            </>
          )
        }
      />

      {!error && !loading && pageRows.length > 0 && (
        <Pagination page={page} pageCount={pageCount} total={total} unit="건" onPage={setPage} />
      )}

      {openId && (
        <SalesDealDrawer
          deal={selectedQuote}
          stage={selectedStage}
          loading={detailLoading}
          error={detailError}
          onRetry={reloadDetail}
          onClose={() => setOpenId(null)}
          onEditQuote={() => {
            if (!selectedQuote) return
            setEditingQuote(selectedQuote)
            setOpenId(null)
          }}
        />
      )}

      {editingQuote && (
        <QuoteForm
          deal={editingQuote}
          statuses={documentStatuses}
          onClose={() => setEditingQuote(null)}
          onSubmit={async (dealId, fields) => {
            await saveDealDocument(dealId, fields, '견적을 저장')
            setEditingQuote(null)
          }}
        />
      )}

      {createOpen && (
        <QuoteForm
          statuses={documentStatuses}
          onClose={closeCreate}
          onSubmit={async (dealId, fields) => {
            await saveDealDocument(dealId, fields, '견적을 저장')
            closeCreate()
            reload()
          }}
        />
      )}
    </section>
  )
}
