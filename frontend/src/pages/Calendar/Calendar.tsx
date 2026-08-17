import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'

import Button from '@/components/Button'
import { readProfileId } from '@/mocks'
import { aiSuggestions } from '@/shared/suggestions'
import type { AiSuggestion, CalendarEvent } from '@/types'
import usePointerDrag from '@/hooks/usePointerDrag'
import { parseISO, startOfMonth, TODAY, TODAY_ISO } from '@/utils/date'

import EventModal from './components/EventModal'
import MonthGrid from './components/MonthGrid'
import SuggestionPanel from './components/SuggestionPanel'
import { CELL_ATTR, type Dragging } from './dragging'
import useCalendarEvents, { DEFAULTS } from './useCalendarEvents'

import styles from './Calendar.module.scss'

const acceptedStorageKey = () => `salesluv.calendar.accepted:${readProfileId() ?? 'default'}`

function readAccepted(): ReadonlySet<string> {
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(acceptedStorageKey()) ?? '[]')
    return new Set(
      Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string') : [],
    )
  } catch {
    return new Set()
  }
}

export default function Calendar() {
  const [cursor, setCursor] = useState(() => startOfMonth(TODAY))
  const {
    events,
    eventsByDate,
    loading,
    error,
    reload,
    addEvent,
    updateEvent,
    moveEvent,
    removeEvent,
  } = useCalendarEvents(cursor)
  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set())
  const [accepted, setAccepted] = useState<ReadonlySet<string>>(readAccepted)
  const [refreshing, setRefreshing] = useState(false)
  const [editing, setEditing] = useState<CalendarEvent | null>(null)
  /** 새 일정을 만드는 날짜. 등록 모달을 그 날짜로 엽니다. */
  const [creating, setCreating] = useState<string | null>(null)
  const [justAddedId, setJustAddedId] = useState<string | null>(null)
  const accepting = useRef(new Set<string>())

  const suggestions = useMemo(() => {
    if (loading || error) return []
    // ponytail: activity에 추천 원본 ID가 없어 고정 추천 6개의 고유 제목으로 중복만 막습니다.
    // 추천이 동적으로 늘면 activity에 source_id를 추가해야 합니다.
    const existingTitles = new Set(events.map((event) => event.title))
    return aiSuggestions.filter(
      (suggestion) =>
        !accepted.has(suggestion.id) &&
        !dismissed.has(suggestion.id) &&
        !existingTitles.has(suggestion.title),
    )
  }, [accepted, dismissed, error, events, loading])

  useEffect(() => {
    try {
      sessionStorage.setItem(acceptedStorageKey(), JSON.stringify([...accepted]))
    } catch {
      // 현재 화면에서는 accepted 상태와 DB 제목 대조가 중복을 막습니다.
    }
  }, [accepted])

  const dismiss = useCallback((id: string) => {
    setDismissed((prev) => new Set(prev).add(id))
    setPreviewId(null)
  }, [])

  /** dateISO 를 주면 추천일 대신 그 날짜로 넣습니다. 끌어다 놓은 경우입니다. */
  const accept = useCallback(
    async (s: AiSuggestion, dateISO?: string) => {
      if (loading || error || accepting.current.has(s.id)) return
      accepting.current.add(s.id)
      const date = dateISO ?? s.date
      try {
        const added = await addEvent({
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
        setAccepted((prev) => new Set(prev).add(s.id))
        dismiss(s.id)
      } catch {
        return
      } finally {
        accepting.current.delete(s.id)
      }
    },
    [addEvent, dismiss, error, loading],
  )

  // 목업이라 부를 서버가 없습니다. 닫아 둔 추천을 되살리는 것이 다시 받아 온
  // 결과이고, 짧은 지연은 이 자리에 붙을 API 호출의 자리입니다.
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => clearTimeout(refreshTimer.current ?? undefined), [])

  const refresh = useCallback(() => {
    setRefreshing(true)
    setPreviewId(null)
    refreshTimer.current = setTimeout(() => {
      setDismissed(new Set(accepted))
      setRefreshing(false)
    }, 600)
  }, [accepted])

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

  /** 끌던 것을 이 날짜에 놓습니다. */
  const drop = useCallback(
    (dragged: Dragging, dateISO: string) => {
      if (dragged.kind === 'event') {
        void move(dragged.id, dateISO)
        return
      }
      const s = suggestions.find((item) => item.id === dragged.id)
      if (s) void accept(s, dateISO)
    },
    [suggestions, move, accept],
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

  return (
    <section>
      {/* Topbar breadcrumb 이 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">캘린더</h1>

      {error && (
        <div role="alert">
          <span>{error}</span>{' '}
          <Button variant="outline" size="sm" onClick={reload}>
            다시 시도
          </Button>
        </div>
      )}
      {loading && <p role="status">일정을 불러오는 중입니다.</p>}

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
            onRefresh={refresh}
            refreshing={refreshing || loading}
          />
        </div>
      </div>

      {/* 네이티브 드래그가 아니라 직접 그리므로, 끌고 다니는 조각도 우리가 띄웁니다. */}
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
