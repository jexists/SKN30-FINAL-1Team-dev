// 하루치 목록 카드의 머리말. 날짜가 제목이고 오른쪽 끝에 그 카드가 할 일이 섭니다.
//
// 대시보드 하루 카드와 업무보고서 작성 화면이 같은 것을 보여 주므로 머리말도
// 하나만 둡니다. 다른 점은 날짜를 바꿀 수 있는지 하나뿐이라 그것만 선택으로 받습니다.
import { useRef, type ReactNode } from 'react'

import { ChevronDownIcon } from '@/components/icons'
import { fmtDay, parseISO, TODAY } from '@/utils/date'

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

export default function DayHeader({
  dateISO,
  onDateChange,
  maxISO,
  label,
  pickerType = 'date',
  children,
}: Props) {
  /** 날짜를 누르면 열리는 브라우저 달력. 입력칸 자체는 보이지 않습니다. */
  const pickerRef = useRef<HTMLInputElement>(null)
  const date = parseISO(dateISO)
  // 하루를 가리킬 때만 어제·오늘·내일이 뜻을 가집니다.
  const relative = label
    ? undefined
    : RELATIVE[String(Math.round((date.getTime() - TODAY.getTime()) / DAY))]
  const title = label ?? fmtDay(date)
  // 월 달력은 'YYYY-MM' 만 주고받습니다. 밖에서는 언제나 그 달 1일로 봅니다.
  const month = pickerType === 'month'

  return (
    <div className={styles.head}>
      <h2>
        {onDateChange ? (
          <button
            type="button"
            className={styles.dateBtn}
            onClick={() => {
              const el = pickerRef.current
              if (!el) return
              // showPicker 가 없는 브라우저에서는 입력칸을 잡아 주는 정도까지만 합니다.
              if (el.showPicker) el.showPicker()
              else el.focus()
            }}
          >
            {title}
            <ChevronDownIcon width={15} height={15} />
          </button>
        ) : (
          title
        )}

        {relative && (
          <i className={`${styles.pill} ${relative === '오늘' ? styles.now : ''}`}>{relative}</i>
        )}
      </h2>

      {children}

      {onDateChange && (
        <input
          ref={pickerRef}
          className={styles.picker}
          // 보이지 않는 칸이라 탭으로 걸리면 갈 곳 없는 정거장이 됩니다.
          tabIndex={-1}
          type={pickerType}
          aria-label={month ? '기준 월' : '기준 날짜'}
          value={month ? dateISO.slice(0, 7) : dateISO}
          max={month ? maxISO?.slice(0, 7) : maxISO}
          onChange={(event) => {
            const value = event.target.value
            if (value === '') return
            onDateChange(month ? `${value}-01` : value)
          }}
        />
      )}
    </div>
  )
}
