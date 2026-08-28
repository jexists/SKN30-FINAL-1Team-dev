import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'

import ErrorToast from '@/components/ErrorToast'
import usePointerDrag from '@/hooks/usePointerDrag'
import useOrderList from '@/pages/Orders/useOrderList'
import type { AiSuggestion, CalendarEvent } from '@/types'
import { startOfMonth, TODAY, TODAY_ISO } from '@/utils/date'

import CalendarSkeleton from './components/CalendarSkeleton'
import EventModal from './components/EventModal'
import MonthGrid from './components/MonthGrid'
import SuggestionPanel from './components/SuggestionPanel'
import { CELL_ATTR, type Dragging } from './dragging'
import useAiSuggestions from './useAiSuggestions'
import useCalendarEvents, { DEFAULTS } from './useCalendarEvents'

import styles from './Calendar.module.scss'

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
  const {
    suggestions,
    previewId,
    setPreviewId,
    refresh: refreshSuggestions,
    accept: acceptSuggestion,
    dismiss: dismissSuggestion,
  } = useAiSuggestions(addEvent)

  useEffect(() => {
    void refreshSuggestions()
  }, [refreshSuggestions])

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

  // 캘린더 칸에 놓인 AI 추천 카드를 그 날짜로 승인한다.
  const dropSuggestion = useCallback(
    async (id: string, dateISO: string) => {
      const suggestion = suggestions.find((s) => s.id === id)
      if (!suggestion) return
      try {
        const added = await acceptSuggestion(suggestion, dateISO)
        setSelectedISO(dateISO)
        setJustAddedId(added.id)
      } catch {
        return
      }
    },
    [suggestions, acceptSuggestion],
  )

  const drop = useCallback(
    (dragged: Dragging, dateISO: string) => {
      if (dragged.kind === 'event') void move(dragged.id, dateISO)
      else void dropSuggestion(dragged.id, dateISO)
    },
    [move, dropSuggestion],
  )

  const { dragging, dropKey: dropISO, point, start } = usePointerDrag<Dragging>(CELL_ATTR, drop)

  const grabEvent = useCallback(
    (pointer: ReactPointerEvent, event: CalendarEvent) =>
      start(pointer, { kind: 'event', id: event.id, label: `${event.time} ${event.title}` }),
    [start],
  )

  const grabSuggestion = useCallback(
    (pointer: ReactPointerEvent, suggestion: AiSuggestion) =>
      start(pointer, {
        kind: 'suggestion',
        id: suggestion.id,
        label: `${suggestion.time} ${suggestion.hospital}`,
      }),
    [start],
  )

  const acceptSuggestionToCalendar = useCallback(
    async (suggestion: AiSuggestion) => {
      try {
        const added = await acceptSuggestion(suggestion)
        setSelectedISO(added.date)
        setJustAddedId(added.id)
      } catch {
        return
      }
    },
    [acceptSuggestion],
  )

  // 닫는 일은 모달이 합니다. 등록한 뒤 결과를 보여 줄 자리가 있어야 해서입니다.
  const create = useCallback(
    async (event: CalendarEvent) => {
      const added = await addEvent(event)
      setJustAddedId(added.id)
    },
    [addEvent],
  )

  const save = useCallback(
    async (event: CalendarEvent) => {
      await updateEvent(event)
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

  // 첫 진입입니다. 달력 칸만 자리표시자로 두면 달·요일·날짜가 이미 다 그려진 화면에서
  // 칩만 깜빡여 무엇을 기다리는지 읽히지 않습니다. 카드 두 장을 통째로 덮습니다.
  if (loading && eventsByDate.size === 0 && !error) {
    return (
      <section aria-busy>
        <h1 className="sr-only">캘린더</h1>
        <CalendarSkeleton />
      </section>
    )
  }

  return (
    <section aria-busy={loading}>
      <h1 className="sr-only">캘린더</h1>

      <ErrorToast message={error} onRetry={reload} />
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
            suggestions={suggestions}
            previewId={previewId}
            onPreview={setPreviewId}
            onAccept={acceptSuggestionToCalendar}
            onDismiss={dismissSuggestion}
            onGrab={grabSuggestion}
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
