// 영업 현황 보드. 컬럼은 영업 단계이고 카드 한 장이 영업 건 하나입니다.
//
// 카드를 끄는 동안 목록을 실제로 바꾸지 않습니다. 놓을 자리를 선으로만 알리고,
// 손을 뗄 때 한 번만 옮깁니다. 끌면서 목록이 계속 재배치되면 어디에 놓이는지
// 오히려 알기 어렵습니다.
import {
  useCallback,
  useDeferredValue,
  useMemo,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useSearchParams } from 'react-router'

import Button from '@/components/Button'
import ContractDrawer from '@/components/ContractDrawer'
import ContractForm from '@/components/ContractForm'
import FilterSelect from '@/components/FilterSelect'
import Modal from '@/components/Modal'
import { PlusIcon, SearchIcon } from '@/components/icons'
import usePointerDrag from '@/hooks/usePointerDrag'
import { useOwnerScope } from '@/scope/scopeContext'
import { OWNERS } from '@/shared/contracts'
import { addDays, iso, TODAY } from '@/utils/date'

import { DROP_ATTR, parseSlot, TONES, type BoardContract } from './board'
import StageColumn from './components/StageColumn'
import ViewToggle from './components/ViewToggle'
import useDealBoard from './useDealBoard'

import styles from './BoardView.module.scss'

/** 기간 선택지. 값이 개월 수이고 0 이면 전체입니다. */
const RANGES = [
  { value: '3', label: '최근 3개월' },
  { value: '6', label: '최근 6개월' },
  { value: '12', label: '최근 1년' },
  { value: '0', label: '전체' },
]

/** 기본 기간. 확정 건이 2년치라 전부 펼치면 확정 컬럼만 길어집니다. */
const DEFAULT_RANGE = '6'

/** 손끝에 붙어 다니는 조각이 알아야 하는 것 */
interface CardDrag {
  no: string
  label: string
}

export default function BoardView() {
  const {
    columns,
    byColumn,
    findContract,
    moveCard,
    addContract,
    updateContract,
    removeContract,
    renameColumn,
    recolorColumn,
    addColumn,
    removeColumn,
  } = useDealBoard()

  // 팀 전체를 볼 때만 담당 영업으로 한 번 더 좁힙니다. 목록 화면과 같은 규칙입니다.
  const { matchesOwner, showOwner, owners } = useOwnerScope()

  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const owner = showOwner ? (params.get('owner') ?? '') : ''
  const range = params.get('range') ?? DEFAULT_RANGE

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

  const [openNo, setOpenNo] = useState<string | null>(null)
  const [addingTo, setAddingTo] = useState<string | null>(null)
  const [editingNo, setEditingNo] = useState<string | null>(null)
  const [deletingNo, setDeletingNo] = useState<string | null>(null)
  const [openFilter, setOpenFilter] = useState<'owner' | 'range' | null>(null)
  // 새 컬럼을 어느 컬럼 오른쪽에 넣을지. null 이면 입력칸이 닫힌 상태이고,
  // 빈 문자열이면 보드 맨 끝입니다.
  const [newColumnAfter, setNewColumnAfter] = useState<string | null>(null)
  const [newColumnName, setNewColumnName] = useState('')

  // 기본값은 쿼리에서 지웁니다. 주소를 복사했을 때 조건이 그대로 살아나되 짧게 남습니다.
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

  const matches = useCallback(
    (card: BoardContract) => {
      if (!matchesOwner(card.owner)) return false
      if (owner !== '' && card.owner !== owner) return false
      if (fromISO !== null && card.date < fromISO) return false
      const needle = deferredQuery.trim().toLowerCase()
      if (needle === '') return true
      return [card.no, card.org, card.product, card.owner, card.memo ?? '']
        .join(' ')
        .toLowerCase()
        .includes(needle)
    },
    [matchesOwner, owner, fromISO, deferredQuery],
  )

  const shownByColumn = useMemo(() => {
    const map = new Map<string, BoardContract[]>()
    for (const column of columns)
      map.set(column.id, (byColumn.get(column.id) ?? []).filter(matches))
    return map
  }, [columns, byColumn, matches])

  const shownCount = useMemo(
    () => [...shownByColumn.values()].reduce((sum, list) => sum + list.length, 0),
    [shownByColumn],
  )

  /**
   * 놓은 자리는 화면에 보이는 목록 기준입니다. 필터가 걸려 있으면 그 자리가
   * 전체 목록에서는 다른 번호라, 그 자리에 있던 카드 앞으로 넣습니다.
   */
  const drop = useCallback(
    (dragged: CardDrag, key: string) => {
      const slot = parseSlot(key)
      if (!slot) return

      const shown = shownByColumn.get(slot.columnId) ?? []
      const all = byColumn.get(slot.columnId) ?? []
      const anchor = shown[slot.index]
      const index = anchor ? all.findIndex((c) => c.no === anchor.no) : all.length

      moveCard(dragged.no, slot.columnId, index < 0 ? all.length : index)
    },
    [shownByColumn, byColumn, moveCard],
  )

  const { dragging, dropKey, point, start } = usePointerDrag<CardDrag>(DROP_ATTR, drop)

  const grab = useCallback(
    (pointer: ReactPointerEvent, contract: BoardContract) =>
      start(pointer, { no: contract.no, label: `${contract.org} · ${contract.product}` }),
    [start],
  )

  /** 키보드로 앞뒤 컬럼에 옮깁니다. 옮긴 카드는 그 컬럼 맨 위로 갑니다. */
  const nudge = useCallback(
    (no: string, delta: -1 | 1) => {
      const card = findContract(no)
      if (!card) return
      const at = columns.findIndex((col) => col.id === card.stageId)
      const target = columns[at + delta]
      if (target) moveCard(no, target.id, 0)
    },
    [findContract, columns, moveCard],
  )

  const openContract = openNo ? findContract(openNo) : undefined
  const editingContract = editingNo ? findContract(editingNo) : undefined
  const deletingContract = deletingNo ? findContract(deletingNo) : undefined
  const addingColumn = addingTo ? columns.find((col) => col.id === addingTo) : undefined

  const createColumn = () => {
    const name = newColumnName.trim()
    if (name === '') return
    // 색은 컬럼 수에 따라 돌려 씁니다. 만들자마자 옆 컬럼과 같은 색이면 구분이 안 됩니다.
    addColumn(name, TONES[columns.length % TONES.length], newColumnAfter ?? undefined)
    setNewColumnName('')
    setNewColumnAfter(null)
  }

  return (
    <section className={styles.page}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">영업 현황 보드</h1>

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

        <span className={styles.count}>{shownCount}건</span>
        <ViewToggle view="board" />
      </div>

      <div className={styles.board}>
        {columns.map((column) => (
          <StageColumn
            key={column.id}
            column={column}
            cards={shownByColumn.get(column.id) ?? []}
            dropSlot={dropKey}
            draggingNo={dragging?.no ?? null}
            others={columns.filter((col) => col.id !== column.id)}
            onOpen={setOpenNo}
            onGrab={grab}
            onNudge={nudge}
            onEditCard={setEditingNo}
            onDeleteCard={setDeletingNo}
            onAddCard={setAddingTo}
            onRename={renameColumn}
            onRecolor={recolorColumn}
            onAddAfter={(id) => setNewColumnAfter(id)}
            onRemove={removeColumn}
          />
        ))}

        <div className={styles.newColumn}>
          {newColumnAfter === null ? (
            <button
              type="button"
              className={styles.newButton}
              onClick={() => setNewColumnAfter('')}
            >
              <PlusIcon width={14} height={14} />
              컬럼 추가
            </button>
          ) : (
            <div className={styles.newForm}>
              <input
                autoFocus
                className={styles.newInput}
                value={newColumnName}
                placeholder="컬럼 이름"
                aria-label="새 컬럼 이름"
                onChange={(event) => setNewColumnName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') createColumn()
                  if (event.key === 'Escape') {
                    setNewColumnName('')
                    setNewColumnAfter(null)
                  }
                }}
              />
              <Button type="button" onClick={createColumn}>
                추가
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* 네이티브 드래그가 아니라 직접 그리므로, 끌고 다니는 조각도 우리가 띄웁니다. */}
      {dragging && point && (
        <div className={styles.dragChip} style={{ left: point.x, top: point.y }} aria-hidden="true">
          {dragging.label}
        </div>
      )}

      {openContract && (
        <ContractDrawer
          contract={openContract}
          stage={columns.find((col) => col.id === openContract.stageId)}
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

      {addingColumn && (
        <ContractForm
          stageName={addingColumn.name}
          onClose={() => setAddingTo(null)}
          onSubmit={(draft) => {
            addContract(draft, addingColumn.id)
            setAddingTo(null)
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
