// 라벨·입력·오류 한 줄. 폼마다 같은 모양이라 한 곳에 둡니다.
import type { ReactNode } from 'react'

import styles from './FormField.module.scss'

interface Props {
  label: string
  required?: boolean
  error?: string
  /** 두 칸 배치에서 한 줄을 다 쓰게 합니다. */
  wide?: boolean
  children: ReactNode
}

export default function FormField({ label, required, error, wide, children }: Props) {
  return (
    <label className={[styles.field, wide ? styles.isWide : ''].filter(Boolean).join(' ')}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </label>
  )
}
