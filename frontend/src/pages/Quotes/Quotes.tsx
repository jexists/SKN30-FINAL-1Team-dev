// 견적 목록. 계약 현황 목록과 같은 형태입니다. 견적은 한 방향으로만 흐르므로
// 옮겨 담을 보드를 두지 않고 목록 하나만 둡니다.
//
// 조건은 주소에 둡니다(q·owner·range·stage). 목록을 걸러 둔 채로 링크를 건네면
// 받는 쪽도 같은 화면을 봅니다. 정렬과 페이지는 보는 사람 사정이라 주소에 남기지 않습니다.
import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import DataTable, { compareBy, type SortState } from '@/components/DataTable'
import FilterSelect from '@/components/FilterSelect'
import { PlusIcon, QuoteIcon, SearchIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import Pagination from '@/components/Pagination'
import StageChip from '@/components/StageChip'
import StageTabs from '@/components/StageTabs'
import { useOwnerScope } from '@/scope/scopeContext'
import { OWNERS } from '@/shared/contracts'
import { isExpired } from '@/shared/quotes'
import type { Quote, QuoteStageId } from '@/types'
import { addDays, fmtDot, fmtDotShort, iso, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

import { QUOTE_COLUMNS } from './columns'
import QuoteForm from './components/QuoteForm'
import { QUOTE_STAGES, stageById } from './stages'
import useQuoteList from './useQuoteList'

import styles from '@/pages/listPage.module.scss'

/** 기간 선택지. 값이 개월 수이고 0 이면 전체입니다. 계약 목록과 같은 어휘를 씁니다. */
const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

/** 기본 기간. 견적일 기준입니다. */
const DEFAULT_RANGE = '6'

export default function Quotes() {
  const { quotes, findQuote, addQuote, updateQuote, removeQuote } = useQuoteList()
  // 팀 전체를 볼 때만 담당 영업으로 한 번 더 좁힙니다. 범위가 이미 한 사람이면
  // 같은 뜻의 조건이 둘이 되어 서로 어긋날 수 있습니다.
  const { matchesOwner, showOwner, owners } = useOwnerScope()

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const owner = showOwner ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const stage = params.get('stage') ?? ''

  const ownerOptions = useMemo(
    () => [
      { value: '', label: '담당 전체' },
      ...OWNERS.filter((name) => owners.includes(name)).map((name) => ({
        value: name,
        label: name,
      })),
    ],
    [owners],
  )

  // 타이핑 중에도 입력이 밀리지 않도록 목록 계산만 한 박자 늦춥니다.
  const deferredQuery = useDeferredValue(query)

  const [sort, setSort] = useState<SortState>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [adding, setAdding] = useState(false)
  const [editingNo, setEditingNo] = useState<string | null>(null)
  const [deletingNo, setDeletingNo] = useState<string | null>(null)
  const [openFilter, setOpenFilter] = useState<'owner' | 'range' | null>(null)

  // 한 사람만 보고 있으면 담당 영업 열은 모든 줄이 같은 값이라 자리만 차지합니다.
  const columns = useMemo(
    () => QUOTE_COLUMNS.filter((col) => col.id !== 'owner' || showOwner),
    [showOwner],
  )

  // 기본값은 쿼리에서 지웁니다. 주소를 복사했을 때 조건이 그대로 살아나되 짧게 남습니다.
  // 조건이 바뀌면 첫 페이지로 돌아옵니다. 3페이지에 있다가 결과가 줄면 빈 화면을 봅니다.
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

  // 단계를 뺀 나머지 조건까지만 거른 목록입니다. 탭의 건수를 여기서 셉니다.
  const beforeStage = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()
    return quotes.filter((quote) => {
      if (!matchesOwner(quote.owner)) return false
      if (owner !== '' && quote.owner !== owner) return false
      if (fromISO !== null && quote.date < fromISO) return false
      if (needle === '') return true
      return [quote.no, quote.org, quote.product, quote.owner]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [quotes, matchesOwner, owner, fromISO, deferredQuery])

  const stageCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const q of beforeStage) map.set(q.stageId, (map.get(q.stageId) ?? 0) + 1)
    return map
  }, [beforeStage])

  const matched = useMemo(() => {
    const rows = stage === '' ? beforeStage : beforeStage.filter((q) => q.stageId === stage)
    if (!sort) return rows
    const sign = sort.dir === 'asc' ? 1 : -1
    const compare = compareBy(columns, sort.id)
    return [...rows].sort((a, b) => sign * compare(a, b))
  }, [beforeStage, stage, sort, columns])

  // 결과가 줄어들어 현재 페이지가 사라졌으면 마지막 페이지로 당겨 옵니다.
  const pageCount = Math.max(1, Math.ceil(matched.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = useMemo(
    () => matched.slice((safePage - 1) * pageSize, safePage * pageSize),
    [matched, safePage, pageSize],
  )

  const onSort = useCallback((id: string) => {
    // 오름 → 내림 → 해제. 원래 순서로 되돌릴 방법이 있어야 합니다.
    setSort((prev) => {
      if (prev?.id !== id) return { id, dir: 'asc' }
      if (prev.dir === 'asc') return { id, dir: 'desc' }
      return null
    })
  }, [])

  const clearFilters = useCallback(() => {
    setParams(new URLSearchParams(), { replace: true })
    setPage(1)
  }, [setParams])

  // 객체가 아니라 견적번호를 들고 목록에서 찾습니다. 열어 둔 견적을 지우면
  // 여기가 비면서 모달이 알아서 닫힙니다.
  const editingQuote = editingNo ? findQuote(editingNo) : undefined
  const deletingQuote = deletingNo ? findQuote(deletingNo) : undefined

  const isFiltered = query.trim() !== '' || owner !== '' || stage !== '' || range !== DEFAULT_RANGE

  return (
    <section className={styles.page}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">견적 현황</h1>

      <div className={styles.toolbar}>
        <label className={styles.search}>
          <SearchIcon width={16} height={16} />
          <input
            value={query}
            placeholder="고객사·제품·견적번호 검색"
            aria-label="견적 검색"
            onChange={(event) => setParam('q', event.target.value)}
          />
        </label>

        {showOwner && (
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
          <Button onClick={() => setAdding(true)}>
            <PlusIcon width={15} height={15} />
            견적 추가
          </Button>
        </div>
      </div>

      <StageTabs
        stages={QUOTE_STAGES}
        label="견적 단계"
        value={stage}
        countOf={(id) => stageCounts.get(id) ?? 0}
        total={beforeStage.length}
        onChange={(next) => setParam('stage', next)}
      />

      <DataTable
        rows={pageRows}
        columns={columns}
        rowKey={(q) => q.no}
        handleColumn="org"
        sort={sort}
        onSort={onSort}
        onOpen={(q) => setEditingNo(q.no)}
        caption="견적 목록. 헤더를 눌러 정렬할 수 있습니다."
        renderCell={(id, quote) => {
          if (id === 'stage') return stageChip(quote)
          // 기한이 지난 견적은 다시 써야 합니다. 훑어볼 때 바로 보여야 합니다.
          if (id !== 'validUntil' || !isExpired(quote)) return undefined
          return (
            <span className={styles.late}>
              {fmtDotShort(parseISO(quote.validUntil))}
              <i>만료</i>
            </span>
          )
        }}
        mini={(quote) => ({
          title: quote.org,
          badge: stageChip(quote),
          sub: `${quote.product} · ${quote.kind}`,
          meta: [
            <span key="m1" className="tnum">
              {won(quote.amount)}
            </span>,
            <span key="m2" className="tnum">
              {fmtDot(parseISO(quote.date))}
            </span>,
            isExpired(quote) ? (
              <i key="m3" className={styles.lateOnly}>
                만료
              </i>
            ) : (
              <span key="m4" className="tnum">
                ~{fmtDotShort(parseISO(quote.validUntil))}
              </span>
            ),
          ],
        })}
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
              <p>아직 등록한 견적이 없습니다.</p>
              <Button onClick={() => setAdding(true)}>견적 추가</Button>
            </>
          )
        }
      />

      {matched.length > 0 && (
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

      {adding && (
        // 단계 탭을 고른 채로 추가하면 그 단계로 들어갑니다.
        <QuoteForm
          stageId={(stage || undefined) as QuoteStageId | undefined}
          onClose={() => setAdding(false)}
          onSubmit={(draft) => {
            addQuote(draft)
            setAdding(false)
          }}
        />
      )}

      {editingQuote && (
        <QuoteForm
          quote={editingQuote}
          onClose={() => setEditingNo(null)}
          onDelete={() => {
            setDeletingNo(editingQuote.no)
            setEditingNo(null)
          }}
          onSubmit={(draft) => {
            updateQuote(editingQuote.no, draft)
            setEditingNo(null)
          }}
        />
      )}

      {deletingQuote && (
        <Modal
          title="견적을 삭제할까요?"
          description={`${deletingQuote.no} · ${deletingQuote.org}. 되돌릴 수 없습니다.`}
          onClose={() => setDeletingNo(null)}
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setDeletingNo(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  removeQuote(deletingQuote.no)
                  setDeletingNo(null)
                }}
              >
                삭제
              </Button>
            </>
          }
        >
          <p className={styles.confirm}>
            {deletingQuote.product} · {deletingQuote.owner}
          </p>
        </Modal>
      )}
    </section>
  )
}

/** 표와 카드가 같은 배지를 씁니다. */
function stageChip(quote: Quote) {
  const stage = stageById(quote.stageId)
  return stage ? <StageChip tone={stage.tone}>{stage.name}</StageChip> : null
}
