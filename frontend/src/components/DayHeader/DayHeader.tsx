// 하루치 목록 카드의 머리말. 날짜가 제목이고 오른쪽 끝에 그 카드가 할 일이 섭니다.
//
// 대시보드 하루 카드와 업무보고서 작성 화면이 같은 것을 보여 주므로 머리말도
// 하나만 둡니다. 다른 점은 날짜를 바꿀 수 있는지 하나뿐이라 그것만 선택으로 받습니다.
import { forwardRef, type ReactNode } from 'react'

import DayPicker from '@/components/DayPicker'
import { ChevronDownIcon } from '@/components/icons'
import { fmtDay, parseISO, startOfMonth, toDate, toISO, TODAY } from '@/utils/date'

import styles from './DayHeader.module.scss'

interface Props {
  dateISO: string
  /** 주면 날짜가 버튼이 되어 누를 때 달력이 열립니다. 안 주면 글자만 섭니다. */
  onDateChange?: (nextISO: string) => void
  /** 달력에서 고를 수 있는 마지막 날 */
  maxISO?: string
  /**
   * 날짜 대신 세울 글자. 주간·월간처럼 덮는 것이 하루가 아닐 때 씁니다.
   * 이때는 어제·오늘·내일 알약을 달지 않습니다 — 하루가 아닌 기간에는 뜻이 없습니다.
   */
  label?: string
  /** 눌렀을 때 열리는 달력의 종류. 월간은 'month' 입니다. */
  pickerType?: 'date' | 'month'
  /** 머리말 오른쪽 끝에 서는 것 (대시보드는 '일정 추가' 버튼) */
  children?: ReactNode
}

const DAY = 86_400_000
const RELATIVE: Record<string, string> = { '-1': '어제', '0': '오늘', '1': '내일' }

/**
 * 달력을 여는 제목. react-datepicker 는 customInput 에 value·onChange 까지 함께
 * 꽂지만 버튼은 글자를 밖에서 받으므로 여는 손잡이(onClick)와 달력이 설 자리(ref)만
 * 씁니다.
 */
const DateTrigger = forwardRef<HTMLButtonElement, { onClick?: () => void; children?: ReactNode }>(
  function DateTrigger({ onClick, children }, ref) {
    return (
      <button type="button" ref={ref} className={styles.dateBtn} onClick={onClick}>
        {children}
      </button>
    )
  },
)

export default function DayHeader({
  dateISO,
  onDateChange,
  maxISO,
  label,
  pickerType = 'date',
  children,
}: Props) {
  const date = parseISO(dateISO)
  // 하루를 가리킬 때만 어제·오늘·내일이 뜻을 가집니다.
  const relative = label
    ? undefined
    : RELATIVE[String(Math.round((date.getTime() - TODAY.getTime()) / DAY))]
  const title = label ?? fmtDay(date)
  const month = pickerType === 'month'

  return (
    <div className={styles.head}>
      <h2>
        {onDateChange ? (
          <DayPicker
            className={styles.dateCell}
            label={month ? '기준 월' : '기준 날짜'}
            month={month}
            // 작성 화면의 자료 열은 overflow 를 자릅니다. 달력이 그 안에서 잘리지 않게 합니다.
            fixed
            selected={date}
            maxDate={maxISO ? (toDate(maxISO) ?? undefined) : undefined}
            // 월 달력은 고른 달에 지금 고른 날의 일(日)을 얹어 돌려줍니다. 밖에서는
            // 월간을 언제나 그 달 1일로 보므로 여기서 못 박습니다.
            onChange={(next) => next && onDateChange(toISO(month ? startOfMonth(next) : next))}
            customInput={
              <DateTrigger>
                {title}
                <ChevronDownIcon width={15} height={15} />
              </DateTrigger>
            }
          />
        ) : (
          title
        )}

        {relative && (
          <i className={`${styles.pill} ${relative === '오늘' ? styles.now : ''}`}>{relative}</i>
        )}
      </h2>

      {children}
    </div>
  )
}
