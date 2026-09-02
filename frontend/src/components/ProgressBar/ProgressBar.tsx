// 진행 막대. 얼마나 남았는지 아는 구간은 채워진 길이로, 모르는 구간은 흐르는
// 띠로 알립니다.
//
// 모르는 구간까지 0% 막대로 세우면 "멈춰 있다" 로 읽힙니다. 그래서 값이 없을
// 때는 길이를 말하지 않고 움직임만 남깁니다.
import styles from './ProgressBar.module.scss'

interface Props {
  /** 0~100. 없으면 남은 양을 알 수 없는 구간입니다. */
  value?: number
  /** 화면 낭독기가 읽을 말. 눈에는 막대만 보입니다. */
  label: string
  className?: string
}

export default function ProgressBar({ value, label, className }: Props) {
  const determinate = typeof value === 'number'
  const percent = determinate ? Math.min(100, Math.max(0, Math.round(value))) : undefined

  return (
    <div
      className={[styles.track, determinate ? '' : styles.flowing, className]
        .filter(Boolean)
        .join(' ')}
      role="progressbar"
      aria-label={label}
      aria-valuenow={percent}
      aria-valuemin={determinate ? 0 : undefined}
      aria-valuemax={determinate ? 100 : undefined}
    >
      <span
        className={styles.fill}
        style={percent === undefined ? undefined : { width: `${percent}%` }}
      />
    </div>
  )
}
