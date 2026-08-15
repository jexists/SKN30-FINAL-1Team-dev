import { useCallback, useDeferredValue, useMemo, useState } from 'react'

import Pagination from '@/components/Pagination'
import { customers as seedCustomers } from '@/shared/customers'
import type { Customer } from '@/types'
import { useOwnerScope } from '@/scope/scopeContext'
import { downloadCsv, toCsv } from '@/utils/csv'

import { COLUMN_BY_ID } from './columns'
import useColumnPrefs from './useColumnPrefs'
import CustomerDrawer from './components/CustomerDrawer'
import CustomerFormModal from './components/CustomerFormModal'
import CustomerTable from './components/CustomerTable'
import ImportModal from './components/ImportModal'
import SelectionBar from './components/SelectionBar'
import TableToolbar from './components/TableToolbar'
import { TODAY_ISO } from '@/utils/date'

export type SortState = { id: string; dir: 'asc' | 'desc' } | null

export default function Customers() {
  const { matchesOwner } = useOwnerScope()
  const [rows, setRows] = useState<Customer[]>(seedCustomers)
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<SortState>(null)
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [modal, setModal] = useState<'create' | 'import' | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)

  const { prefs, toggleColumn, moveColumn, setWidth, reset } = useColumnPrefs()

  // 타이핑 중에도 입력이 밀리지 않도록 목록 계산만 한 박자 늦춥니다.
  const deferredQuery = useDeferredValue(query)

  const columns = useMemo(
    () =>
      prefs.order
        .filter((id) => prefs.visible.includes(id))
        .map((id) => COLUMN_BY_ID.get(id))
        .filter((c) => c !== undefined),
    [prefs.order, prefs.visible],
  )

  // 보기 범위 밖은 없는 셈 칩니다. 빈 화면 안내와 드로어의 '같은 회사 고객'까지
  // 같은 범위를 봐야 하므로 검색보다 먼저 한 번 걸러 둡니다.
  const scoped = useMemo(() => rows.filter((c) => matchesOwner(c.owner)), [rows, matchesOwner])

  // 검색 → 정렬. 이 순서를 한 곳에 모아 두어야 결과를 설명할 수 있습니다.
  const matched = useMemo(() => {
    const needle = deferredQuery.trim().toLowerCase()

    const filtered = scoped.filter((c) => {
      if (needle === '') return true
      // 검색은 숨긴 컬럼까지 포함합니다. 안 보인다고 못 찾으면 답답합니다.
      return [c.name, c.org, c.dept, c.title, c.email, c.phone, c.owner, c.memo]
        .join(' ')
        .toLowerCase()
        .includes(needle)
    })

    if (!sort) return filtered
    const column = COLUMN_BY_ID.get(sort.id)
    if (!column) return filtered

    const sign = sort.dir === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => sign * column.value(a).localeCompare(column.value(b), 'ko'))
  }, [scoped, deferredQuery, sort])

  // 결과가 줄어들어 현재 페이지가 사라졌으면 마지막 페이지로 당겨 옵니다.
  const pageCount = Math.max(1, Math.ceil(matched.length / pageSize))
  const safePage = Math.min(page, pageCount)
  const pageRows = useMemo(
    () => matched.slice((safePage - 1) * pageSize, safePage * pageSize),
    [matched, safePage, pageSize],
  )

  // 객체가 아니라 id 를 들고 목록에서 찾습니다. 열어 둔 고객을 지우면
  // 여기가 비면서 드로어가 알아서 닫힙니다.
  const openCustomer = useMemo(() => scoped.find((r) => r.id === openId) ?? null, [scoped, openId])

  const resetPage = useCallback(() => setPage(1), [])

  const onQueryChange = useCallback(
    (next: string) => {
      setQuery(next)
      resetPage()
    },
    [resetPage],
  )

  const clearQuery = useCallback(() => {
    setQuery('')
    resetPage()
  }, [resetPage])

  const onSort = useCallback((id: string) => {
    // 오름 → 내림 → 해제. 원래 순서로 되돌릴 방법이 있어야 합니다.
    setSort((prev) => {
      if (prev?.id !== id) return { id, dir: 'asc' }
      if (prev.dir === 'asc') return { id, dir: 'desc' }
      return null
    })
  }, [])

  const toggleRow = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }, [])

  const togglePage = useCallback(() => {
    setSelected((prev) => {
      const allOnPage = pageRows.every((r) => prev.has(r.id))
      const next = new Set(prev)
      pageRows.forEach((r) => (allOnPage ? next.delete(r.id) : next.add(r.id)))
      return next
    })
  }, [pageRows])

  const clearSelection = useCallback(() => setSelected(new Set()), [])

  const deleteSelected = useCallback(() => {
    setRows((prev) => prev.filter((r) => !selected.has(r.id)))
    setSelected(new Set())
  }, [selected])

  const addCustomers = useCallback(
    (added: Customer[]) => {
      // 방금 넣은 것이 보이지 않으면 저장됐는지 알 수 없어 맨 위에 붙이고 1페이지로 옵니다.
      setRows((prev) => [...added, ...prev])
      setSort(null)
      resetPage()
      setModal(null)
    },
    [resetPage],
  )

  const exportCsv = useCallback(() => {
    // 선택한 게 있으면 그것만, 없으면 지금 화면에 걸린 조건 전체를 내보냅니다.
    const target = selected.size > 0 ? matched.filter((r) => selected.has(r.id)) : matched
    const csv = toCsv(
      columns.map((c) => c.header),
      target.map((row) => columns.map((c) => c.value(row))),
    )
    downloadCsv(`고객목록_${TODAY_ISO}.csv`, csv)
  }, [selected, matched, columns])

  return (
    <section>
      {/* 제목은 Topbar 빵부스러기가 이미 말해 줍니다. 화면에는 도구만 둡니다. */}
      <h1 className="sr-only">고객 목록</h1>

      <TableToolbar
        query={query}
        onQueryChange={onQueryChange}
        prefs={prefs}
        onToggleColumn={toggleColumn}
        onMoveColumn={moveColumn}
        onResetColumns={reset}
        onExport={exportCsv}
        onImport={() => setModal('import')}
        onCreate={() => setModal('create')}
      />

      {selected.size > 0 && (
        <SelectionBar
          count={selected.size}
          onExport={exportCsv}
          onDelete={deleteSelected}
          onClear={clearSelection}
        />
      )}

      <CustomerTable
        columns={columns}
        widths={prefs.widths}
        onResize={setWidth}
        rows={pageRows}
        sort={sort}
        onSort={onSort}
        selected={selected}
        onToggleRow={toggleRow}
        onTogglePage={togglePage}
        onOpen={setOpenId}
        isFiltered={query.trim() !== ''}
        hasAnyData={scoped.length > 0}
        onClearFilters={clearQuery}
        onCreate={() => setModal('create')}
      />

      {matched.length > 0 && (
        <Pagination
          page={safePage}
          pageCount={pageCount}
          pageSize={pageSize}
          total={matched.length}
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size)
            resetPage()
          }}
        />
      )}

      {modal === 'create' && (
        <CustomerFormModal onClose={() => setModal(null)} onSubmit={(c) => addCustomers([c])} />
      )}
      {modal === 'import' && <ImportModal onClose={() => setModal(null)} onImport={addCustomers} />}

      {openCustomer && (
        <CustomerDrawer
          customer={openCustomer}
          all={scoped}
          onOpen={setOpenId}
          onClose={() => setOpenId(null)}
        />
      )}
    </section>
  )
}
