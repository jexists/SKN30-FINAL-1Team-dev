// 하루를 고르는 칸. 공지 게시기간과 작성 리스트 기간이 같은 것을 씁니다.
//
// 열린 달력은 DatePicker 의 형제로 붙습니다. 감싸개가 없으면 그 달력이 한 칸을
// 차지해 옆에 선 입력을 다음 줄로 밀어냅니다.
import DatePicker, { registerLocale } from 'react-datepicker'
import { ko } from 'date-fns/locale'

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
  isClearable?: boolean
  disabled?: boolean
  placeholderText?: string
  /**
   * 모달처럼 overflow 를 자르는 곳 안에서 열릴 때 켭니다. 켜지 않으면 아래쪽에서
   * 열린 달력이 잘립니다.
   */
  fixed?: boolean
  className?: string
}

export default function DayPicker({
  selected,
  onChange,
  label,
  minDate,
  maxDate,
  isClearable,
  disabled,
  placeholderText,
  fixed,
  className,
}: Props) {
  // 지우기가 켜지면 ✕ 가 입력 위에 겹쳐 뜹니다. 글자가 그 밑으로 들어가지 않게
  // 오른쪽 여백을 넓히는 표시를 겉에 둡니다.
  const root = [styles.root, isClearable && styles.isClearable, className].filter(Boolean).join(' ')

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
        dateFormat="yyyy-MM-dd"
        placeholderText={placeholderText}
        // date-fns 의 ko 로케일은 달 제목을 '8월 2026' 으로 냅니다. 우리말 차례로 뒤집습니다.
        dateFormatCalendar="yyyy년 M월"
        customInput={<input aria-label={label} className={styles.input} />}
        popperPlacement="bottom-start"
        popperProps={fixed ? { strategy: 'fixed' } : undefined}
      />
    </div>
  )
}
