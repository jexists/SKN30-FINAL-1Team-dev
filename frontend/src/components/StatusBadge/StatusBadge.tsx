import styles from './StatusBadge.module.scss'

/** 배지 색. neutral 은 tag-pill 기본색으로, 아직 아무 일도 일어나지 않은 상태에 씁니다. */
export type StatusTone = 'neutral' | 'blue' | 'orange' | 'green' | 'red'

interface Props {
  label: string
  tone?: StatusTone
}

const TONE: Record<StatusTone, string> = {
  neutral: '',
  blue: 'isBlue',
  orange: 'isOrange',
  green: 'isGreen',
  red: 'isRed',
}

export default function StatusBadge({ label, tone = 'neutral' }: Props) {
  const toneClass = TONE[tone]
  return (
    <span className={toneClass ? `${styles.badge} ${styles[toneClass]}` : styles.badge}>
      {label}
    </span>
  )
}
