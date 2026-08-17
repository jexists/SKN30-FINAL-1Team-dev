// 영업 현황 보드. 컬럼은 서버의 영업 단계이고 카드 한 장이 실제 계약 하나입니다.
import {
  useCallback,
  useDeferredValue,
  useMemo,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import FilterSelect from '@/components/FilterSelect'
import { PlusIcon } from '@/components/icons'
import Modal from '@/components/Modal'
import SearchInput from '@/components/SearchInput'
import usePointerDrag from '@/hooks/usePointerDrag'
import { addDays, iso, TODAY } from '@/utils/date'

import { DROP_ATTR, parseSlot, type BoardContract } from './board'
import StageColumn from './components/StageColumn'
import ViewToggle from './components/ViewToggle'
import PipelineContractDrawer from './PipelineContractDrawer'
import PipelineContractForm from './PipelineContractForm'
import usePipelineContracts, { type PipelineContract } from './usePipelineContracts'

import styles from './BoardView.module.scss'

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

const pipelineIdentity = (contract: BoardContract) => (contract as PipelineContract).id

export default function BoardView() {
  const [openId, setOpenId] = useState<string | null>(null)
  const {
    columns,
    cards,
    companies,
    products,
    loading,
    error,
    reload,
    detail,
    detailLoading,
    detailError,
    reloadDetail,
    mutationError,
    clearMutationError,
    isCreating,
    isPending,
    createContract,
    updateContract,
    deleteContract,
    moveContract,
  } = usePipelineContracts(openId)

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const range = params.get('range') ?? DEFAULT_RANGE
  const deferredQuery = useDeferredValue(query)

  const [addingTo, setAddingTo] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [openFilter, setOpenFilter] = useState<'range' | null>(null)

  const setParam = useCallback(
    (key: string, value: string, fallback = '') => {
      const next = new URLSearchParams(params)
      if (value === fallback) next.delete(key)
      else next.set(key, value)
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
    const grouped = new Map<string, PipelineContract[]>()
    for (const column of columns) grouped.set(column.id, [])
    for (const card of cards) grouped.get(card.stageId)?.push(card)
    for (const stageCards of grouped.values()) stageCards.sort((a, b) => a.order - b.order)
    return grouped
  }, [cards, columns])

  const matches = useCallback(
    (card: PipelineContract) => {
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
    const grouped = new Map<string, PipelineContract[]>()
    for (const column of columns)
      grouped.set(column.id, (byColumn.get(column.id) ?? []).filter(matches))
    return grouped
  }, [byColumn, columns, matches])

  const findById = useCallback((id: string) => cards.find((card) => card.id === id), [cards])

  const drop = useCallback(
    (dragged: CardDrag, key: string) => {
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

      void moveContract(card.id, card.stageId, slot.columnId, position).catch(() => undefined)
    },
    [byColumn, cards, isPending, moveContract, shownByColumn],
  )

  const { dragging, dropKey, point, start } = usePointerDrag<CardDrag>(DROP_ATTR, drop)

  const grab = useCallback(
    (pointer: ReactPointerEvent, _contract: BoardContract, id: string) => {
      const card = findById(id)
      if (!card || isPending(card.id)) return
      start(pointer, {
        id: card.id,
        label: card.org + ' · ' + card.product,
      })
    },
    [findById, isPending, start],
  )

  const nudge = useCallback(
    (id: string, delta: -1 | 1) => {
      const card = findById(id)
      if (!card || isPending(card.id)) return
      const at = columns.findIndex((column) => column.id === card.stageId)
      const target = columns[at + delta]
      if (target) void moveContract(card.id, card.stageId, target.id, 0).catch(() => undefined)
    },
    [columns, findById, isPending, moveContract],
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

  const openContract = detail ?? cards.find(({ id }) => id === openId) ?? null
  const editingContract = cards.find(({ id }) => id === editingId)
  const deletingContract = cards.find(({ id }) => id === deletingId)
  const addingColumn = columns.find(({ id }) => id === addingTo)
  const firstColumn = columns[0]
  const openStage = openContract
    ? columns.find((column) => column.id === openContract.stageId)
    : undefined
  const isDeleting = deletingContract ? isPending(deletingContract.id) : false

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">영업 현황 보드</h1>

      <div className={styles.toolbar}>
        <SearchInput
          className={styles.search}
          value={query}
          placeholder="고객사·제품·계약번호 검색"
          label="영업 건 검색"
          onChange={(next) => setParam('q', next)}
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
            disabled={loading || !firstColumn || isCreating}
            onClick={() => firstColumn && setAddingTo(firstColumn.id)}
          >
            <PlusIcon width={15} height={15} />
            영업 건 추가
          </Button>
        </div>
      </div>

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

      {error ? (
        <div role="alert">
          <p>{error}</p>
          <Button variant="outline" onClick={reload}>
            다시 시도
          </Button>
        </div>
      ) : loading && columns.length === 0 ? (
        <p role="status">영업 현황을 불러오는 중입니다.</p>
      ) : columns.length === 0 ? (
        <p role="status">아직 설정된 영업 단계가 없습니다.</p>
      ) : (
        <>
          {!loading && cards.length === 0 && <p role="status">아직 등록한 영업 건이 없습니다.</p>}
          <div className={styles.board}>
            {columns.map((column) => (
              <StageColumn
                key={column.id}
                column={column}
                cards={shownByColumn.get(column.id) ?? []}
                identityOf={pipelineIdentity}
                editableStages={false}
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

      {!error && loading && columns.length > 0 && <p role="status">보드를 새로고침 중입니다.</p>}

      {dragging && point && (
        <div className={styles.dragChip} style={{ left: point.x, top: point.y }} aria-hidden="true">
          {dragging.label}
        </div>
      )}

      {openId && (
        <PipelineContractDrawer
          contract={openContract}
          stage={openStage}
          loading={detailLoading}
          error={detailError}
          onRetry={reloadDetail}
          onClose={() => setOpenId(null)}
          onEdit={() => {
            if (!openContract) return
            clearMutationError()
            setEditingId(openContract.id)
            setOpenId(null)
          }}
          onDelete={() => {
            if (!openContract) return
            clearMutationError()
            setDeletingId(openContract.id)
            setOpenId(null)
          }}
        />
      )}

      {addingColumn && (
        <PipelineContractForm
          stageName={addingColumn.name}
          companies={companies}
          products={products}
          optionsLoading={loading}
          onClose={() => setAddingTo(null)}
          onSubmit={async (input) => {
            await createContract(input, addingColumn.id)
            setAddingTo(null)
          }}
        />
      )}

      {editingContract && (
        <PipelineContractForm
          contract={editingContract}
          companies={companies}
          products={products}
          optionsLoading={loading}
          onClose={() => setEditingId(null)}
          onSubmit={async (input) => {
            await updateContract(editingContract.id, input)
            setEditingId(null)
          }}
        />
      )}

      {deletingContract && (
        <Modal
          title="영업 건을 삭제할까요?"
          description={deletingContract.no + ' · ' + deletingContract.org + '. 되돌릴 수 없습니다.'}
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
                  void deleteContract(deletingContract.id)
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
            {deletingContract.product} · {deletingContract.owner}
          </p>
          {mutationError && <p role="alert">{mutationError}</p>}
        </Modal>
      )}
    </section>
  )
}
