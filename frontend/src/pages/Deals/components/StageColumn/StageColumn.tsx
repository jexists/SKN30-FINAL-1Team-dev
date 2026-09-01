// 보드의 컬럼 하나입니다. 헤더(이름·건수·합계·설정)와 카드 목록을 갖습니다.
import { useState, type PointerEvent as ReactPointerEvent } from 'react'

import { PlusIcon } from '@/components/icons'
import type { ColumnTone } from '@/types'
import { won } from '@/utils/format'

import { DROP_ATTR, slotKey, type BoardColumn, type BoardDeal } from '../../board'
import ColumnMenu from '../ColumnMenu'
import DealCard from '../DealCard'

import styles from './StageColumn.module.scss'

/** 한 번에 그리는 카드 수. 확정 컬럼은 시드만 80건이 넘어 전부 그리면 무겁습니다. */
const PAGE = 15

interface Props {
  column: BoardColumn
  cards: BoardDeal[]
  /** 실제 API 카드는 UUID, 목업 카드는 영업번호를 상호작용 식별자로 씁니다. */
  identityOf?: (deal: BoardDeal) => string
  /** 실제 API에는 단계 CRUD가 없으므로 그 화면에서는 설정 메뉴를 숨깁니다. */
  editableStages?: boolean
  /** 카드마다 담당 영업을 세울지. 보드가 보기 범위를 보고 정합니다. */
  showOwner?: boolean
  readOnly?: boolean
  /** 지금 가리키고 있는 자리. `<컬럼 id>:<자리>` */
  dropSlot: string | null
  draggingIdentity: string | null
  others: BoardColumn[]
  onOpen: (identity: string) => void
  onGrab: (event: ReactPointerEvent, deal: BoardDeal, identity: string) => void
  onNudge: (identity: string, delta: -1 | 1) => void
  onEditCard: (identity: string) => void
  onDeleteCard: (identity: string) => void
  onAddCard: (columnId: string) => void
  onRename: (id: string, name: string) => void
  onRecolor: (id: string, tone: ColumnTone) => void
  onAddAfter: (id: string) => void
  onRemove: (id: string, moveToId: string) => void
}

export default function StageColumn({
  column,
  cards,
  identityOf = (deal) => deal.no,
  editableStages = true,
  showOwner = false,
  readOnly = false,
  dropSlot,
  draggingIdentity,
  others,
  onOpen,
  onGrab,
  onNudge,
  onEditCard,
  onDeleteCard,
  onAddCard,
  onRename,
  onRecolor,
  onAddAfter,
  onRemove,
}: Props) {
  const [limit, setLimit] = useState(PAGE)

  const visible = cards.slice(0, limit)
  const rest = cards.length - visible.length
  const total = cards.reduce((sum, c) => sum + c.amount, 0)

  return (
    <section className={[styles.column, styles[column.tone]].join(' ')}>
      <header className={styles.head}>
        <span className={styles.dot} aria-hidden="true" />
        <h2 className={styles.name}>{column.name}</h2>
        <span className={styles.count}>{cards.length}</span>
        <span className={`${styles.total} tnum`}>{won(total)}</span>

        {editableStages && (
          <ColumnMenu
            column={column}
            others={others}
            cardCount={cards.length}
            onRename={(name) => onRename(column.id, name)}
            onRecolor={(tone) => onRecolor(column.id, tone)}
            onAddAfter={() => onAddAfter(column.id)}
            onRemove={(moveToId) => onRemove(column.id, moveToId)}
          />
        )}
      </header>

      {/* 목록 자체도 놓을 자리입니다. 카드 아래 빈 곳에 놓으면 맨 끝으로 갑니다. */}
      <ul className={styles.list} {...{ [DROP_ATTR]: slotKey(column.id, cards.length) }}>
        {visible.map((card, index) => {
          const key = slotKey(column.id, index)
          const identity = identityOf(card)
          return (
            <li
              key={identity}
              className={[styles.slot, dropSlot === key && styles.isDropTarget]
                .filter(Boolean)
                .join(' ')}
              {...{ [DROP_ATTR]: key }}
            >
              <DealCard
                deal={card}
                identity={identity}
                isDragging={draggingIdentity === identity}
                onOpen={onOpen}
                onGrab={onGrab}
                onNudge={onNudge}
                onEdit={onEditCard}
                onDelete={onDeleteCard}
                showOwner={showOwner}
                readOnly={readOnly}
              />
            </li>
          )
        })}

        {cards.length === 0 && (
          <li
            className={[styles.empty, dropSlot === slotKey(column.id, 0) && styles.isDropTarget]
              .filter(Boolean)
              .join(' ')}
          >
            비어 있습니다
          </li>
        )}

        {rest > 0 && (
          <li>
            <button type="button" className={styles.more} onClick={() => setLimit(limit + PAGE)}>
              {rest}건 더 보기
            </button>
          </li>
        )}
      </ul>

      {!readOnly && (
        <button type="button" className={styles.add} onClick={() => onAddCard(column.id)}>
          <PlusIcon width={14} height={14} />
          영업 딜 추가
        </button>
      )}
    </section>
  )
}
