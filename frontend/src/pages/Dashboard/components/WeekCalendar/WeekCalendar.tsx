import Button from '@/components/Button'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import WeekStrip from '@/components/WeekStrip'
import { agendaFor } from '@/shared/agenda'
import { orders } from '@/shared/orders'
import { addDays, iso, TODAY, weekRangeLabel } from '@/utils/date'

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

export default function WeekCalendar({
  weekOffset,
  selectedISO,
  onSelect,
  onWeekChange,
  onToday,
}: Props) {
  const days = rangeDays(weekOffset)

  // 선택 칸은 배경이 파랗게 차므로 점 색을 뒤집습니다.
  const renderMarks = (dateISO: string, isSelected: boolean) => {
    const meetings = agendaFor(dateISO).length
    const deliveries = orders.filter((o) => o.expect === dateISO).length
    const meetingCls = `${styles.dotMeeting} ${isSelected ? styles.isOnBlue : ''}`
    const deliveryCls = `${styles.dotDelivery} ${isSelected ? styles.isOnBlue : ''}`

    return (
      <>
        {Array.from({ length: Math.min(meetings, 3) }, (_, i) => (
          <i key={`m${i}`} className={meetingCls} />
        ))}
        {Array.from({ length: Math.min(deliveries, 2) }, (_, i) => (
          <i key={`d${i}`} className={deliveryCls} />
        ))}
      </>
    )
  }

  return (
    <article className={styles.weekcal}>
      <div className={styles.head}>
        <div>
          <p className={styles.eyebrow}>주간업무</p>
          <p className={`${styles.range} tnum`}>{weekRangeLabel(days)}</p>
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

      <div className={styles.strip}>
        <WeekStrip
          days={days}
          selectedISO={selectedISO}
          onSelect={onSelect}
          // 화살표로 보이는 주를 벗어나면 주를 따라 넘깁니다.
          onOutOfRange={(next) => onWeekChange(weekOffset + (iso(days[0]) > next ? -1 : 1))}
          renderMarks={renderMarks}
          label="주간 일정"
          notch
        />
      </div>
    </article>
  )
}
