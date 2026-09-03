import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { errorMessage, transportMessage } from '@/api/errorMessage'
import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import Modal from '@/components/Modal'
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import { useScopeOwnerIds, useShowOwner } from '@/shared/scope'
import { showToast } from '@/shared/toast'
import type { Customer, CustomerContactResponse, PageResponse } from '@/types'

import type { BusinessCardDraft } from './businessCard'
import { COLUMN_BY_ID } from './columns'
import { toCustomer } from './contact'
import { exportCustomers, TooManyCustomersError } from './exportCustomers'
import useColumnPrefs from './useColumnPrefs'
import BusinessCardModal from './components/BusinessCardModal'
import CustomerDrawer from './components/CustomerDrawer'
import CustomerFormModal from './components/CustomerFormModal'
import CustomerTable from './components/CustomerTable'
import ImportModal from './components/ImportModal'
import SelectionBar from './components/SelectionBar'
import TableToolbar from './components/TableToolbar'

import styles from './Customers.module.scss'

export type SortState = { id: string; dir: 'asc' | 'desc' } | null

/** 한 번에 하나만 열립니다. 명함으로 읽은 값은 그대로 등록 폼으로 넘어갑니다. */
type OpenDialog = 'create' | 'import' | 'card' | null

function loadErrorMessage(error: unknown): string {
  const fallback = '고객 목록을 불러오지 못했습니다.'
  if (!isAxiosError(error)) return fallback
  if (error.response?.status === 401) return '로그인이 만료되었습니다. 다시 로그인해 주세요.'
  if (error.response?.status === 422) return '고객 검색 조건을 처리하지 못했습니다.'
  return transportMessage(error) ?? fallback
}

export default function Customers() {
  const [rows, setRows] = useState<Customer[]>([])
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [page, setPage] = useState(1)
  const [dialog, setDialog] = useState<OpenDialog>(null)
  const [cardDraft, setCardDraft] = useState<BusinessCardDraft | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [editing, setEditing] = useState<Customer | null>(null)
  const [deleting, setDeleting] = useState<Customer | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // 삭제는 팀장만 합니다. 메뉴에서 감추기만 하고 실제로 막는 일은 백엔드가 합니다.
  const { isManager } = useCurrentUser()

  const { prefs, toggleColumn, moveColumn, setWidth, reset } = useColumnPrefs()
  // 한 사람만 보고 있으면 담당자 칸이 줄마다 같은 이름이라 아예 감춥니다. 팀원은 늘 그렇습니다.
  // 저장된 설정은 건드리지 않습니다. 범위를 넓히면 그대로 돌아와야 합니다.
  const showOwner = useShowOwner()
  const hiddenColumns = useMemo(() => (showOwner ? [] : ['owner']), [showOwner])
  const deferredQuery = useDeferredValue(query)
  const ownerIds = useScopeOwnerIds()

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
          skip: (page - 1) * PAGE_SIZE,
          limit: PAGE_SIZE,
          owner_member_id: ownerIds,
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
  }, [deferredQuery, page, reloadKey, ownerIds])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const openCustomer = useMemo(() => rows.find((row) => row.id === openId) ?? null, [rows, openId])
  const resetPage = useCallback(() => setPage(1), [])

  // 팀 전체의 3페이지가 한 사람의 3페이지일 리 없으므로 범위가 바뀌면 첫 장으로 돌아갑니다.
  useEffect(() => {
    resetPage()
  }, [ownerIds, resetPage])

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

  const closeDialog = useCallback(() => {
    setDialog(null)
    setCardDraft(null)
  }, [])

  /** 목록을 처음부터 다시 받습니다. 방금 넣은 고객이 검색어에 걸리지 않을 수 있습니다. */
  const reload = useCallback(() => {
    closeDialog()
    setNotice(null)
    setQuery('')
    setPage(1)
    setReloadKey((value) => value + 1)
  }, [closeDialog])

  const onImported = useCallback(
    (added: number) => {
      reload()
      setNotice(`${added}명을 등록했습니다.`)
    },
    [reload],
  )

  // 명함에서 읽은 값은 바로 저장하지 않습니다. 사람이 등록 폼에서 확인하고 고칩니다.
  const onRecognized = useCallback((draft: BusinessCardDraft) => {
    setCardDraft(draft)
    setDialog('create')
  }, [])

  const onCustomerCreated = useCallback(
    (_contact: CustomerContactResponse, warning?: string) => {
      reload()
      if (warning) setNotice(warning)
    },
    [reload],
  )

  /**
   * 고친 줄만 갈아 끼웁니다. 목록을 다시 받으면 열려 있던 상세가 닫히는데
   * (아래 로딩 효과가 openId 를 비웁니다), 방금 고친 값은 그 자리에서 보여야 합니다.
   */
  const onCustomerUpdated = useCallback((contact: CustomerContactResponse) => {
    const updated = toCustomer(contact)
    setRows((previous) => previous.map((row) => (row.id === updated.id ? updated : row)))
    setEditing(null)
    showToast('고객 정보를 수정했습니다.')
  }, [])

  const closeDeleteModal = useCallback(() => {
    if (isDeleting) return
    setDeleting(null)
    setDeleteError(null)
  }, [isDeleting])

  const confirmDelete = useCallback(() => {
    if (deleting === null || isDeleting) return
    const target = deleting

    setIsDeleting(true)
    setDeleteError(null)

    void client
      .delete(`/customer-contacts/${target.id}`)
      .then(() => {
        setDeleting(null)
        setOpenId(null)
        // 눈앞에서 먼저 지우고, 쪽수와 합계는 다시 받아 맞춥니다.
        setRows((previous) => previous.filter((row) => row.id !== target.id))
        setTotal((previous) => Math.max(0, previous - 1))
        setReloadKey((value) => value + 1)
        showToast('고객을 삭제했습니다.')
      })
      .catch((error: unknown) => {
        setDeleteError(errorMessage(error, '고객을 삭제하지 못했습니다.'))
      })
      .finally(() => setIsDeleting(false))
  }, [deleting, isDeleting])

  // 내보내기는 화면 밖의 줄까지 모두 모읍니다. 페이지 한 장만 담으면 파일이 거짓말을 합니다.
  const exportRef = useRef<AbortController | null>(null)
  useEffect(() => () => exportRef.current?.abort(), [])

  const onExport = useCallback(() => {
    if (exporting) return
    const controller = new AbortController()
    exportRef.current = controller

    setExporting(true)
    setNotice(null)

    void exportCustomers({ query, ownerIds, columns, signal: controller.signal })
      .then((count) => {
        if (!controller.signal.aborted) setNotice(`${count}명을 파일로 내려받았습니다.`)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setNotice(
          error instanceof TooManyCustomersError
            ? `${error.message} 검색으로 범위를 좁힌 뒤 다시 받아 주세요.`
            : errorMessage(error, '고객 목록을 내보내지 못했습니다.'),
        )
      })
      .finally(() => {
        if (!controller.signal.aborted) setExporting(false)
      })
  }, [columns, exporting, ownerIds, query])

  // 첫 진입입니다. 툴바·탭·표가 차례로 나타나면 화면이 두세 번 들썩이므로
  // 화면 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && rows.length === 0 && !loadError) {
    return (
      <section aria-busy={loading}>
        <h1 className="sr-only">고객 목록</h1>
        <ListPageSkeleton label="고객 목록을 불러오는 중입니다." />
      </section>
    )
  }

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
        onCreate={() => setDialog('create')}
        onImport={() => setDialog('import')}
        onScanCard={() => setDialog('card')}
        onExport={onExport}
        exporting={exporting}
        canExport={total > 0}
      />

      {selected.size > 0 && <SelectionBar count={selected.size} onClear={clearSelection} />}

      {notice && (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      )}

      {!loadError && loading && rows.length > 0 && (
        <InlineLoader label="고객 목록을 새로고침하는 중입니다." />
      )}

      <ErrorToast message={loadError} onRetry={() => setReloadKey((value) => value + 1)} />

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
        onCreate={() => setDialog('create')}
      />

      {!loadError && total > 0 && (
        <Pagination page={page} pageCount={pageCount} total={total} onPage={setPage} />
      )}

      {dialog === 'create' && (
        <CustomerFormModal
          onClose={closeDialog}
          onCreated={onCustomerCreated}
          duplicateMatches={cardDraft?.matches}
          archiveImage={cardDraft?.sourceImage}
          initial={
            cardDraft
              ? {
                  name: cardDraft.name,
                  dept: cardDraft.dept,
                  title: cardDraft.title,
                  email: cardDraft.email,
                  phone: cardDraft.phone,
                }
              : undefined
          }
          initialCompany={
            cardDraft?.org.trim() ? { kind: 'new', name: cardDraft.org.trim() } : undefined
          }
        />
      )}

      {dialog === 'import' && <ImportModal onClose={closeDialog} onImported={onImported} />}

      {dialog === 'card' && (
        <BusinessCardModal
          onClose={closeDialog}
          onRecognized={onRecognized}
          onManual={() => setDialog('create')}
        />
      )}

      {openCustomer && (
        <CustomerDrawer
          customer={openCustomer}
          canDelete={isManager}
          onEdit={() => setEditing(openCustomer)}
          onDelete={() => {
            setDeleteError(null)
            setDeleting(openCustomer)
          }}
          onClose={() => setOpenId(null)}
        />
      )}

      {editing && (
        <CustomerFormModal
          customer={editing}
          onClose={() => setEditing(null)}
          onCreated={onCustomerCreated}
          onUpdated={onCustomerUpdated}
        />
      )}

      {deleting && (
        <Modal
          title="고객을 삭제하시겠습니까?"
          description={`${deleting.org} · ${deleting.name}`}
          onClose={closeDeleteModal}
          footer={
            <>
              <Button
                type="button"
                variant="outline"
                disabled={isDeleting}
                onClick={closeDeleteModal}
              >
                취소
              </Button>
              <Button type="button" disabled={isDeleting} onClick={confirmDelete}>
                {isDeleting ? '삭제 중…' : '삭제'}
              </Button>
            </>
          }
        >
          <p className={styles.confirm}>삭제한 고객 정보는 복구할 수 없습니다.</p>
          {deleteError && (
            <p className={styles.confirmError} role="alert">
              {deleteError}
            </p>
          )}
        </Modal>
      )}
    </section>
  )
}
