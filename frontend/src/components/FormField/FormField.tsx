// 라벨·입력·오류 한 줄. 폼마다 같은 모양이라 한 곳에 둡니다.
import type { ReactNode } from 'react'

import styles from './FormField.module.scss'

interface Props {
  label: string
  required?: boolean
  error?: string
  /** 두 칸 배치에서 한 줄을 다 쓰게 합니다. */
  wide?: boolean
  /**
   * label 로 감쌀지 여부. Select 처럼 버튼으로 여는 칸은 라벨 글자를 눌러도 함께
   * 눌리거나 포커스가 엉킵니다. 그런 칸은 false 로 두고 div 로 감쌉니다.
   */
  htmlFor?: boolean
  children: ReactNode
}

export default function FormField({
  label,
  required,
  error,
  wide,
  htmlFor = true,
  children,
}: Props) {
  const Wrapper = htmlFor ? 'label' : 'div'
  return (
    <Wrapper className={[styles.field, wide ? styles.isWide : ''].filter(Boolean).join(' ')}>
      <span className={styles.label}>
        {label}
        {required && <b aria-hidden="true">*</b>}
      </span>
      {children}
      {error && <span className={styles.error}>{error}</span>}
    </Wrapper>
  )
}
