import { useEffect, useRef, type ReactNode } from 'react'

import styles from './Popover.module.scss'

interface PopoverProps {
  open: boolean
  onClose: () => void
  /** 팝오버를 여는 버튼. 열고 닫는 상태는 호출부가 갖습니다. */
  trigger: ReactNode
  /** 트리거의 왼쪽 끝에 맞출지 오른쪽 끝에 맞출지 */
  align?: 'start' | 'end'
  label: string
  children: ReactNode
}

export default function Popover({
  open,
  onClose,
  trigger,
  align = 'start',
  label,
  children,
}: PopoverProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onClose()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      onClose()
      // 닫은 뒤 포커스가 문서 맨 위로 튀지 않도록 트리거로 되돌립니다.
      triggerRef.current?.querySelector('button')?.focus()
    }

    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open, onClose])

  return (
    <div className={styles.root} ref={rootRef}>
      <div ref={triggerRef}>{trigger}</div>

      {open && (
        <div
          className={`${styles.panel} ${align === 'end' ? styles.alignEnd : ''}`}
          role="dialog"
          aria-label={label}
        >
          {children}
        </div>
      )}
    </div>
  )
}
