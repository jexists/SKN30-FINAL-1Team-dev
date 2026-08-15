import { useCallback, useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react'

import { agendaById } from '@/shared/agenda'
import { aiSuggestions } from '@/shared/suggestions'
import type { AiSuggestion, CalendarEvent } from '@/types'
import usePointerDrag from '@/hooks/usePointerDrag'
import RecordDrawer from '@/pages/Dashboard/components/RecordDrawer'
import { parseISO, startOfMonth, TODAY, TODAY_ISO } from '@/utils/date'

import EventModal from './components/EventModal'
import MonthGrid from './components/MonthGrid'
import SuggestionPanel from './components/SuggestionPanel'
import { CELL_ATTR, type Dragging } from './dragging'
import useCalendarEvents, { DEFAULTS } from './useCalendarEvents'

import styles from './Calendar.module.scss'

export default function Calendar() {
  const { eventsByDate, addEvent, updateEvent, moveEvent, removeEvent } = useCalendarEvents()

  const [cursor, setCursor] = useState(() => startOfMonth(TODAY))
  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set())
  /** 상세를 보고 있는 일정. 칩을 누르면 고치기 전에 먼저 이것부터 폅니다. */
  const [viewingId, setViewingId] = useState<string | null>(null)
  const [editing, setEditing] = useState<CalendarEvent | null>(null)
  /** 새 일정을 만드는 날짜. 등록 모달을 그 날짜로 엽니다. */
  const [creating, setCreating] = useState<string | null>(null)
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

  // 놓인 자리의 표식은 날짜 칸의 ISO 문자열입니다. 이 화면의 어휘로 이름만 바꿔 받습니다.
  const { dragging, dropKey: dropISO, point, start } = usePointerDrag<Dragging>(CELL_ATTR, drop)

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

  const create = useCallback(
    (event: CalendarEvent) => {
      // 빈 id 는 addEvent 가 새로 매깁니다.
      setJustAddedId(addEvent(event).id)
      setCreating(null)
    },
    [addEvent],
  )

  // 목록이 바뀌면 이 컴포넌트가 다시 그려지므로 여기서 매번 집어 옵니다.
  const viewed = viewingId ? agendaById(viewingId) : undefined

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
          onOpenEvent={(event) => setViewingId(event.id)}
          onCreate={setCreating}
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

      {viewed && (
        <RecordDrawer
          item={viewed}
          done={viewed.done}
          onClose={() => setViewingId(null)}
          onEdit={(item) => {
            setViewingId(null)
            setEditing(item)
          }}
          onDelete={(id) => {
            setViewingId(null)
            removeEvent(id)
          }}
        />
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
