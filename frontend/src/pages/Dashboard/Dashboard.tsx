import { useCallback, useRef, useState } from 'react'

import { directives } from '@/shared/notices'
import type { AgendaItem, CalendarEvent, Notice } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'
import EventModal from '@/pages/Calendar/components/EventModal'
import useCalendarEvents, { DEFAULTS } from '@/pages/Calendar/useCalendarEvents'
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

// 주간 캘린더는 오늘을 왼쪽에서 셋째 칸에 둡니다. 주를 옮기면 보이는 범위의
// 첫날을 고르게 해 선택이 화면 밖으로 나가지 않게 합니다.
const rangeStart = (offset: number) => addDays(TODAY, -2 + offset * 7)

const FLASH_MS = 1400

/** 열려 있는 드로어. 한 번에 하나만 뜹니다. */
type OpenDrawer =
  | { type: 'addEvent' }
  | { type: 'record'; item: AgendaItem }
  | { type: 'kpi'; key: KpiListKey }
  | { type: 'notice'; label: string; notice: Notice }

export default function Dashboard() {
  // 캘린더와 같은 일정 목록입니다. 여기서 등록한 것이 그쪽에도 그대로 있습니다.
  const { addEvent } = useCalendarEvents()
  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [weekOffset, setWeekOffset] = useState(0)
  const [doneIds, setDoneIds] = useState<ReadonlySet<string>>(new Set())
  const [flash, setFlash] = useState(false)
  const [open, setOpen] = useState<OpenDrawer | null>(null)

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

  const toggleDone = useCallback((id: string) => {
    // 메모리에만 둡니다. 저장하지 않으므로 새로고침하면 초기 상태로 돌아갑니다.
    setDoneIds((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }, [])

  const closeDrawer = useCallback(() => setOpen(null), [])

  // '오늘 방문 회사' 타일은 패널을 여는 대신 아젠다로 내려보냅니다.
  // 답이 이미 페이지 안에 있어 잠깐 강조하는 것으로 충분합니다.
  const jumpToToday = useCallback(() => {
    goToday()
    agendaRef.current?.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'start',
    })
    setFlash(true)
    setTimeout(() => setFlash(false), FLASH_MS)
  }, [goToday, reduceMotion])

  return (
    <section>
      {/* Topbar breadcrumb 이 이미 화면 이름을 말하므로, 이 제목은 스크린리더용
          문서 개요만 잡습니다. */}
      <h1 className="sr-only">영업 대시보드</h1>

      <div className={styles.notices}>
        <NoticeTicker onOpen={(notice) => setOpen({ type: 'notice', label: '공지', notice })} />
        <NoticeTicker
          label="팀장 지시사항"
          items={directives}
          onOpen={(notice) => setOpen({ type: 'notice', label: '팀장 지시사항', notice })}
        />
      </div>

      <SummaryBand
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
        flash={flash}
      />

      {open?.type === 'addEvent' && (
        <EventModal
          mode="create"
          // 영업 화면이라 새 일정은 미팅으로 열어 둡니다. DEFAULTS 의 'internal' 은
          // 캘린더 인라인 추가(제목만 받는 자리)의 기본값이라 여기서는 뒤집습니다.
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
            // id 는 스토어가 붙입니다. 모달이 들고 있던 빈 id 는 넘기지 않습니다.
            const { id: _id, ...draft } = event
            addEvent(draft)
            setSelectedISO(draft.date)
            closeDrawer()
          }}
        />
      )}

      {open?.type === 'record' && (
        <RecordDrawer item={open.item} done={doneIds.has(open.item.id)} onClose={closeDrawer} />
      )}

      {open?.type === 'kpi' && <ListDrawer list={kpiList(open.key)} onClose={closeDrawer} />}

      {open?.type === 'notice' && (
        <NoticeDrawer label={open.label} notice={open.notice} onClose={closeDrawer} />
      )}
    </section>
  )
}
