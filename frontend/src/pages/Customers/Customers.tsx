import { useCallback, useEffect, useMemo, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { errorMessage, transportMessage } from '@/api/errorMessage'
import { useCurrentUser } from '@/auth/sessionContext'
import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import Modal from '@/components/Modal'
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import { ListPageSkeleton, TableSkeleton } from '@/components/Skeleton'
import { useScopeOwnerIds, useShowOwner } from '@/shared/scope'
import { showToast } from '@/shared/toast'
import type {
  Customer,
  CustomerContactBulkResult,
  CustomerContactResponse,
  PageResponse,
} from '@/types'

import type { BusinessCardDraft } from './businessCard'
import type { BusinessLicenseDraft } from './businessLicense'
import { COLUMN_BY_ID } from './columns'
import { toCustomer } from './contact'
import { exportCustomers } from './exportCustomers'
import useColumnPrefs from './useColumnPrefs'
import BusinessCardModal from './components/BusinessCardModal'
import BusinessLicenseModal from './components/BusinessLicenseModal'
import CustomerDrawer from './components/CustomerDrawer'
import CustomerFormModal from './components/CustomerFormModal'
import CustomerTable from './components/CustomerTable'
import ImportModal from './components/ImportModal'
import TableToolbar from './components/TableToolbar'

import styles from './Customers.module.scss'

export type SortState = { id: string; dir: 'asc' | 'desc' } | null

/**
 * 한 번에 하나만 열립니다. 명함·사업자등록증에서 읽은 값은 그대로 등록 폼으로 넘어갑니다.
 * TableToolbar 의 등록 메뉴가 돌려주는 말과 같은 값입니다.
 */
type OpenDialog = 'create' | 'import' | 'card' | 'license' | null

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
  const [licenseDraft, setLicenseDraft] = useState<BusinessLicenseDraft | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [confirmingExport, setConfirmingExport] = useState(false)
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
    const needle = query.trim()

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
  }, [query, page, reloadKey, ownerIds])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const openCustomer = useMemo(() => rows.find((row) => row.id === openId) ?? null, [rows, openId])
  const resetPage = useCallback(() => setPage(1), [])

  // 팀 전체의 3페이지가 한 사람의 3페이지일 리 없으므로 범위가 바뀌면 첫 장으로 돌아갑니다.
  useEffect(() => {
    resetPage()
  }, [ownerIds, resetPage])

  const onSearch = useCallback(
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

  const ignoreSort = useCallback(() => undefined, [])

  const closeDialog = useCallback(() => {
    setDialog(null)
    setCardDraft(null)
    setLicenseDraft(null)
  }, [])

  /** 목록을 처음부터 다시 받습니다. 방금 넣은 고객이 검색어에 걸리지 않을 수 있습니다. */
  const reload = useCallback(() => {
    closeDialog()
    setNotice(null)
    setQuery('')
    setPage(1)
    setReloadKey((value) => value + 1)
  }, [closeDialog])

  /*
   * 엑셀은 줄마다 결과가 갈립니다. 등록한 수만 말하면 나머지가 어디로 갔는지 모릅니다.
   * 어느 줄이 왜 빠졌는지는 모달이 계속 보여 줘야 하므로 여기서 닫지 않고 목록만
   * 다시 받습니다. 방금 넣은 고객이 검색어에 걸리지 않을 수 있어 첫 장으로 돌아갑니다.
   */
  const onImported = useCallback((result: CustomerContactBulkResult) => {
    setQuery('')
    setPage(1)
    setReloadKey((value) => value + 1)
    const skipped = [
      result.duplicate > 0 ? `중복 ${result.duplicate}건` : null,
      result.invalid > 0 ? `입력 오류 ${result.invalid}건` : null,
      result.failed > 0 ? `실패 ${result.failed}건` : null,
    ].filter((label): label is string => label !== null)
    setNotice(
      `총 ${result.total}건 중 ${result.success}명을 등록했습니다.` +
        (skipped.length > 0 ? ` ${skipped.join(' · ')}은 등록하지 않았습니다.` : ''),
    )
  }, [])

  // 명함에서 읽은 값은 바로 저장하지 않습니다. 사람이 등록 폼에서 확인하고 고칩니다.
  const onRecognized = useCallback((draft: BusinessCardDraft) => {
    setCardDraft(draft)
    setDialog('create')
  }, [])

  // 사업자등록증에서 읽은 값도 바로 저장하지 않습니다. 이름 칸에는 대표자를 넣지만
  // 실제 담당자는 다른 사람일 수 있어, 사람이 등록 폼에서 확인하고 고칩니다.
  const onLicenseDrafted = useCallback((draft: BusinessLicenseDraft) => {
    setLicenseDraft(draft)
    // 못 읽은 칸은 사람이 채워야 합니다. 빈 폼만 열어 두면 무엇이 빠졌는지 모릅니다.
    const unread = [
      draft.company.trim() === '' ? '회사명' : null,
      draft.address.trim() === '' ? '주소' : null,
      draft.businessNo.trim() === '' ? '사업자등록번호' : null,
      draft.representative.trim() === '' ? '대표자명' : null,
    ].filter((label): label is string => label !== null)
    setNotice(
      unread.length > 0
        ? `사업자등록증에서 ${unread.join('·')}을(를) 읽지 못했습니다. 직접 채워 주세요.`
        : null,
    )
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

  // 고른 줄만 내보냅니다. 페이지를 넘기면 선택이 풀리므로 지금 보이는 줄이 전부입니다.
  const picked = useMemo(() => rows.filter((row) => selected.has(row.id)), [rows, selected])

  const onExport = useCallback(() => {
    if (picked.length === 0) {
      showToast('내보낼 고객을 먼저 선택하세요.')
      return
    }
    setConfirmingExport(true)
  }, [picked])

  const confirmExport = useCallback(() => {
    const count = exportCustomers({ customers: picked, columns })
    setConfirmingExport(false)
    showToast(`${count}명을 내보냈습니다.`)
  }, [columns, picked])

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
        onSearch={onSearch}
        prefs={prefs}
        onToggleColumn={toggleColumn}
        onMoveColumn={moveColumn}
        onResetColumns={reset}
        hiddenColumns={hiddenColumns}
        onAdd={setDialog}
        onExport={onExport}
        canExport={total > 0}
      />

      {notice && (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      )}

      <ErrorToast message={loadError} onRetry={() => setReloadKey((value) => value + 1)} />

      {!loadError && loading ? (
        <TableSkeleton label="고객 목록을 새로고침하는 중입니다." rows={rows.length} />
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
          onCreate={() => setDialog('create')}
        />
      )}

      {!loadError && total > 0 && (
        <Pagination page={page} pageCount={pageCount} total={total} onPage={setPage} />
      )}

      {dialog === 'create' && (
        <CustomerFormModal
          onClose={closeDialog}
          onCreated={onCustomerCreated}
          duplicateMatches={cardDraft?.matches}
          archiveImage={cardDraft?.sourceImage}
          // 등록증에 있는 사람은 대표자뿐입니다. 이름만 채우고 나머지 사람 칸은
          // 명함일 때만 채웁니다. 대표자가 담당자가 아니면 폼에서 고칩니다.
          initial={
            cardDraft
              ? {
                  name: cardDraft.name,
                  dept: cardDraft.dept,
                  title: cardDraft.title,
                  email: cardDraft.email,
                  phone: cardDraft.phone,
                }
              : licenseDraft?.representative.trim()
                ? { name: licenseDraft.representative.trim() }
                : undefined
          }
          initialCompany={
            cardDraft?.org.trim()
              ? { kind: 'new', name: cardDraft.org.trim() }
              : licenseDraft?.company.trim()
                ? { kind: 'new', name: licenseDraft.company.trim() }
                : undefined
          }
          initialBusinessNo={licenseDraft?.businessNo}
          // 등록증의 소재지는 한 줄로 옵니다. 우편번호가 필요하면 주소 검색으로 다시 고릅니다.
          initialAddress={
            licenseDraft?.address.trim()
              ? { postcode: '', address: licenseDraft.address.trim(), addressDetail: '' }
              : undefined
          }
        />
      )}

      {dialog === 'import' && <ImportModal onClose={closeDialog} onImported={onImported} />}

      {dialog === 'license' && (
        <BusinessLicenseModal onClose={closeDialog} onDrafted={onLicenseDrafted} />
      )}

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

      {confirmingExport && (
        <Modal
          title="고객 데이터 다운로드"
          onClose={() => setConfirmingExport(false)}
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setConfirmingExport(false)}>
                취소
              </Button>
              <Button type="button" onClick={confirmExport}>
                내보내기
              </Button>
            </>
          }
        >
          <p className={styles.confirm}>
            체크된 {picked.length}개의 고객 정보를 파일로 내려받습니다.
          </p>
        </Modal>
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
