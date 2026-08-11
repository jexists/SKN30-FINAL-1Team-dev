import { useCallback, useRef, useState } from 'react'

import useMediaQuery from '@/hooks/useMediaQuery'
import { addDays, iso, TODAY, TODAY_ISO } from '@/utils/date'

import DayAgenda from './components/DayAgenda'
import NoticeTicker from './components/NoticeTicker'
import PurchaseOrders from './components/PurchaseOrders'
import SummaryBand from './components/SummaryBand'
import WeekCalendar from './components/WeekCalendar'

// 주간 캘린더는 오늘을 왼쪽에서 셋째 칸에 둡니다. 주를 옮기면 보이는 범위의
// 첫날을 고르게 해 선택이 화면 밖으로 나가지 않게 합니다.
const rangeStart = (offset: number) => addDays(TODAY, -2 + offset * 7)

const FLASH_MS = 1400

export default function Dashboard() {
  const [selectedISO, setSelectedISO] = useState(TODAY_ISO)
  const [weekOffset, setWeekOffset] = useState(0)
  const [doneIds, setDoneIds] = useState<ReadonlySet<string>>(new Set())
  const [flash, setFlash] = useState(false)

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

      <NoticeTicker />
      <SummaryBand onJumpToToday={jumpToToday} />

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
        flash={flash}
      />

      <PurchaseOrders />
    </section>
  )
}
