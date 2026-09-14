// 하루를 고르는 칸. 공지 게시기간과 작성 리스트 기간이 같은 것을 씁니다.
//
// 열린 달력은 DatePicker 의 형제로 붙습니다. 감싸개가 없으면 그 달력이 한 칸을
// 차지해 옆에 선 입력을 다음 줄로 밀어냅니다.
import { useRef, type ReactElement } from 'react'
import DatePicker, { registerLocale } from 'react-datepicker'
import { ko } from 'date-fns/locale'

import { TODAY } from '@/utils/date'

import 'react-datepicker/dist/react-datepicker.css'
import styles from './DayPicker.module.scss'

registerLocale('ko', ko)

interface Props {
  selected: Date | null
  onChange: (date: Date | null) => void
  /** 화면 낭독기가 읽을 이름. '노출 시작일'·'조회 시작일' 처럼 자리마다 다릅니다. */
  label: string
  minDate?: Date
  maxDate?: Date
  /** 하루가 아니라 달을 고릅니다. 날짜 격자 대신 1월~12월 격자가 열립니다. */
  month?: boolean
  isClearable?: boolean
  disabled?: boolean
  /** 아직 못 채운 필수 칸. form-field 가 aria-invalid 에 빨간 테두리를 그립니다. */
  invalid?: boolean
  /** 툴바가 아니라 폼의 세로 칸 안에 설 때 켭니다. 칸 너비를 꽉 채웁니다. */
  fill?: boolean
  placeholderText?: string
  /**
   * 모달처럼 overflow 를 자르는 곳 안에서 열릴 때 켭니다. 켜지 않으면 아래쪽에서
   * 열린 달력이 잘립니다.
   */
  fixed?: boolean
  /**
   * 기본 입력칸 대신 세울 것. 머리말처럼 글자가 곧 손잡이인 자리에서 씁니다.
   * 라이브러리가 onClick·ref 를 꽂아 주므로 그 둘을 받는 요소여야 합니다.
   */
  customInput?: ReactElement
  className?: string
}

export default function DayPicker({
  selected,
  onChange,
  label,
  minDate,
  maxDate,
  month,
  isClearable,
  disabled,
  invalid,
  fill,
  placeholderText,
  fixed,
  customInput,
  className,
}: Props) {
  // 지우기가 켜지면 ✕ 가 입력 위에 겹쳐 뜹니다. 글자가 그 밑으로 들어가지 않게
  // 오른쪽 여백을 넓히는 표시를 겉에 둡니다.
  const root = [styles.root, fill && styles.fill, isClearable && styles.isClearable, className]
    .filter(Boolean)
    .join(' ')

  // 지금으로 돌아오는 길. 값은 그대로 두고 달력이 보는 자리만 옮깁니다.
  //
  // 라이브러리의 오늘 버튼은 누르면 오늘을 골라 버리고 minDate·maxDate 도 보지
  // 않습니다. 그래서 그 감싸개의 클릭이 위로 올라가지 못하게 막고(stopPropagation)
  // 우리가 뷰만 옮깁니다. 감싸개가 div 라 키보드가 닿지 않으므로 안에 진짜 button
  // 을 넣습니다. 갈 곳에 고를 것이 없으면(오늘이 범위 밖) 아예 내놓지 않습니다.
  const pickerRef = useRef<DatePicker>(null)
  const todayReachable = (!minDate || TODAY >= minDate) && (!maxDate || TODAY <= maxDate)

  return (
    <div className={root}>
      <DatePicker
        selected={selected}
        onChange={onChange}
        minDate={minDate}
        maxDate={maxDate}
        isClearable={isClearable}
        disabled={disabled}
        locale="ko"
        showMonthYearPicker={month}
        dateFormat={month ? 'yyyy년 M월' : 'yyyy-MM-dd'}
        placeholderText={placeholderText}
        // date-fns 의 ko 로케일은 달 제목을 '8월 2026' 으로 냅니다. 우리말 차례로 뒤집습니다.
        dateFormatCalendar="yyyy년 M월"
        customInput={
          customInput ?? (
            <input
              aria-label={label}
              aria-invalid={invalid || undefined}
              className={styles.input}
            />
          )
        }
        ref={pickerRef}
        todayButton={
          todayReachable ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation()
                pickerRef.current?.setPreSelection(TODAY)
              }}
            >
              오늘
            </button>
          ) : undefined
        }
        popperPlacement="bottom-start"
        popperProps={fixed ? { strategy: 'fixed' } : undefined}
      />
    </div>
  )
}
