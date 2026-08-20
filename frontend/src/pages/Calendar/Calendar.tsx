import { useCallback, useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react'

import Button from '@/components/Button'
import usePointerDrag from '@/hooks/usePointerDrag'
import useOrderList from '@/pages/Orders/useOrderList'
import type { CalendarEvent } from '@/types'
import { startOfMonth, TODAY, TODAY_ISO } from '@/utils/date'

import EventModal from './components/EventModal'
import MonthGrid from './components/MonthGrid'
import SuggestionPanel from './components/SuggestionPanel'
import { CELL_ATTR, type Dragging } from './dragging'
import useCalendarEvents, { DEFAULTS } from './useCalendarEvents'

import styles from './Calendar.module.scss'

const SUGGESTION_API_ERROR = 'AI 추천 일정 조회 API가 백엔드에 제공되지 않습니다.'

export default function Calendar() {
  const [cursor, setCursor] = useState(() => startOfMonth(TODAY))
  const {
    eventsByDate,
    loading: eventsLoading,
    error: eventsError,
    reload: reloadEvents,
    addEvent,
    updateEvent,
    moveEvent,
    removeEvent,
  } = useCalendarEvents(cursor)
  const {
    orders,
    loading: ordersLoading,
    error: ordersError,
    reload: reloadOrders,
  } = useOrderList()
  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [editing, setEditing] = useState<CalendarEvent | null>(null)
  const [creating, setCreating] = useState<string | null>(null)
  const [justAddedId, setJustAddedId] = useState<string | null>(null)

  const deliveriesByDate = useMemo(
    () =>
      orders
        .filter((order) => order.stageOutcomeCode !== 'cancelled')
        .reduce<Map<string, number>>(
          (map, order) => map.set(order.expect, (map.get(order.expect) ?? 0) + 1),
          new Map(),
        ),
    [orders],
  )

  const move = useCallback(
    async (id: string, dateISO: string) => {
      try {
        const moved = await moveEvent(id, dateISO)
        if (!moved) return
        setSelectedISO(dateISO)
        setJustAddedId(moved.id)
      } catch {
        return
      }
    },
    [moveEvent],
  )

  const drop = useCallback(
    (dragged: Dragging, dateISO: string) => {
      if (dragged.kind === 'event') void move(dragged.id, dateISO)
    },
    [move],
  )

  const { dragging, dropKey: dropISO, point, start } = usePointerDrag<Dragging>(CELL_ATTR, drop)

  const grabEvent = useCallback(
    (pointer: ReactPointerEvent, event: CalendarEvent) =>
      start(pointer, { kind: 'event', id: event.id, label: `${event.time} ${event.title}` }),
    [start],
  )

  const create = useCallback(
    async (event: CalendarEvent) => {
      const added = await addEvent(event)
      setJustAddedId(added.id)
      setCreating(null)
    },
    [addEvent],
  )

  const save = useCallback(
    async (event: CalendarEvent) => {
      await updateEvent(event)
      setEditing(null)
    },
    [updateEvent],
  )

  const remove = useCallback(
    async (id: string) => {
      await removeEvent(id)
      setEditing(null)
    },
    [removeEvent],
  )

  const loading = eventsLoading || ordersLoading
  const error = eventsError ?? ordersError
  const reload = () => {
    reloadEvents()
    reloadOrders()
  }

  return (
    <section aria-busy={loading}>
      <h1 className="sr-only">캘린더</h1>

      {error && (
        <div role="alert">
          <span>{error}</span>{' '}
          <Button variant="outline" size="sm" onClick={reload}>
            다시 시도
          </Button>
        </div>
      )}
      {!error && loading && <p role="status">일정과 발주를 불러오는 중입니다.</p>}

      <div className={styles.layout}>
        <MonthGrid
          cursor={cursor}
          selectedISO={selectedISO}
          eventsByDate={eventsByDate}
          deliveriesByDate={deliveriesByDate}
          ghost={null}
          justAddedId={justAddedId}
          dragging={dragging}
          dropISO={dropISO}
          onCursorChange={setCursor}
          onSelect={setSelectedISO}
          onOpenEvent={setEditing}
          onCreate={setCreating}
          onGrabEvent={grabEvent}
        />

        <div className={styles.side}>
          <SuggestionPanel
            suggestions={[]}
            previewId={null}
            onPreview={() => undefined}
            onAccept={() => undefined}
            onDismiss={() => undefined}
            onGrab={() => undefined}
            onRefresh={() => undefined}
            error={SUGGESTION_API_ERROR}
          />
        </div>
      </div>

      {dragging && point && (
        <div className={styles.dragChip} style={{ left: point.x, top: point.y }} aria-hidden="true">
          {dragging.label}
        </div>
      )}

      {creating && (
        <EventModal
          draft={{ ...DEFAULTS, id: '', date: creating, title: '' }}
          mode="create"
          onClose={() => setCreating(null)}
          onSave={create}
        />
      )}

      {editing && (
        <EventModal
          draft={editing}
          onClose={() => setEditing(null)}
          onSave={save}
          onDelete={remove}
        />
      )}
    </section>
  )
}
