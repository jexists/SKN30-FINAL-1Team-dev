import type { ComponentPropsWithRef, ReactNode } from 'react'

import { buttonClass, type ButtonSize, type ButtonVariant } from './buttonClass'

interface ButtonProps extends ComponentPropsWithRef<'button'> {
  children: ReactNode
  variant?: ButtonVariant
  size?: ButtonSize
  /** 아이콘만 든 정사각 버튼. 글자가 없으므로 aria-label 을 함께 넘기세요. */
  iconOnly?: boolean
}

export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  iconOnly = false,
  className,
  ...rest
}: ButtonProps) {
  // className 을 뒤에 붙여 호출부가 여백·폭 정도는 조정할 수 있게 합니다.
  return (
    <button className={buttonClass({ variant, size, iconOnly }, className)} {...rest}>
      {children}
    </button>
  )
}
