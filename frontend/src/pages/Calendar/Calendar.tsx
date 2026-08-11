import { useCallback, useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react'

import { aiSuggestions } from '@/content/suggestions'
import type { AiSuggestion, CalendarEvent } from '@/content/types'
import { parseISO, startOfMonth, TODAY, TODAY_ISO } from '@/utils/date'

import EventModal from './components/EventModal'
import MonthGrid from './components/MonthGrid'
import SuggestionPanel from './components/SuggestionPanel'
import useCalendarEvents from './useCalendarEvents'
import usePointerDrag, { type Dragging } from './usePointerDrag'

import styles from './Calendar.module.scss'

export default function Calendar() {
  const { eventsByDate, addEvent, updateEvent, moveEvent, removeEvent } = useCalendarEvents()

  const [cursor, setCursor] = useState(() => startOfMonth(TODAY))
  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set())
  const [editing, setEditing] = useState<CalendarEvent | null>(null)
  const [justAddedId, setJustAddedId] = useState<string | null>(null)

  const suggestions = useMemo(() => aiSuggestions.filter((s) => !dismissed.has(s.id)), [dismissed])

  const dismiss = useCallback((id: string) => {
    setDismissed((prev) => new Set(prev).add(id))
    setPreviewId(null)
  }, [])

  /** dateISO 를 주면 추천일 대신 그 날짜로 넣습니다. 끌어다 놓은 경우입니다. */
  const accept = useCallback(
    (s: AiSuggestion, dateISO?: string) => {
      const date = dateISO ?? s.date
      const added = addEvent({
        date,
        time: s.time,
        dur: s.dur,
        kind: s.kind,
        title: s.title,
        hospital: s.hospital,
        dept: s.dept,
        contact: s.contact,
        place: s.place,
        brief: s.reason,
      })
      // 넣은 자리가 화면 밖이면 확인할 수 없으니 그 달로 옮기고 그 날을 고릅니다.
      setCursor(startOfMonth(parseISO(date)))
      setSelectedISO(date)
      setJustAddedId(added.id)
      dismiss(s.id)
    },
    [addEvent, dismiss],
  )

  /** 끌던 것을 이 날짜에 놓습니다. */
  const drop = useCallback(
    (dragged: Dragging, dateISO: string) => {
      if (dragged.kind === 'event') {
        moveEvent(dragged.id, dateISO)
        setSelectedISO(dateISO)
        setJustAddedId(dragged.id)
        return
      }
      const s = suggestions.find((item) => item.id === dragged.id)
      if (s) accept(s, dateISO)
    },
    [suggestions, moveEvent, accept],
  )

  const { dragging, dropISO, point, start } = usePointerDrag(drop)

  const grabEvent = useCallback(
    (pointer: ReactPointerEvent, event: CalendarEvent) =>
      start(pointer, { kind: 'event', id: event.id, label: `${event.time} ${event.title}` }),
    [start],
  )

  const grabSuggestion = useCallback(
    (pointer: ReactPointerEvent, s: AiSuggestion) =>
      start(pointer, { kind: 'suggestion', id: s.id, label: `${s.time} ${s.title}` }),
    [start],
  )

  // 가리키거나 끌고 있는 추천을 달력이 이해하는 모양으로 바꿔 넘깁니다.
  // 끄는 중에는 고스트가 추천일이 아니라 지금 가리키는 칸에 붙습니다.
  const ghost = useMemo(() => {
    const dragged = dragging?.kind === 'suggestion' ? dragging.id : null
    const s = suggestions.find((item) => item.id === (dragged ?? previewId))
    if (!s) return null
    return {
      date: dragged ? (dropISO ?? s.date) : s.date,
      time: s.time,
      title: s.title,
      kind: s.kind,
    }
  }, [suggestions, previewId, dragging, dropISO])

  const quickAdd = useCallback(
    (dateISO: string, title: string) => {
      setJustAddedId(addEvent({ date: dateISO, title }).id)
    },
    [addEvent],
  )

  const save = useCallback(
    (event: CalendarEvent) => {
      updateEvent(event)
      setEditing(null)
    },
    [updateEvent],
  )

  const remove = useCallback(
    (id: string) => {
      removeEvent(id)
      setEditing(null)
    },
    [removeEvent],
  )

  return (
    <section>
      {/* Topbar breadcrumb 이 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">캘린더</h1>

      <div className={styles.layout}>
        <MonthGrid
          cursor={cursor}
          selectedISO={selectedISO}
          eventsByDate={eventsByDate}
          ghost={ghost}
          justAddedId={justAddedId}
          dragging={dragging}
          dropISO={dropISO}
          onCursorChange={setCursor}
          onSelect={setSelectedISO}
          onOpenEvent={setEditing}
          onQuickAdd={quickAdd}
          onGrabEvent={grabEvent}
        />

        <div className={styles.side}>
          <SuggestionPanel
            suggestions={suggestions}
            previewId={previewId}
            onPreview={setPreviewId}
            onAccept={accept}
            onDismiss={dismiss}
            onGrab={grabSuggestion}
          />
        </div>
      </div>

      {/* 네이티브 드래그가 아니라 직접 그리므로, 끌고 다니는 조각도 우리가 띄웁니다. */}
      {dragging && point && (
        <div className={styles.dragChip} style={{ left: point.x, top: point.y }} aria-hidden="true">
          {dragging.label}
        </div>
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
