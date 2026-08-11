import type { KeyboardEvent } from 'react'

import Button from '@/components/Button'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import { agendaFor } from '@/content/agenda'
import { orders } from '@/content/orders'
import { addDays, iso, parseISO, TODAY, TODAY_ISO, WD } from '@/utils/date'

import styles from './WeekCalendar.module.scss'

interface Props {
  weekOffset: number
  selectedISO: string
  onSelect: (dateISO: string) => void
  onWeekChange: (offset: number) => void
  onToday: () => void
}

// 오늘을 왼쪽에서 셋째 칸에 두어 지난 이틀과 앞으로의 나흘이 함께 보이게 합니다.
const rangeStart = (offset: number) => addDays(TODAY, -2 + offset * 7)
const rangeDays = (offset: number) =>
  Array.from({ length: 7 }, (_, i) => addDays(rangeStart(offset), i))

function rangeLabel(days: Date[]) {
  const [first] = days
  const last = days[6]
  return first.getMonth() === last.getMonth()
    ? `${first.getMonth() + 1}월 ${first.getDate()}일 – ${last.getDate()}일`
    : `${first.getMonth() + 1}월 ${first.getDate()}일 – ${last.getMonth() + 1}월 ${last.getDate()}일`
}

export default function WeekCalendar({
  weekOffset,
  selectedISO,
  onSelect,
  onWeekChange,
  onToday,
}: Props) {
  const days = rangeDays(weekOffset)

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()

    const step = event.key === 'ArrowRight' ? 1 : -1
    const next = iso(addDays(parseISO(selectedISO), step))

    // 보이는 주를 벗어나면 주를 따라 넘깁니다.
    if (!days.map(iso).includes(next)) onWeekChange(weekOffset + step)
    onSelect(next)

    // 렌더 후 새 셀로 포커스를 옮깁니다.
    requestAnimationFrame(() => {
      document.querySelector<HTMLButtonElement>(`[data-iso="${next}"]`)?.focus()
    })
  }

  return (
    <article className={styles.weekcal}>
      <div className={styles.head}>
        <div>
          <p className="eyebrow">Weekly plan</p>
          <p className={`${styles.range} tnum`}>{rangeLabel(days)}</p>
        </div>

        <div className={styles.tools}>
          <span className={styles.legend}>
            <span>
              <i className={styles.dotMeeting} /> 일정
            </span>
            <span>
              <i className={styles.dotDelivery} /> 납기
            </span>
          </span>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => onWeekChange(weekOffset - 1)}
            aria-label="이전 주"
          >
            <ChevronLeftIcon width={15} height={15} />
          </button>
          <Button variant="ghost" onClick={onToday}>
            오늘
          </Button>
          <button
            type="button"
            className={styles.iconBtn}
            onClick={() => onWeekChange(weekOffset + 1)}
            aria-label="다음 주"
          >
            <ChevronRightIcon width={15} height={15} />
          </button>
        </div>
      </div>

      <div className={styles.grid} role="tablist" aria-label="주간 일정" onKeyDown={onKeyDown}>
        {days.map((d) => {
          const key = iso(d)
          const dow = d.getDay()
          const isToday = key === TODAY_ISO
          const isSelected = key === selectedISO
          const meetings = agendaFor(key).length
          const deliveries = orders.filter((o) => o.expect === key).length

          const cls = [
            styles.day,
            isToday && styles.isToday,
            isSelected && styles.isSelected,
            dow === 0 && styles.isSun,
            dow === 6 && styles.isSat,
          ]
            .filter(Boolean)
            .join(' ')

          return (
            <button
              key={key}
              type="button"
              role="tab"
              className={cls}
              data-iso={key}
              aria-selected={isSelected}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => onSelect(key)}
            >
              <span className={styles.wd}>
                {WD[dow]}
                {isToday && <em className={styles.todayTag}> · 오늘</em>}
              </span>
              <span className={`${styles.num} tnum`}>{String(d.getDate()).padStart(2, '0')}</span>
              {d.getDate() === 1 && (
                <span className={`${styles.month} tnum`}>{d.getMonth() + 1}월</span>
              )}
              <span className={styles.dots}>
                {Array.from({ length: Math.min(meetings, 3) }, (_, i) => (
                  <i key={`m${i}`} className={styles.dotMeeting} />
                ))}
                {Array.from({ length: Math.min(deliveries, 2) }, (_, i) => (
                  <i key={`d${i}`} className={styles.dotDelivery} />
                ))}
              </span>
            </button>
          )
        })}
      </div>
    </article>
  )
}
