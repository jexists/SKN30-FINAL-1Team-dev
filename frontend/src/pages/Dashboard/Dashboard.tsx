import { useCallback, useRef, useState } from 'react'

import Button from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import Modal from '@/components/Modal'
import type { AgendaItem, CalendarEvent, Notice } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'
import EventModal from '@/pages/Calendar/components/EventModal'
import { DEFAULTS, useAgendaMutations } from '@/pages/Calendar/useCalendarEvents'
import { toNotice } from '@/shared/notices'
import { iso, TODAY_ISO } from '@/utils/date'

import DashboardSkeleton from './components/DashboardSkeleton'
import DayAgenda from './components/DayAgenda'
import ListDrawer from './components/ListDrawer'
import NoticeDrawer from './components/NoticeDrawer'
import NoticeTicker from './components/NoticeTicker'
import RecordDrawer from './components/RecordDrawer'
import SummaryBand from './components/SummaryBand'
import WeekCalendar from './components/WeekCalendar'
import { csList, followUpList, renewalList, type KpiListKey } from './drawerLists'
import useDashboard, {
  useFollowUpList,
  useRenewalList,
  useSupportList,
  weekStart,
} from './useDashboard'

import styles from './Dashboard.module.scss'

const FLASH_MS = 1400

type OpenDrawer =
  | { type: 'addEvent' }
  | { type: 'record'; item: AgendaItem }
  | { type: 'kpi'; key: KpiListKey }
  | { type: 'notice'; label: string; notice: Notice }

export default function Dashboard() {
  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [weekOffset, setWeekOffset] = useState(0)
  const [flash, setFlash] = useState(false)
  const [open, setOpen] = useState<OpenDrawer | null>(null)
  const [editing, setEditing] = useState<AgendaItem | null>(null)
  const [deleting, setDeleting] = useState<AgendaItem | null>(null)

  const { data, loading, error: loadError, reload } = useDashboard(weekOffset)
  // 일정 목록은 하루씩 받아 옵니다. 오늘치는 위 응답이 이미 심어 두어 다시 받지 않습니다.
  const { mutationError, addEvent, updateEvent, removeEvent, toggleComplete } = useAgendaMutations()

  // 드로어는 눌러야 열립니다. 열린 것만 자기 목록을 받아 옵니다.
  const kpiKey = open?.type === 'kpi' ? open.key : null
  const followUps = useFollowUpList(kpiKey === 'followUp')
  const support = useSupportList(kpiKey === 'cs')
  const renewals = useRenewalList(kpiKey === 'renewal', data?.date ?? TODAY_ISO)

  const agendaRef = useRef<HTMLElement>(null)
  const reduceMotion = useMediaQuery('(prefers-reduced-motion: reduce)')

  const changeWeek = useCallback((offset: number) => {
    setWeekOffset(offset)
    setSelectedISO(iso(weekStart(offset)))
  }, [])

  const goToday = useCallback(() => {
    setWeekOffset(0)
    setSelectedISO(TODAY_ISO)
  }, [])

  const toggleDone = useCallback(
    (item: AgendaItem) => {
      // 타일의 오늘 일정 수는 완료 여부와 무관하지만, 후속업무 수는 따라 움직입니다.
      void toggleComplete(item.id, item.done)
        .then(reload)
        .catch(() => undefined)
    },
    [reload, toggleComplete],
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

  const error = loadError ?? mutationError

  return (
    <section aria-busy={loading}>
      <h1 className="sr-only">영업 대시보드</h1>

      <ErrorToast message={error} onRetry={reload} />
      {/* 주를 옮기면 다시 받아 오지만 자리표시자로 되돌리지는 않습니다. 화살표를 누를
          때마다 화면 전체가 사라졌다 서면 어디를 보고 있었는지 놓칩니다. */}
      {data === null ? (
        <DashboardSkeleton />
      ) : (
        <>
          <div className={styles.notices}>
            <NoticeTicker
              items={data.notices.items.map((item) => toNotice(item, 'team'))}
              onOpen={(notice) => setOpen({ type: 'notice', label: '공지', notice })}
            />
            <NoticeTicker
              label="팀장 지시사항"
              items={data.directives.items.map((item) => toNotice(item, 'personal'))}
              onOpen={(notice) => setOpen({ type: 'notice', label: '팀장 지시사항', notice })}
            />
          </div>

          <SummaryBand
            data={data}
            onJumpToToday={jumpToToday}
            onOpenList={(key) => setOpen({ type: 'kpi', key })}
          />

          <WeekCalendar
            weekly={data.weekly}
            weekOffset={weekOffset}
            selectedISO={selectedISO}
            onSelect={setSelectedISO}
            onWeekChange={changeWeek}
            onToday={goToday}
          />

          <DayAgenda
            ref={agendaRef}
            dateISO={selectedISO}
            onToggleDone={toggleDone}
            onOpen={(item) => setOpen({ type: 'record', item })}
            onAddSchedule={() => setOpen({ type: 'addEvent' })}
            onEdit={setEditing}
            onDelete={setDeleting}
            flash={flash}
          />
        </>
      )}

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
          // 닫는 일은 모달이 합니다. 등록한 뒤 결과를 보여 줄 자리가 있어야 해서입니다.
          onSave={(event) => {
            const { id: _id, ...draft } = event
            void addEvent(draft)
              .then(reload)
              .catch(() => undefined)
            setSelectedISO(draft.date)
          }}
        />
      )}

      {editing && (
        <EventModal
          draft={editing}
          onClose={() => setEditing(null)}
          onSave={(event) => {
            void updateEvent(event)
              .then(reload)
              .catch(() => undefined)
            setSelectedISO(event.date)
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
                  void removeEvent(deleting.id)
                    .then(reload)
                    .catch(() => undefined)
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

      {open?.type === 'record' && <RecordDrawer item={open.item} onClose={closeDrawer} />}

      {kpiKey === 'followUp' && data !== null && (
        <ListDrawer
          list={followUpList(followUps.items, data.follow_ups)}
          loading={followUps.loading}
          error={followUps.error}
          onRetry={followUps.reload}
          remaining={followUps.total - followUps.items.length}
          loadingMore={followUps.loadingMore}
          onLoadMore={followUps.loadMore}
          onClose={closeDrawer}
        />
      )}
      {kpiKey === 'cs' && (
        <ListDrawer
          list={csList(support.items)}
          loading={support.loading}
          error={support.error}
          onRetry={support.reload}
          remaining={support.total - support.items.length}
          loadingMore={support.loadingMore}
          onLoadMore={support.loadMore}
          onClose={closeDrawer}
        />
      )}
      {kpiKey === 'renewal' && (
        <ListDrawer
          list={renewalList(renewals.items)}
          loading={renewals.loading}
          error={renewals.error}
          onRetry={renewals.reload}
          remaining={renewals.total - renewals.items.length}
          loadingMore={renewals.loadingMore}
          onLoadMore={renewals.loadMore}
          onClose={closeDrawer}
        />
      )}

      {open?.type === 'notice' && (
        <NoticeDrawer label={open.label} notice={open.notice} onClose={closeDrawer} />
      )}
    </section>
  )
}
