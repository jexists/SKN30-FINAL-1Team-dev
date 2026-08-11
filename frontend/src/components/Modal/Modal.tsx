import { useEffect, useId, useRef, type ReactNode } from 'react'

import { CloseIcon } from '@/components/icons'

import styles from './Modal.module.scss'

interface ModalProps {
  title: string
  description?: string
  onClose: () => void
  /** 하단 액션 영역. 버튼은 호출부가 넘깁니다. */
  footer?: ReactNode
  /** 폼 모달이면 다이얼로그 본문을 <form> 으로 감쌉니다. */
  onSubmit?: () => void
  size?: 'md' | 'lg'
  children: ReactNode
}

export default function Modal({
  title,
  description,
  onClose,
  footer,
  onSubmit,
  size = 'md',
  children,
}: ModalProps) {
  const bodyRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  // AppShell 의 드로어와 같은 처리입니다. Escape 로 닫고 뒤 배경은 스크롤을 멈춥니다.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    const previousOverflow = document.body.style.overflow
    const previouslyFocused = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus()
    }
  }, [onClose])

  // 열리면 첫 입력으로 바로 타이핑할 수 있게 포커스를 옮깁니다.
  useEffect(() => {
    const first = bodyRef.current?.querySelector<HTMLElement>(
      'input, select, textarea, button, [tabindex]:not([tabindex="-1"])',
    )
    first?.focus()
  }, [])

  const Wrapper = onSubmit ? 'form' : 'div'

  return (
    <div className={styles.scrim} onPointerDown={onClose}>
      {/* 스크림 클릭으로만 닫히도록 다이얼로그 안쪽 클릭은 여기서 멈춥니다. */}
      <div
        className={`${styles.dialog} ${size === 'lg' ? styles.isLarge : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <Wrapper
          className={styles.form}
          // 브라우저 기본 검사는 막습니다. 문구가 브라우저 언어를 따르고,
          // 우리가 만든 오류 메시지가 아예 뜨지 못하게 가로챕니다.
          noValidate={onSubmit ? true : undefined}
          onSubmit={
            onSubmit
              ? (event: React.FormEvent) => {
                  event.preventDefault()
                  onSubmit()
                }
              : undefined
          }
        >
          <header className={styles.head}>
            <div>
              <h2 id={titleId}>{title}</h2>
              {description && <p className={styles.desc}>{description}</p>}
            </div>
            <button type="button" className={styles.close} onClick={onClose} aria-label="닫기">
              <CloseIcon />
            </button>
          </header>

          <div className={styles.body} ref={bodyRef}>
            {children}
          </div>

          {footer && <footer className={styles.foot}>{footer}</footer>}
        </Wrapper>
      </div>
    </div>
  )
}
