import type { ReactNode } from 'react'

import styles from './StatusBadge.module.scss'

/** 배지 색. neutral 은 tag-pill 기본색으로, 아직 아무 일도 일어나지 않은 상태에 씁니다. */
export type StatusTone = 'neutral' | 'blue' | 'orange' | 'green' | 'red'

interface Props {
  label: string
  tone?: StatusTone
  /** 글자 앞에 서는 표시. 상태를 한 번 더 말해야 하는 머리 띠에서만 씁니다. */
  icon?: ReactNode
}

const TONE: Record<StatusTone, string> = {
  neutral: '',
  blue: 'isBlue',
  orange: 'isOrange',
  green: 'isGreen',
  red: 'isRed',
}

export default function StatusBadge({ label, tone = 'neutral', icon }: Props) {
  const toneClass = TONE[tone]
  return (
    <span className={toneClass ? `${styles.badge} ${styles[toneClass]}` : styles.badge}>
      {icon}
      {label}
    </span>
  )
}
