import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import Pagination from '@/components/Pagination'
import type {
  Customer,
  CustomerContactResponse,
  CustomerSource,
  CustomerSourceCode,
  CustomerStatus,
  CustomerStatusCode,
  PageResponse,
} from '@/types'

import { COLUMN_BY_ID } from './columns'
import useColumnPrefs from './useColumnPrefs'
import CustomerDrawer from './components/CustomerDrawer'
import CustomerFormModal from './components/CustomerFormModal'
import CustomerTable from './components/CustomerTable'
import SelectionBar from './components/SelectionBar'
import TableToolbar from './components/TableToolbar'

export type SortState = { id: string; dir: 'asc' | 'desc' } | null

const STATUS_LABEL: Record<CustomerStatusCode, CustomerStatus> = {
  new: '신규',
  proposal: '제안',
  negotiation: '협의',
  contracted: '계약',
  on_hold: '보류',
}

const SOURCE_LABEL: Record<CustomerSourceCode, CustomerSource> = {
  referral: '소개',
  exhibition: '박람회',
  website: '홈페이지',
  cold_call: '콜드콜',
  existing_customer: '기존 거래',
}

function toCustomer(contact: CustomerContactResponse): Customer {
  return {
    id: contact.id,
    name: contact.name,
    org: contact.company_name,
    dept: contact.department ?? '',
    title: contact.job_title ?? '',
    email: contact.email ?? '',
    phone: contact.phone,
    owner: contact.owner_display_name,
    source: contact.source_code === null ? '미지정' : SOURCE_LABEL[contact.source_code],
    status: contact.status_code === null ? '미지정' : STATUS_LABEL[contact.status_code],
    memo: contact.memo ?? '',
    last: null,
    next: null,
    created: contact.registered_at.slice(0, 10),
    overdue: false,
    companyId: contact.company_id,
    ownerMemberId: contact.owner_member_id,
    owners: contact.assignees.map((assignee) => ({
      id: assignee.id,
      name: assignee.display_name,
    })),
    regionCode: contact.company_region_code,
  }
}

function loadErrorMessage(error: unknown): string {
  if (!isAxiosError(error)) return '고객 목록을 불러오지 못했습니다.'
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 422) return '고객 검색 조건을 처리하지 못했습니다.'
  return '서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

export default function Customers() {
  const [rows, setRows] = useState<Customer[]>([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [createOpen, setCreateOpen] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const { prefs, toggleColumn, moveColumn, setWidth, reset } = useColumnPrefs()
  // 팀원에게는 자기가 담당인 고객만 보여, 담당자 칸이 늘 자기 이름입니다. 아예 감춥니다.
  // 저장된 설정은 건드리지 않습니다. 팀장으로 다시 들어오면 그대로 돌아와야 합니다.
  const { isManager } = useCurrentUser()
  const hiddenColumns = useMemo(() => (isManager ? [] : ['owner']), [isManager])
  const deferredQuery = useDeferredValue(query)

  // 정렬 API가 붙기 전에 현재 페이지만 정렬하면 전체 순서를 오해하게 됩니다.
  const columns = useMemo(
    () =>
      prefs.order
        .filter((id) => prefs.visible.includes(id))
        .filter((id) => !hiddenColumns.includes(id))
        .map((id) => COLUMN_BY_ID.get(id))
        .filter((column) => column !== undefined)
        .map((column) => ({ ...column, sortable: false })),
    [prefs.order, prefs.visible, hiddenColumns],
  )

  useEffect(() => {
    const controller = new AbortController()
    const needle = deferredQuery.trim()

    setLoading(true)
    setLoadError(null)

    void client
      .get<PageResponse<CustomerContactResponse>>('/customer-contacts', {
        params: {
          q: needle === '' ? undefined : needle.slice(0, 100),
          skip: (page - 1) * pageSize,
          limit: pageSize,
        },
        signal: controller.signal,
      })
      .then(({ data }) => {
        if (controller.signal.aborted) return
        setRows(data.items.map(toCustomer))
        setTotal(data.total)
        setSelected(new Set())
        setOpenId(null)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setLoadError(loadErrorMessage(error))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    return () => controller.abort()
  }, [deferredQuery, page, pageSize, reloadKey])

  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const openCustomer = useMemo(() => rows.find((row) => row.id === openId) ?? null, [rows, openId])
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

  const toggleRow = useCallback((id: string) => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }, [])

  const togglePage = useCallback(() => {
    setSelected((previous) => {
      const allOnPage = rows.length > 0 && rows.every((row) => previous.has(row.id))
      const next = new Set(previous)
      rows.forEach((row) => (allOnPage ? next.delete(row.id) : next.add(row.id)))
      return next
    })
  }, [rows])

  const clearSelection = useCallback(() => setSelected(new Set()), [])
  const ignoreSort = useCallback(() => undefined, [])

  const onCreated = useCallback(() => {
    setCreateOpen(false)
    setQuery('')
    setPage(1)
    setReloadKey((value) => value + 1)
  }, [])

  return (
    <section aria-busy={loading}>
      <h1 className="sr-only">고객 목록</h1>

      <TableToolbar
        query={query}
        onQueryChange={onQueryChange}
        prefs={prefs}
        onToggleColumn={toggleColumn}
        onMoveColumn={moveColumn}
        onResetColumns={reset}
        hiddenColumns={hiddenColumns}
        onCreate={() => setCreateOpen(true)}
      />

      {selected.size > 0 && <SelectionBar count={selected.size} onClear={clearSelection} />}

      {loadError ? (
        <div role="alert">
          <p>{loadError}</p>
          <Button variant="outline" onClick={() => setReloadKey((value) => value + 1)}>
            다시 시도
          </Button>
        </div>
      ) : loading && rows.length === 0 ? (
        <p role="status">고객 목록을 불러오는 중입니다.</p>
      ) : (
        <CustomerTable
          columns={columns}
          widths={prefs.widths}
          onResize={setWidth}
          rows={rows}
          sort={null}
          onSort={ignoreSort}
          selected={selected}
          onToggleRow={toggleRow}
          onTogglePage={togglePage}
          onOpen={setOpenId}
          isFiltered={query.trim() !== ''}
          hasAnyData={total > 0}
          onClearFilters={clearQuery}
          onCreate={() => setCreateOpen(true)}
        />
      )}

      {!loadError && total > 0 && (
        <Pagination
          page={page}
          pageCount={pageCount}
          pageSize={pageSize}
          total={total}
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size)
            resetPage()
          }}
        />
      )}

      {createOpen && (
        <CustomerFormModal onClose={() => setCreateOpen(false)} onCreated={onCreated} />
      )}

      {openCustomer && <CustomerDrawer customer={openCustomer} onClose={() => setOpenId(null)} />}
    </section>
  )
}
