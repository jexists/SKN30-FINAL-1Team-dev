// 영업 현황 목록. 같은 딜을 보드(/visits/board)에서는 단계별 칸으로 봅니다.
//
// 조건은 주소에 둡니다(q·owner·range·stage). 목록을 걸러 둔 채로 링크를 건네면
// 받는 쪽도 같은 화면을 봅니다. 정렬과 페이지는 보는 사람 사정이라 주소에 남기지 않습니다.
import { useCallback, useDeferredValue, useMemo, useState } from 'react'

import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import ContractDrawer from '@/components/ContractDrawer'
import ContractForm from '@/components/ContractForm'
import DataTable, { compareBy, type SortState } from '@/components/DataTable'
import FilterSelect from '@/components/FilterSelect'
import { ContractIcon, PlusIcon, SearchIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import Pagination from '@/components/Pagination'
import StageChip from '@/components/StageChip'
import StageTabs from '@/components/StageTabs'
import { useOwnerScope } from '@/scope/scopeContext'
import { OWNERS } from '@/shared/contracts'
import { addDays, fmtDot, iso, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

import type { BoardContract } from './board'
import { dealColumns } from './columns'
import ViewToggle from './components/ViewToggle'
import useDealBoard from './useDealBoard'

import styles from '@/pages/listPage.module.scss'

/** 기간 선택지. 값이 개월 수이고 0 이면 전체입니다. 보드와 같은 어휘를 씁니다. */
const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

/** 기본 기간. 확정 건이 2년치라 전부 펼치면 목록이 지나치게 길어집니다. */
const DEFAULT_RANGE = '6'

export default function Visits() {
  const { columns, cards, findContract, addContract, updateContract, removeContract } =
    useDealBoard()
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
  const [openNo, setOpenNo] = useState<string | null>(null)
  const [editingNo, setEditingNo] = useState<string | null>(null)
  const [deletingNo, setDeletingNo] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [openFilter, setOpenFilter] = useState<'owner' | 'range' | null>(null)

  const tableColumns = useMemo(
    () => dealColumns(columns).filter((col) => col.id !== 'owner' || showOwner),
    [columns, showOwner],
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
    return cards.filter((card) => {
      if (!matchesOwner(card.owner)) return false
      if (owner !== '' && card.owner !== owner) return false
      if (fromISO !== null && card.date < fromISO) return false
      if (needle === '') return true
      return [card.no, card.org, card.product, card.owner, card.memo ?? '']
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })
  }, [cards, matchesOwner, owner, fromISO, deferredQuery])

  const stageCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const card of beforeStage) map.set(card.stageId, (map.get(card.stageId) ?? 0) + 1)
    return map
  }, [beforeStage])

  const matched = useMemo(() => {
    const rows = stage === '' ? beforeStage : beforeStage.filter((c) => c.stageId === stage)
    if (!sort) return rows
    const sign = sort.dir === 'asc' ? 1 : -1
    const compare = compareBy(tableColumns, sort.id)
    return [...rows].sort((a, b) => sign * compare(a, b))
  }, [beforeStage, stage, sort, tableColumns])

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

  // 객체가 아니라 계약번호를 들고 목록에서 찾습니다. 열어 둔 건을 지우면
  // 여기가 비면서 드로어가 알아서 닫힙니다.
  const openContract = openNo ? findContract(openNo) : undefined
  const editingContract = editingNo ? findContract(editingNo) : undefined
  const deletingContract = deletingNo ? findContract(deletingNo) : undefined

  const stageOf = (card: BoardContract) => columns.find((col) => col.id === card.stageId)
  // 단계 탭을 고른 채로 추가하면 그 단계로 들어갑니다.
  const addingStage = columns.find((col) => col.id === stage) ?? columns[0]

  const isFiltered = query.trim() !== '' || owner !== '' || stage !== '' || range !== DEFAULT_RANGE

  return (
    <section className={styles.page}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">영업 현황</h1>

      <div className={styles.toolbar}>
        <label className={styles.search}>
          <SearchIcon width={16} height={16} />
          <input
            value={query}
            placeholder="고객사·제품·계약번호 검색"
            aria-label="영업 건 검색"
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
          <ViewToggle view="list" />
          <Button onClick={() => setAdding(true)}>
            <PlusIcon width={15} height={15} />
            영업 건 추가
          </Button>
        </div>
      </div>

      <StageTabs
        stages={columns}
        label="영업 단계"
        value={stage}
        countOf={(id) => stageCounts.get(id) ?? 0}
        total={beforeStage.length}
        onChange={(next) => setParam('stage', next)}
      />

      <DataTable
        rows={pageRows}
        columns={tableColumns}
        rowKey={(card) => card.no}
        handleColumn="org"
        sort={sort}
        onSort={onSort}
        onOpen={(card) => setOpenNo(card.no)}
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
            sub: `${card.product} · ${card.kind}`,
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
              <p>조건에 맞는 영업 건이 없습니다.</p>
              <Button variant="outline" onClick={clearFilters}>
                검색·필터 초기화
              </Button>
            </>
          ) : (
            <>
              <ContractIcon width={34} height={34} strokeWidth={1.5} />
              <p>아직 등록한 영업 건이 없습니다.</p>
              <Button onClick={() => setAdding(true)}>영업 건 추가</Button>
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

      {openContract && (
        <ContractDrawer
          contract={openContract}
          stage={stageOf(openContract)}
          onClose={() => setOpenNo(null)}
          onEdit={() => {
            setEditingNo(openContract.no)
            setOpenNo(null)
          }}
          onDelete={() => {
            setDeletingNo(openContract.no)
            setOpenNo(null)
          }}
        />
      )}

      {adding && addingStage && (
        <ContractForm
          stageName={addingStage.name}
          onClose={() => setAdding(false)}
          onSubmit={(draft) => {
            addContract(draft, addingStage.id)
            setAdding(false)
          }}
        />
      )}

      {editingContract && (
        <ContractForm
          contract={editingContract}
          onClose={() => setEditingNo(null)}
          onSubmit={(draft) => {
            updateContract(editingContract.no, draft)
            setEditingNo(null)
          }}
        />
      )}

      {deletingContract && (
        <Modal
          title="영업 건을 삭제할까요?"
          description={`${deletingContract.no} · ${deletingContract.org}. 되돌릴 수 없습니다.`}
          onClose={() => setDeletingNo(null)}
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setDeletingNo(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  removeContract(deletingContract.no)
                  setDeletingNo(null)
                }}
              >
                삭제
              </Button>
            </>
          }
        >
          <p className={styles.confirm}>
            {deletingContract.product} · {deletingContract.owner}
          </p>
        </Modal>
      )}
    </section>
  )
}
