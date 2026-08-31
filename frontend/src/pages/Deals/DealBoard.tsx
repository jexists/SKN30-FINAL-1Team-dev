// 영업 현황 보드. 컬럼은 서버의 영업 단계이고 카드 한 장이 영업 딜 하나입니다.
import {
  useCallback,
  useDeferredValue,
  useMemo,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import FilterSelect from '@/components/FilterSelect'
import { PlusIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import SearchInput from '@/components/SearchInput'
import { InlineLoader, SkeletonBlocks } from '@/components/Skeleton'
import usePointerDrag from '@/hooks/usePointerDrag'
import { useShowOwner } from '@/shared/scope'
import { addDays, iso, TODAY } from '@/utils/date'

import { DROP_ATTR, parseSlot, type BoardDeal } from './board'
import StageColumn from './components/StageColumn'
import ViewToggle from './components/ViewToggle'
import SalesDealDrawer from './SalesDealDrawer'
import SalesDealForm from './SalesDealForm'
import useSalesDeals, { type SalesDeal } from './useSalesDeals'

import styles from './DealBoard.module.scss'

/** 자리표시자 컬럼 하나의 폭·높이. StageColumn 과 .board 에 맞춥니다. */
const COLUMN_W = 288
const BOARD_H = 420

const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

const DEFAULT_RANGE = '6'
const ignoreStageEdit = () => undefined

interface CardDrag {
  id: string
  label: string
}

const pipelineIdentity = (deal: BoardDeal) => (deal as SalesDeal).id

export default function DealBoard() {
  const [openId, setOpenId] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const requestedPipelineId = params.get('pipeline') ?? ''
  // 카드마다 묻지 않고 보드가 한 번 정해 컬럼으로 내려 줍니다.
  const showOwner = useShowOwner()
  const {
    pipelines,
    dealPipelineId,
    activePipeline,
    columns,
    cards,
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
    moveSalesDeal,
  } = useSalesDeals(openId, requestedPipelineId || null, 'board')

  const query = params.get('q') ?? ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const deferredQuery = useDeferredValue(query)
  const readOnly = activePipeline?.status_code === 'archived'

  const [addingTo, setAddingTo] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [openFilter, setOpenFilter] = useState<'pipeline' | 'range' | null>(null)

  const pipelineOptions = useMemo(
    () =>
      pipelines.map((pipeline) => ({
        value: pipeline.id,
        label: pipeline.name + (pipeline.status_code === 'archived' ? ' (보관)' : ''),
      })),
    [pipelines],
  )

  const setParam = useCallback(
    (key: string, value: string, fallback = '') => {
      const next = new URLSearchParams(params)
      if (value === fallback) next.delete(key)
      else next.set(key, value)
      setParams(next, { replace: true })
    },
    [params, setParams],
  )

  const setPipeline = useCallback(
    (value: string) => {
      const next = new URLSearchParams(params)
      next.set('pipeline', value)
      next.delete('stage')
      setParams(next, { replace: true })
    },
    [params, setParams],
  )

  const fromISO = useMemo(() => {
    const months = Number(range)
    if (!months) return null
    return iso(addDays(TODAY, -Math.round(months * 30.4)))
  }, [range])

  const byColumn = useMemo(() => {
    const grouped = new Map<string, SalesDeal[]>()
    for (const column of columns) grouped.set(column.id, [])
    for (const card of cards) grouped.get(card.stageId)?.push(card)
    for (const stageCards of grouped.values()) stageCards.sort((a, b) => a.order - b.order)
    return grouped
  }, [cards, columns])

  const matches = useCallback(
    (card: SalesDeal) => {
      if (fromISO !== null && card.date < fromISO) return false
      const needle = deferredQuery.trim().toLowerCase()
      if (needle === '') return true
      return [card.no, card.org, card.product, card.owner, card.memo ?? '']
        .join(' ')
        .toLowerCase()
        .includes(needle)
    },
    [deferredQuery, fromISO],
  )

  const shownByColumn = useMemo(() => {
    const grouped = new Map<string, SalesDeal[]>()
    for (const column of columns)
      grouped.set(column.id, (byColumn.get(column.id) ?? []).filter(matches))
    return grouped
  }, [byColumn, columns, matches])

  const findById = useCallback((id: string) => cards.find((card) => card.id === id), [cards])

  const drop = useCallback(
    (dragged: CardDrag, key: string) => {
      if (readOnly) return
      const slot = parseSlot(key)
      const card = cards.find(({ id }) => id === dragged.id)
      if (!slot || !card || isPending(card.id)) return

      const shown = shownByColumn.get(slot.columnId) ?? []
      const all = byColumn.get(slot.columnId) ?? []
      const anchor = shown[slot.index]
      let position = anchor ? all.findIndex(({ id }) => id === anchor.id) : all.length
      if (position < 0) position = all.length

      const sourceIndex = (byColumn.get(card.stageId) ?? []).findIndex(({ id }) => id === card.id)
      if (card.stageId === slot.columnId && sourceIndex >= 0 && sourceIndex < position)
        position -= 1
      if (card.stageId === slot.columnId && position === sourceIndex) return

      void moveSalesDeal(card.id, card.stageId, slot.columnId, position).catch(() => undefined)
    },
    [byColumn, cards, isPending, moveSalesDeal, readOnly, shownByColumn],
  )

  const { dragging, dropKey, point, start } = usePointerDrag<CardDrag>(DROP_ATTR, drop)

  const grab = useCallback(
    (pointer: ReactPointerEvent, _deal: BoardDeal, id: string) => {
      if (readOnly) return
      const card = findById(id)
      if (!card || isPending(card.id)) return
      start(pointer, {
        id: card.id,
        label: card.org + ' · ' + card.product,
      })
    },
    [findById, isPending, readOnly, start],
  )

  const nudge = useCallback(
    (id: string, delta: -1 | 1) => {
      if (readOnly) return
      const card = findById(id)
      if (!card || isPending(card.id)) return
      const at = columns.findIndex((column) => column.id === card.stageId)
      const target = columns[at + delta]
      if (target) void moveSalesDeal(card.id, card.stageId, target.id, 0).catch(() => undefined)
    },
    [columns, findById, isPending, moveSalesDeal, readOnly],
  )

  const openById = useCallback(
    (id: string) => {
      const card = findById(id)
      if (card) setOpenId(card.id)
    },
    [findById],
  )

  const editById = useCallback(
    (id: string) => {
      const card = findById(id)
      if (!card) return
      clearMutationError()
      setEditingId(card.id)
    },
    [clearMutationError, findById],
  )

  const deleteById = useCallback(
    (id: string) => {
      const card = findById(id)
      if (!card) return
      clearMutationError()
      setDeletingId(card.id)
    },
    [clearMutationError, findById],
  )

  const openDeal = detail ?? cards.find(({ id }) => id === openId) ?? null
  const editingDeal = cards.find(({ id }) => id === editingId)
  const deletingDeal = cards.find(({ id }) => id === deletingId)
  const addingColumn = columns.find(({ id }) => id === addingTo)
  const firstColumn = columns[0]
  const openStage = openDeal ? columns.find((column) => column.id === openDeal.stageId) : undefined
  const isDeleting = deletingDeal ? isPending(deletingDeal.id) : false

  // 첫 진입입니다. 툴바와 컬럼이 따로 나타나면 화면이 두 번 들썩이므로 한 장을
  // 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (loading && columns.length === 0 && !error) {
    return (
      <section className={styles.page} aria-busy>
        <h1 className="sr-only">영업 현황 보드</h1>
        <SkeletonBlocks
          label="영업 현황을 불러오는 중입니다."
          count={3}
          height={36}
          width={168}
          gap={8}
          radius="var(--r-sm)"
          row
        />
        <SkeletonBlocks
          label="영업 단계를 불러오는 중입니다."
          count={4}
          height={BOARD_H}
          width={COLUMN_W}
          gap={12}
          row
        />
      </section>
    )
  }

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">영업 현황 보드</h1>

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
          <ViewToggle view="board" />
          <Button
            disabled={loading || !canCreate || !firstColumn || isCreating}
            onClick={() => firstColumn && setAddingTo(firstColumn.id)}
          >
            <PlusIcon width={15} height={15} />
            영업 딜 추가
          </Button>
        </div>
      </div>

      {readOnly && <p role="status">보관된 파이프라인은 읽기 전용입니다.</p>}

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

      <ErrorToast message={error} onRetry={reload} />

      {columns.length === 0 ? (
        <p role="status">아직 설정된 영업 단계가 없습니다.</p>
      ) : (
        <>
          {!loading && cards.length === 0 && <p role="status">아직 등록한 영업 딜이 없습니다.</p>}
          <div className={styles.board}>
            {columns.map((column) => (
              <StageColumn
                key={column.id}
                column={column}
                cards={shownByColumn.get(column.id) ?? []}
                identityOf={pipelineIdentity}
                editableStages={false}
                showOwner={showOwner}
                readOnly={readOnly}
                dropSlot={dropKey}
                draggingIdentity={dragging?.id ?? null}
                others={[]}
                onOpen={openById}
                onGrab={grab}
                onNudge={nudge}
                onEditCard={editById}
                onDeleteCard={deleteById}
                onAddCard={(id) => {
                  clearMutationError()
                  setAddingTo(id)
                }}
                onRename={ignoreStageEdit}
                onRecolor={ignoreStageEdit}
                onAddAfter={ignoreStageEdit}
                onRemove={ignoreStageEdit}
              />
            ))}
          </div>
        </>
      )}

      {!error && loading && columns.length > 0 && (
        <InlineLoader label="보드를 새로고침하는 중입니다." />
      )}

      {dragging && point && (
        <div className={styles.dragChip} style={{ left: point.x, top: point.y }} aria-hidden="true">
          {dragging.label}
        </div>
      )}

      {openId && (
        <SalesDealDrawer
          deal={openDeal}
          stage={openStage}
          loading={detailLoading}
          error={detailError}
          onRetry={reloadDetail}
          onClose={() => setOpenId(null)}
          onEdit={() => {
            if (!openDeal) return
            clearMutationError()
            setEditingId(openDeal.id)
            setOpenId(null)
          }}
          onDelete={() => {
            if (!openDeal) return
            clearMutationError()
            setDeletingId(openDeal.id)
            setOpenId(null)
          }}
        />
      )}

      {addingColumn && !readOnly && (
        <SalesDealForm
          columns={columns}
          stageId={addingColumn.id}
          dealTypes={dealTypes}
          optionsLoading={loading}
          onClose={() => setAddingTo(null)}
          onSubmit={async (input) => {
            await createSalesDeal(input)
            setAddingTo(null)
          }}
        />
      )}

      {editingDeal && !readOnly && (
        <SalesDealForm
          deal={editingDeal}
          columns={columns}
          stageId={editingDeal.stageId}
          dealTypes={dealTypes}
          optionsLoading={loading}
          onClose={() => setEditingId(null)}
          onSubmit={async (input) => {
            await updateSalesDeal(editingDeal.id, input)
            setEditingId(null)
          }}
        />
      )}

      {deletingDeal && !readOnly && (
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
