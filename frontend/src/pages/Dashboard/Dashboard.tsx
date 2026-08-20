import { useCallback, useMemo, useRef, useState } from 'react'

import Button from '@/components/Button'
import Modal from '@/components/Modal'
import type { AgendaItem, CalendarEvent, Notice } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'
import EventModal from '@/pages/Calendar/components/EventModal'
import useCalendarEvents, { DEFAULTS } from '@/pages/Calendar/useCalendarEvents'
import useSupportRequests from '@/pages/Complaints/useSupportRequests'
import useSalesDeals from '@/pages/Deals/useSalesDeals'
import useOrderList from '@/pages/Orders/useOrderList'
import { useNotices } from '@/shared/notices'
import { addDays, iso, TODAY, TODAY_ISO } from '@/utils/date'

import DayAgenda from './components/DayAgenda'
import ListDrawer from './components/ListDrawer'
import NoticeDrawer from './components/NoticeDrawer'
import NoticeTicker from './components/NoticeTicker'
import RecordDrawer from './components/RecordDrawer'
import SummaryBand from './components/SummaryBand'
import WeekCalendar from './components/WeekCalendar'
import { kpiList, type KpiListKey } from './drawerLists'

import styles from './Dashboard.module.scss'

const rangeStart = (offset: number) => addDays(TODAY, -2 + offset * 7)
const FLASH_MS = 1400

type OpenDrawer =
  | { type: 'addEvent' }
  | { type: 'record'; item: AgendaItem }
  | { type: 'kpi'; key: KpiListKey }
  | { type: 'notice'; label: string; notice: Notice }

export default function Dashboard() {
  const {
    events,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
    addEvent,
    updateEvent,
    removeEvent,
    toggleComplete,
  } = useCalendarEvents()
  const {
    notices,
    directives,
    loading: noticesLoading,
    error: noticesError,
    reload: reloadNotices,
  } = useNotices()
  const {
    requests,
    loading: supportLoading,
    error: supportError,
    reload: reloadSupport,
  } = useSupportRequests(null)
  const {
    cards: deals,
    loading: dealsLoading,
    error: dealsError,
    reload: reloadDeals,
  } = useSalesDeals(null, null, 'list')
  const {
    orders,
    loading: ordersLoading,
    error: ordersError,
    reload: reloadOrders,
  } = useOrderList()

  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [weekOffset, setWeekOffset] = useState(0)
  const [flash, setFlash] = useState(false)
  const [open, setOpen] = useState<OpenDrawer | null>(null)
  const [editing, setEditing] = useState<AgendaItem | null>(null)
  const [deleting, setDeleting] = useState<AgendaItem | null>(null)

  const doneIds = useMemo(
    () => new Set(events.filter((event) => event.done).map((event) => event.id)),
    [events],
  )
  const agendaRef = useRef<HTMLElement>(null)
  const reduceMotion = useMediaQuery('(prefers-reduced-motion: reduce)')

  const changeWeek = useCallback((offset: number) => {
    setWeekOffset(offset)
    setSelectedISO(iso(rangeStart(offset)))
  }, [])

  const goToday = useCallback(() => {
    setWeekOffset(0)
    setSelectedISO(TODAY_ISO)
  }, [])

  const toggleDone = useCallback(
    (id: string) => {
      const event = events.find((item) => item.id === id)
      if (event) void toggleComplete(id, event.done).catch(() => undefined)
    },
    [events, toggleComplete],
  )

  const closeDrawer = useCallback(() => setOpen(null), [])

  const jumpToToday = useCallback(() => {
    goToday()
    agendaRef.current?.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'start',
    })
    setFlash(true)
    setTimeout(() => setFlash(false), FLASH_MS)
  }, [goToday, reduceMotion])

  const error = agendaError ?? noticesError ?? supportError ?? dealsError ?? ordersError
  const loading = agendaLoading || noticesLoading || supportLoading || dealsLoading || ordersLoading

  const reload = () => {
    reloadAgenda()
    reloadNotices()
    reloadSupport()
    reloadDeals()
    reloadOrders()
  }

  return (
    <section aria-busy={loading}>
      <h1 className="sr-only">영업 대시보드</h1>

      {error && (
        <div className={styles.state} role="alert">
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={reload}>
            다시 시도
          </Button>
        </div>
      )}
      {!error && loading && (
        <p className={styles.state} role="status">
          대시보드 데이터를 불러오는 중입니다.
        </p>
      )}

      <div className={styles.notices}>
        <NoticeTicker
          items={notices}
          onOpen={(notice) => setOpen({ type: 'notice', label: '공지', notice })}
        />
        <NoticeTicker
          label="팀장 지시사항"
          items={directives}
          onOpen={(notice) => setOpen({ type: 'notice', label: '팀장 지시사항', notice })}
        />
      </div>

      <SummaryBand
        requests={requests}
        deals={deals}
        onJumpToToday={jumpToToday}
        onOpenList={(key) => setOpen({ type: 'kpi', key })}
      />

      <WeekCalendar
        weekOffset={weekOffset}
        selectedISO={selectedISO}
        onSelect={setSelectedISO}
        onWeekChange={changeWeek}
        onToday={goToday}
      />

      <DayAgenda
        ref={agendaRef}
        dateISO={selectedISO}
        doneIds={doneIds}
        onToggleDone={toggleDone}
        onOpen={(item) => setOpen({ type: 'record', item })}
        onAddSchedule={() => setOpen({ type: 'addEvent' })}
        onEdit={setEditing}
        onDelete={setDeleting}
        flash={flash}
      />

      {open?.type === 'addEvent' && (
        <EventModal
          mode="create"
          draft={
            {
              ...DEFAULTS,
              kind: 'visit',
              id: '',
              date: selectedISO,
              title: '',
            } satisfies CalendarEvent
          }
          onClose={closeDrawer}
          onSave={(event) => {
            const { id: _id, ...draft } = event
            void addEvent(draft).catch(() => undefined)
            setSelectedISO(draft.date)
            closeDrawer()
          }}
        />
      )}

      {editing && (
        <EventModal
          draft={editing}
          onClose={() => setEditing(null)}
          onSave={(event) => {
            void updateEvent(event).catch(() => undefined)
            setSelectedISO(event.date)
            setEditing(null)
          }}
        />
      )}

      {deleting && (
        <Modal
          title="일정을 삭제할까요?"
          description="되돌릴 수 없습니다."
          onClose={() => setDeleting(null)}
          footer={
            <>
              <Button type="button" variant="outline" onClick={() => setDeleting(null)}>
                취소
              </Button>
              <Button
                type="button"
                onClick={() => {
                  void removeEvent(deleting.id).catch(() => undefined)
                  setDeleting(null)
                }}
              >
                삭제
              </Button>
            </>
          }
        >
          <p className={styles.confirm}>
            {deleting.time} · {deleting.hospital || deleting.title}
          </p>
        </Modal>
      )}

      {open?.type === 'record' && (
        <RecordDrawer
          item={open.item}
          done={doneIds.has(open.item.id)}
          deals={deals}
          orders={orders}
          relatedLoading={dealsLoading || ordersLoading}
          relatedError={dealsError ?? ordersError}
          onRetryRelated={() => {
            reloadDeals()
            reloadOrders()
          }}
          onClose={closeDrawer}
        />
      )}

      {open?.type === 'kpi' && (
        <ListDrawer list={kpiList(open.key, requests, deals)} onClose={closeDrawer} />
      )}

      {open?.type === 'notice' && (
        <NoticeDrawer label={open.label} notice={open.notice} onClose={closeDrawer} />
      )}
    </section>
  )
}
