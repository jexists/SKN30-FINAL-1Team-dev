import { useState, type PointerEvent as ReactPointerEvent } from 'react'

import { PlusIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import { KIND_LABEL } from '@/shared/agenda'
import type { AgendaKind, CalendarEvent } from '@/types'

import { CELL_ATTR, type Dragging } from '../../dragging'

import styles from './DayCell.module.scss'

/** 추천 카드를 가리키는 동안 셀에 미리 앉혀 보는 자리 */
export interface Ghost {
  date: string
  time: string
  title: string
  kind: AgendaKind
}

interface Props {
  date: Date
  dateISO: string
  isOther: boolean
  isToday: boolean
  isSelected: boolean
  /** 이 칸이 그리드의 탭 진입점인지 */
  tabbable: boolean
  /** '8월 11일 (화)' */
  label: string
  events: CalendarEvent[]
  deliveries: number
  ghost: Ghost | null
  justAddedId: string | null
  /** 지금 끌고 있는 것. 일정이면 원본 칩을 흐리게 두어 어디서 떠났는지 보이게 합니다. */
  dragging: Dragging | null
  /** 놓으면 여기로 들어간다는 표시 */
  isDropTarget: boolean
  onSelect: (dateISO: string) => void
  onOpenEvent: (event: CalendarEvent) => void
  /** 그 날짜로 일정 등록 모달을 엽니다. */
  onCreate: (dateISO: string) => void
  onGrabEvent: (pointer: ReactPointerEvent, event: CalendarEvent) => void
}

const KIND_TONE: Partial<Record<AgendaKind, string>> = {
  visit: styles.kindBlue,
  demo: styles.kindPurple,
  booth: styles.kindPurple,
  edu: styles.kindGreen,
  delivery: styles.kindOrange,
}

// 넷째 칸부터는 "+N" 으로 접습니다. 칸 높이를 넘기면 줄이 밀립니다.
const MAX_CHIPS = 3

export default function DayCell({
  date,
  dateISO,
  isOther,
  isToday,
  isSelected,
  tabbable,
  label,
  events,
  deliveries,
  ghost,
  justAddedId,
  dragging,
  isDropTarget,
  onSelect,
  onOpenEvent,
  onCreate,
  onGrabEvent,
}: Props) {
  const [listOpen, setListOpen] = useState(false)

  const dow = date.getDay()
  const visible = events.slice(0, MAX_CHIPS)
  const hidden = events.length - visible.length

  const cls = [
    styles.cell,
    isOther && styles.isOther,
    isSelected && styles.isSelected,
    (ghost || isDropTarget) && styles.isGhostTarget,
  ]
    .filter(Boolean)
    .join(' ')

  const numCls = [
    styles.num,
    'tnum',
    isToday && styles.isToday,
    dow === 0 && styles.isSun,
    dow === 6 && styles.isSat,
  ]
    .filter(Boolean)
    .join(' ')

  const openCreate = () => {
    onSelect(dateISO)
    onCreate(dateISO)
  }

  const renderChip = (event: CalendarEvent) => (
    <div
      key={event.id}
      role="button"
      tabIndex={0}
      className={[
        styles.chip,
        KIND_TONE[event.kind],
        event.done && styles.isDone,
        event.id === justAddedId && styles.isNew,
        dragging?.kind === 'event' && dragging.id === event.id && styles.isDragging,
      ]
        .filter(Boolean)
        .join(' ')}
      onPointerDown={(pointer) => {
        pointer.stopPropagation()
        onGrabEvent(pointer, event)
      }}
      onClick={(e) => {
        e.stopPropagation()
        onOpenEvent(event)
      }}
      onKeyDown={(e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return
        // 스페이스는 두면 페이지가 스크롤됩니다. 화살표는 막지 않고 격자로 흘려보냅니다.
        e.preventDefault()
        e.stopPropagation()
        onOpenEvent(event)
      }}
      onDoubleClick={(e) => e.stopPropagation()}
    >
      <span className={`${styles.chipTime} tnum`}>{event.time}</span>
      <span className={styles.chipTitle}>{event.title}</span>
    </div>
  )

  return (
    <div
      className={cls}
      role="gridcell"
      aria-selected={isSelected}
      // 놓을 자리를 찾을 때 이 표식을 봅니다. usePointerDrag 참고.
      {...{ [CELL_ATTR]: dateISO }}
      onClick={() => onSelect(dateISO)}
      onDoubleClick={openCreate}
    >
      <div className={styles.top}>
        <button
          type="button"
          className={numCls}
          data-iso={dateISO}
          tabIndex={tabbable ? 0 : -1}
          aria-label={`${label}, 일정 ${events.length}건`}
        >
          {date.getDate()}
        </button>

        <span className={styles.marks}>
          {deliveries > 0 && (
            <i className={styles.dotDelivery} title={`업무 ${deliveries}건`} aria-hidden="true" />
          )}
          <button
            type="button"
            className={styles.add}
            aria-label={`${label} 일정 추가`}
            onClick={(e) => {
              e.stopPropagation()
              openCreate()
            }}
          >
            <PlusIcon width={13} height={13} />
          </button>
        </span>
      </div>

      <div className={styles.chips}>
        {visible.map(renderChip)}

        {ghost && (
          <span className={styles.ghost} aria-hidden="true">
            <span className={`${styles.chipTime} tnum`}>{ghost.time}</span>
            <span className={styles.chipTitle}>{ghost.title}</span>
          </span>
        )}

        {hidden > 0 && (
          <Popover
            open={listOpen}
            onClose={() => setListOpen(false)}
            align="start"
            label={`${label} 일정 전체`}
            trigger={
              <button
                type="button"
                className={styles.more}
                aria-expanded={listOpen}
                aria-label={`${label} 일정 ${events.length}건 모두 보기`}
                onClick={(e) => {
                  e.stopPropagation()
                  setListOpen((v) => !v)
                }}
              >
                +{hidden}
              </button>
            }
          >
            <div className={styles.pop} onClick={(e) => e.stopPropagation()}>
              <p className={styles.popHead}>{label}</p>
              {events.map((event) => (
                <button
                  key={event.id}
                  type="button"
                  className={styles.popItem}
                  onClick={() => {
                    setListOpen(false)
                    onOpenEvent(event)
                  }}
                >
                  <span className={`${styles.popTime} tnum`}>{event.time}</span>
                  <span className={styles.popBody}>
                    <b>{event.title}</b>
                    <span>
                      {KIND_LABEL[event.kind]}
                      {event.hospital ? ` · ${event.hospital}` : ''}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </Popover>
        )}
      </div>
    </div>
  )
}
