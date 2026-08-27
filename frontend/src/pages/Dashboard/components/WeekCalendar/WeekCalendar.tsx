import Button from '@/components/Button'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import WeekStrip from '@/components/WeekStrip'
import type { WeeklyBand } from '@/types'
import { addDays, iso, weekRangeLabel } from '@/utils/date'

import { weekStart } from '../../useDashboard'

import styles from './WeekCalendar.module.scss'

interface Props {
  /** 날짜별 건수. 아직 받아 오지 않은 주의 점도 맞게 찍히도록 서버가 셉니다. */
  weekly: WeeklyBand
  weekOffset: number
  selectedISO: string
  onSelect: (dateISO: string) => void
  onWeekChange: (offset: number) => void
  onToday: () => void
}

/**
 * 한 칸에 세우는 표식의 최대 개수. 일곱 칸으로 나눈 폭이라 이보다 늘리면
 * 점이 붙어 몇 개인지 세지지 않습니다.
 *
 * 넘치는 날은 표식 하나를 덜어 그 자리에 '+N' 을 세웁니다. 다섯 개에서 잘라
 * 두면 여섯 개인 날과 열 개인 날이 똑같이 보여, 바쁜 날을 알아볼 수 없습니다.
 */
const MAX_MARKS = 5

const rangeDays = (offset: number) =>
  Array.from({ length: 7 }, (_, i) => addDays(weekStart(offset), i))

export default function WeekCalendar({
  weekly,
  weekOffset,
  selectedISO,
  onSelect,
  onWeekChange,
  onToday,
}: Props) {
  const days = rangeDays(weekOffset)
  const countByDate = new Map(weekly.days.map((day) => [day.date, day]))

  // 선택 칸은 배경이 파랗게 차므로 점 색을 뒤집습니다.
  const renderMarks = (dateISO: string, isSelected: boolean) => {
    // 점은 아래 하루 목록과 같은 것을 셉니다. 칸이 말해 주는 것은 "그날 몇 건인가"
    // 하나입니다.
    const total = countByDate.get(dateISO)?.activity_count ?? 0
    // 넘치는 날은 '+N' 이 한 자리를 가져갑니다.
    const shown = Math.min(total, total > MAX_MARKS ? MAX_MARKS - 1 : MAX_MARKS)
    const hidden = total - shown

    return (
      <>
        {Array.from({ length: shown }, (_, i) => (
          <i key={i} className={`${styles.dot} ${isSelected ? styles.isOnBlue : ''}`} />
        ))}
        {hidden > 0 && (
          <span className={`${styles.more} ${isSelected ? styles.isOnBlue : ''} tnum`}>
            +{hidden}
          </span>
        )}
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
          <Button
            variant="outline"
            iconOnly
            onClick={() => onWeekChange(weekOffset - 1)}
            aria-label="이전 주"
          >
            <ChevronLeftIcon width={15} height={15} />
          </Button>
          <Button variant="ghost" onClick={onToday}>
            오늘
          </Button>
          <Button
            variant="outline"
            iconOnly
            onClick={() => onWeekChange(weekOffset + 1)}
            aria-label="다음 주"
          >
            <ChevronRightIcon width={15} height={15} />
          </Button>
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
