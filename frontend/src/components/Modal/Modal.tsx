import { useEffect, useId, useRef, type ReactNode } from 'react'

import { CloseIcon } from '@/components/icons'
import { pushOverlay } from '@/shared/overlayStack'
import { lockScroll } from '@/shared/scrollLock'

import styles from './Modal.module.scss'

const SIZE_CLASS: Record<'md' | 'lg', string> = {
  md: '',
  lg: styles.isLarge,
}

interface ModalProps {
  title: string
  description?: string
  onClose: () => void
  /** 하단 액션 영역. 버튼은 호출부가 넘깁니다. */
  footer?: ReactNode
  /** 폼 모달이면 다이얼로그 본문을 <form> 으로 감쌉니다. */
  onSubmit?: () => void
  size?: 'md' | 'lg'
  /**
   * 본문의 여백과 스크롤을 자식에게 넘길지. 좌우로 나눈 뒤 한쪽만 스크롤시키는
   * 화면처럼, 본문이 스크롤 영역을 스스로 정해야 할 때만 켭니다.
   */
  flushBody?: boolean
  children: ReactNode
}

export default function Modal({
  title,
  description,
  onClose,
  footer,
  onSubmit,
  size = 'md',
  flushBody = false,
  children,
}: ModalProps) {
  const bodyRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  // 겹쳐 있는 오버레이 중 맨 위인지. 아니면 Escape 와 스크림 클릭에 답하지 않습니다.
  const overlayRef = useRef<{ isTop: () => boolean; release: () => void } | null>(null)
  const isTop = () => overlayRef.current?.isTop() === true

  // 닫기 함수는 호출부에서 매 렌더 새로 만들어지는 일이 흔합니다. 그것을 아래
  // 효과의 의존성으로 두면 글자 하나 칠 때마다 효과가 풀렸다 다시 걸리고,
  // 정리 단계의 focus() 가 조합 중인 한글을 끊어 'ㅌㄷㄹ' 처럼 자모가 흩어집니다.
  // 그래서 최신 함수는 ref 로만 들고, 효과는 열고 닫을 때 한 번씩만 돕니다.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  // AppShell 의 드로어와 같은 처리입니다. Escape 로 닫고 뒤 배경은 스크롤을 멈춥니다.
  useEffect(() => {
    const overlay = pushOverlay()
    overlayRef.current = overlay

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && overlay.isTop()) onCloseRef.current()
    }
    document.addEventListener('keydown', onKeyDown)

    const previouslyFocused = document.activeElement as HTMLElement | null
    const unlockScroll = lockScroll()

    return () => {
      overlay.release()
      overlayRef.current = null
      document.removeEventListener('keydown', onKeyDown)
      unlockScroll()
      previouslyFocused?.focus()
    }
  }, [])

  // 열리면 첫 입력으로 바로 타이핑할 수 있게 포커스를 옮깁니다.
  useEffect(() => {
    const first = bodyRef.current?.querySelector<HTMLElement>(
      'input, select, textarea, button, [tabindex]:not([tabindex="-1"])',
    )
    first?.focus()
  }, [])

  const Wrapper = onSubmit ? 'form' : 'div'

  return (
    <div
      className={styles.scrim}
      onPointerDown={() => {
        if (isTop()) onClose()
      }}
    >
      {/* 스크림 클릭으로만 닫히도록 다이얼로그 안쪽 클릭은 여기서 멈춥니다. */}
      <div
        className={`${styles.dialog} ${SIZE_CLASS[size]}`}
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

          <div className={`${styles.body} ${flushBody ? styles.isFlush : ''}`} ref={bodyRef}>
            {children}
          </div>

          {footer && <footer className={styles.foot}>{footer}</footer>}
        </Wrapper>
      </div>
    </div>
  )
}
