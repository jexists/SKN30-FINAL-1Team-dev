import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react'

import Button from '@/components/Button'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import type { CalendarEvent } from '@/types'
import {
  addDays,
  addMonths,
  fmtDay,
  iso,
  monthMatrix,
  parseISO,
  startOfMonth,
  TODAY,
  TODAY_ISO,
  WD,
  fmtMonth,
} from '@/utils/date'

import type { Dragging } from '../../dragging'
import DayCell, { type Ghost } from '../DayCell'

import styles from './MonthGrid.module.scss'

interface Props {
  /** 지금 보고 있는 달. 1일로 정규화된 값입니다. */
  cursor: Date
  selectedISO: string
  eventsByDate: Map<string, CalendarEvent[]>
  deliveriesByDate: Map<string, number>
  /** 추천 카드에 올려 둔 동안 미리 보여 줄 자리. 없으면 null 입니다. */
  ghost: Ghost | null
  /** 방금 추가되어 한 번 강조할 일정 */
  justAddedId: string | null
  /** 지금 끌고 있는 것 */
  dragging: Dragging | null
  /** 지금 놓으려는 날짜 */
  dropISO: string | null
  onCursorChange: (next: Date) => void
  onSelect: (dateISO: string) => void
  onOpenEvent: (event: CalendarEvent) => void
  onCreate: (dateISO: string) => void
  onGrabEvent: (pointer: ReactPointerEvent, event: CalendarEvent) => void
}

export default function MonthGrid({
  cursor,
  selectedISO,
  eventsByDate,
  deliveriesByDate,
  ghost,
  justAddedId,
  dragging,
  dropISO,
  onCursorChange,
  onSelect,
  onOpenEvent,
  onCreate,
  onGrabEvent,
}: Props) {
  const days = monthMatrix(cursor)
  const month = cursor.getMonth()
  const keys = days.map(iso)

  // 다른 달로 넘어가 선택한 날이 화면에서 사라지면 탭으로 들어올 칸이 없어집니다.
  // 그럴 때는 보이는 달의 1일을 대신 탭 대상으로 둡니다.
  const focusISO = keys.includes(selectedISO) ? selectedISO : iso(startOfMonth(cursor))

  const focusCell = (dateISO: string) => {
    requestAnimationFrame(() => {
      document.querySelector<HTMLButtonElement>(`[data-iso="${dateISO}"]`)?.focus()
    })
  }

  const goto = (dateISO: string) => {
    onSelect(dateISO)
    const date = parseISO(dateISO)
    // 보이는 42칸을 벗어나면 달을 따라 넘깁니다.
    if (!keys.includes(dateISO)) onCursorChange(startOfMonth(date))
    focusCell(dateISO)
  }

  const STEP: Record<string, number> = {
    ArrowLeft: -1,
    ArrowRight: 1,
    ArrowUp: -7,
    ArrowDown: 7,
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = STEP[event.key]
    if (step === undefined) return
    event.preventDefault()
    goto(iso(addDays(parseISO(focusISO), step)))
  }

  const changeMonth = (delta: number) => {
    const next = addMonths(cursor, delta)
    onCursorChange(next)
    focusCell(iso(next))
  }

  const goToday = () => {
    onCursorChange(startOfMonth(TODAY))
    goto(TODAY_ISO)
  }

  return (
    <article className={styles.grid}>
      <header className={styles.head}>
        <div className={styles.nav}>
          <Button variant="outline" iconOnly onClick={() => changeMonth(-1)} aria-label="이전 달">
            <ChevronLeftIcon width={15} height={15} />
          </Button>
          <h2 className={`${styles.month} tnum`} aria-live="polite">
            {fmtMonth(cursor)}
          </h2>
          <Button variant="outline" iconOnly onClick={() => changeMonth(1)} aria-label="다음 달">
            <ChevronRightIcon width={15} height={15} />
          </Button>
        </div>

        <div className={styles.tools}>
          <span className={styles.legend}>
            <span>
              <i className={styles.dotMeeting} /> 미팅
            </span>
            <span>
              <i className={styles.dotDelivery} /> 업무
            </span>
          </span>
          <Button variant="ghost" onClick={goToday}>
            오늘
          </Button>
          {/* 폰에서는 칸 안 + 버튼이 들어갈 폭이 없어 여기로 옮겨 둡니다. */}
          <Button className={styles.createOnPhone} onClick={() => onCreate(selectedISO)}>
            일정 등록
          </Button>
        </div>
      </header>

      <div className={styles.weekdays} aria-hidden="true">
        {WD.map((w, i) => (
          <span key={w} className={i === 0 ? styles.isSun : i === 6 ? styles.isSat : undefined}>
            {w}
          </span>
        ))}
      </div>

      <div className={styles.cells} role="grid" aria-label="월간 일정" onKeyDown={onKeyDown}>
        {Array.from({ length: 6 }, (_, week) => (
          // 행은 display:contents 라 7열 그리드를 그대로 통과합니다.
          <div key={week} className={styles.row} role="row">
            {days.slice(week * 7, week * 7 + 7).map((date) => {
              const key = iso(date)
              return (
                <DayCell
                  key={key}
                  date={date}
                  dateISO={key}
                  isOther={date.getMonth() !== month}
                  isToday={key === TODAY_ISO}
                  isSelected={key === selectedISO}
                  tabbable={key === focusISO}
                  label={fmtDay(date)}
                  events={eventsByDate.get(key) ?? []}
                  deliveries={deliveriesByDate.get(key) ?? 0}
                  ghost={ghost?.date === key ? ghost : null}
                  justAddedId={justAddedId}
                  dragging={dragging}
                  isDropTarget={dropISO === key}
                  onSelect={onSelect}
                  onOpenEvent={onOpenEvent}
                  onCreate={onCreate}
                  onGrabEvent={onGrabEvent}
                />
              )
            })}
          </div>
        ))}
      </div>
    </article>
  )
}
