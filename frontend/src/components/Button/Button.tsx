import type { ButtonHTMLAttributes, ReactNode } from 'react'

import styles from './Button.module.scss'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  variant?: 'primary' | 'outline' | 'ghost'
}

export default function Button({ children, variant = 'primary', className, ...rest }: ButtonProps) {
  // className 을 뒤에 붙여 호출부가 여백·폭 정도는 조정할 수 있게 합니다.
  return (
    <button
      className={[styles.root, styles[variant], className].filter(Boolean).join(' ')}
      {...rest}
    >
      {children}
    </button>
  )
}
