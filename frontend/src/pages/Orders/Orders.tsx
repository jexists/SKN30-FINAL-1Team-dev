// 발주 목록. 계약 현황 목록과 같은 형태입니다. 발주는 결재·생산·물류를 따라
// 한 방향으로만 흐르므로 옮겨 담을 보드를 두지 않고 목록 하나만 둡니다.
//
// 조건은 주소에 둡니다(q·supplier·range·status). 목록을 걸러 둔 채로 링크를 건네면
// 받는 쪽도 같은 화면을 봅니다. 정렬과 페이지는 보는 사람 사정이라 주소에 남기지 않습니다.
import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import Button from '@/components/Button'
import DataTable from '@/components/DataTable'
import ErrorToast from '@/components/ErrorToast'
import FilterSelect from '@/components/FilterSelect'
import { OrdersIcon, PlusIcon, SearchIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import OrderDrawer from '@/components/OrderDrawer'
import Pagination, { PAGE_SIZE } from '@/components/Pagination'
import SearchInput from '@/components/SearchInput'
import { InlineLoader, ListPageSkeleton } from '@/components/Skeleton'
import StageChip from '@/components/StageChip'
import StageTabs from '@/components/StageTabs'
import { orderNewPath, orderPath } from '@/constants/routes'
import { isLate, orderItemLabel, orderTotal } from '@/shared/orders'
import { useShowOwner } from '@/shared/scope'
import type { ApiPurchaseOrder } from '@/types'
import { addDays, fmtDotShort, iso, parseISO, TODAY } from '@/utils/date'
import { won } from '@/utils/format'

import { ORDER_COLUMNS } from './columns'
import OrderForm from './components/OrderForm'
import useOrderList from './useOrderList'

import styles from '@/pages/listPage.module.scss'

/** 기간 선택지. 값이 개월 수이고 0 이면 전체입니다. 계약 목록과 같은 어휘를 씁니다. */
const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

/** 기본 기간. 발주일 기준입니다. */
const DEFAULT_RANGE = '6'

export default function Orders() {
  const navigate = useNavigate()
  const showOwner = useShowOwner()

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const supplier = params.get('supplier') ?? ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const status = params.get('status') ?? ''

  // 타이핑 중에도 입력이 밀리지 않도록 목록 계산만 한 박자 늦춥니다.
  const deferredQuery = useDeferredValue(query)

  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [openFilter, setOpenFilter] = useState<'supplier' | 'range' | null>(null)

  // 한 사람만 보고 있으면 담당 영업 열은 모든 줄이 같은 값이라 자리만 차지합니다.
  //
  // 정렬 API가 붙기 전에 현재 쪽만 정렬하면 전체 순서를 오해하게 됩니다. 고객 목록과
  // 같은 처리로 헤더 정렬을 끕니다.
  const columns = useMemo(
    () =>
      ORDER_COLUMNS.filter((col) => col.id !== 'owner' || showOwner).map((col) => ({
        ...col,
        sortable: false,
      })),
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

  const orderQuery = useMemo(
    () => ({
      q: deferredQuery,
      supplier,
      fromISO,
      status,
      skip: (page - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    }),
    [deferredQuery, supplier, fromISO, status, page],
  )

  const {
    orders: pageRows,
    total,
    counts,
    statuses,
    suppliers,
    loading,
    error,
    reload,
    mutationError,
    clearMutationError,
    isPending,
    findOrderById,
    updateOrder,
    removeOrder,
  } = useOrderList(undefined, orderQuery)

  const supplierOptions = useMemo(
    () => [
      { value: '', label: '공급처 전체' },
      ...suppliers.map((name) => ({ value: name, label: name })),
    ],
    [suppliers],
  )

  const orderStages = useMemo(
    () => statuses.map(({ code, name, tone }) => ({ id: code, name, tone })),
    [statuses],
  )

  // 탭 옆 건수는 서버가 셉니다. 고른 상태는 빼고 센 값이라 탭을 바꿔도 다른 탭 숫자가
  // 0 으로 죽지 않습니다.
  const statusCounts = useMemo(() => new Map(Object.entries(counts)), [counts])

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  // 헤더 정렬을 끄므로 누를 일이 없습니다. 고객 목록과 같은 처리입니다.
  const ignoreSort = useCallback(() => undefined, [])

  const clearFilters = useCallback(() => {
    setParams(new URLSearchParams(), { replace: true })
    setPage(1)
  }, [setParams])

  // 객체가 아니라 발주번호를 들고 목록에서 찾습니다. 열어 둔 발주를 지우면
  // 여기가 비면서 드로어가 알아서 닫힙니다.
  const openOrder = openId ? findOrderById(openId) : undefined
  const editingOrder = editingId ? findOrderById(editingId) : undefined
  const deletingOrder = deletingId ? findOrderById(deletingId) : undefined
  const isDeleting = deletingOrder ? isPending(deletingOrder.id) : false

  const isFiltered =
    query.trim() !== '' || supplier !== '' || status !== '' || range !== DEFAULT_RANGE

  // 첫 진입입니다. 툴바·탭·표가 차례로 나타나면 화면이 두세 번 들썩이므로
  // 화면 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && pageRows.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy={loading}>
        {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
        <h1 className="sr-only">발주 관리</h1>
        <ListPageSkeleton label="발주 목록을 불러오는 중입니다." tabs />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">발주 관리</h1>

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="고객사·품목·발주번호 검색"
          label="발주 검색"
          onChange={(next) => setParam('q', next)}
        />

        <FilterSelect
          label="공급처"
          value={supplier}
          options={supplierOptions}
          open={openFilter === 'supplier'}
          onOpenChange={(open) => setOpenFilter(open ? 'supplier' : null)}
          onChange={(value) => setParam('supplier', value)}
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
          <Button disabled={loading} onClick={() => navigate(orderNewPath(status || undefined))}>
            <PlusIcon width={15} height={15} />
            발주 추가
          </Button>
        </div>
      </div>

      <StageTabs
        stages={orderStages}
        label="발주 상태"
        value={status}
        countOf={(id) => statusCounts.get(id) ?? 0}
        total={[...statusCounts.values()].reduce((sum, count) => sum + count, 0)}
        onChange={(next) => setParam('status', next)}
      />

      {mutationError && !deletingOrder && (
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

      {!error && loading && pageRows.length > 0 && (
        <InlineLoader label="목록을 새로고침하는 중입니다." />
      )}

      <ErrorToast message={error} onRetry={reload} />

      <DataTable
        rows={pageRows}
        columns={columns}
        rowKey={(order) => order.id}
        handleColumn="hospital"
        sort={null}
        onSort={ignoreSort}
        onOpen={(order) => setOpenId(order.id)}
        caption="발주 목록."
        renderCell={(id, order) => {
          if (id === 'status') return statusChip(order)
          if (id !== 'due' || !isLate(order)) return undefined
          return (
            <span className={styles.late}>
              {fmtDotShort(parseISO(order.due))}
              <i>{lateLabel(order)}</i>
            </span>
          )
        }}
        mini={(order) => ({
          title: order.hospital,
          badge: statusChip(order),
          sub: orderItemLabel(order),
          meta: [
            <span key="m1" className="tnum">
              {won(orderTotal(order))}
            </span>,
            <span key="m2" className="tnum">
              납기 {fmtDotShort(parseISO(order.due))}
            </span>,
            isLate(order) ? (
              <i key="m3" className={styles.lateOnly}>
                {lateLabel(order)}
              </i>
            ) : (
              order.supplier
            ),
          ],
        })}
        empty={
          isFiltered ? (
            <>
              <SearchIcon width={34} height={34} strokeWidth={1.5} />
              <p>조건에 맞는 발주가 없습니다.</p>
              <Button variant="outline" onClick={clearFilters}>
                검색·필터 초기화
              </Button>
            </>
          ) : (
            <>
              <OrdersIcon width={34} height={34} strokeWidth={1.5} />
              <p>아직 등록한 발주가 없습니다.</p>
              <Button onClick={() => navigate(orderNewPath())}>발주 추가</Button>
            </>
          )
        }
      />

      {pageRows.length > 0 && (
        <Pagination page={page} pageCount={pageCount} total={total} unit="건" onPage={setPage} />
      )}

      {openOrder && (
        <OrderDrawer
          order={openOrder}
          detailTo={orderPath(openOrder.no)}
          onClose={() => setOpenId(null)}
          onEdit={() => {
            setEditingId(openOrder.id)
            setOpenId(null)
          }}
          onDelete={() => {
            setDeletingId(openOrder.id)
            setOpenId(null)
          }}
        />
      )}

      {editingOrder && (
        <OrderForm
          order={editingOrder}
          statuses={statuses}
          suppliers={suppliers}
          optionsLoading={loading}
          onClose={() => setEditingId(null)}
          onSubmit={async (draft) => {
            await updateOrder(editingOrder.id, draft)
            setEditingId(null)
          }}
        />
      )}

      {deletingOrder && (
        <DeleteConfirm
          order={deletingOrder}
          pending={isDeleting}
          error={mutationError}
          onClose={() => setDeletingId(null)}
          onConfirm={async () => {
            await removeOrder(deletingOrder.id)
            setDeletingId(null)
          }}
        />
      )}
    </section>
  )
}

/** 납기를 며칠 넘겼는지. 표와 카드가 같은 문구를 씁니다. */
const lateLabel = (order: ApiPurchaseOrder) => `${order.expectOff - order.dueOff}일 지연`

/** 표와 카드가 같은 배지를 씁니다. */
function statusChip(order: ApiPurchaseOrder) {
  return <StageChip tone={order.stageTone}>{order.status}</StageChip>
}

interface DeleteConfirmProps {
  order: ApiPurchaseOrder
  pending: boolean
  error: string | null
  onClose: () => void
  onConfirm: () => Promise<void>
}

/** 지우기 전 한 번 묻습니다. 계약 목록과 같은 문구를 씁니다. */
function DeleteConfirm({ order, pending, error, onClose, onConfirm }: DeleteConfirmProps) {
  return (
    <Modal
      title="발주를 삭제할까요?"
      description={`${order.no} · ${order.hospital}. 되돌릴 수 없습니다.`}
      onClose={pending ? () => {} : onClose}
      footer={
        <>
          <Button type="button" variant="outline" disabled={pending} onClick={onClose}>
            취소
          </Button>
          <Button
            type="button"
            disabled={pending}
            onClick={() => void onConfirm().catch(() => undefined)}
          >
            {pending ? '삭제 중…' : '삭제'}
          </Button>
        </>
      }
    >
      <p className={styles.confirm}>
        {orderItemLabel(order)} · {order.supplier}
      </p>
      {error && <p role="alert">{error}</p>}
    </Modal>
  )
}
