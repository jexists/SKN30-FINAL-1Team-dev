// 날짜와 시각을 한 칸에서 받습니다.
//
// 네이티브 date/time 입력은 브라우저가 최소 폭을 정해 버려 520px 모달 안에서
// 잘렸습니다. 여기서는 표시 형식을 우리가 정하므로 좁은 칸에도 온전히 들어갑니다.
import DatePicker, { registerLocale } from 'react-datepicker'
import { ko } from 'date-fns/locale'

import 'react-datepicker/dist/react-datepicker.css'

import styles from './DateTimePicker.module.scss'

registerLocale('ko', ko)

interface Props {
  selected: Date
  onChange: (date: Date | null) => void
  /** 화면 낭독기가 읽을 이름 */
  label: string
  minDate?: Date
  maxDate?: Date
  invalid?: boolean
}

export default function DateTimePicker({
  selected,
  onChange,
  label,
  minDate,
  maxDate,
  invalid = false,
}: Props) {
  // 열린 달력은 DatePicker 의 형제로 붙습니다. 이 감싸개가 없으면 그 달력이
  // 폼 그리드의 칸 하나를 차지해 다음 입력을 아래 줄로 밀어냅니다.
  return (
    <div className={styles.cell}>
      <DatePicker
        selected={selected}
        onChange={onChange}
        minDate={minDate}
        maxDate={maxDate}
        showTimeSelect
        timeIntervals={10}
        timeCaption="시각"
        locale="ko"
        dateFormat="M월 d일 (EEE) a h:mm"
        // date-fns 의 ko 로케일은 달 제목을 '8월 2026' 으로 냅니다. 우리말 차례로 뒤집습니다.
        dateFormatCalendar="yyyy년 M월"
        customInput={
          <input
            aria-label={label}
            aria-invalid={invalid || undefined}
            className={`${styles.input} ${invalid ? styles.isInvalid : ''}`}
          />
        }
        popperPlacement="bottom-start"
        // 모달이 overflow: hidden 이라, 아래쪽에서 열린 달력이 잘리지 않게 띄웁니다.
        popperProps={{ strategy: 'fixed' }}
      />
    </div>
  )
}
