import { useEffect, useId, useRef, type ReactNode } from 'react'

import { CloseIcon } from '@/components/icons'

import styles from './Modal.module.scss'

/**
 * 열려 있는 모달들. 일정 모달 위에 고객 등록 모달을 얹는 것처럼 두 장이 겹치면,
 * Escape 한 번에 둘 다 닫히고 안쪽 스크림을 눌러도 바깥 핸들러까지 올라갑니다
 * (portal 로 꺼내도 React 이벤트는 컴포넌트 트리를 탑니다). 맨 위의 것만 답합니다.
 */
const stack: symbol[] = []

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
  const token = useRef(Symbol('modal')).current
  const isTop = () => stack[stack.length - 1] === token

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
    stack.push(token)

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && stack[stack.length - 1] === token) onCloseRef.current()
    }
    document.addEventListener('keydown', onKeyDown)

    const previousOverflow = document.body.style.overflow
    const previouslyFocused = document.activeElement as HTMLElement | null
    document.body.style.overflow = 'hidden'

    return () => {
      stack.splice(stack.indexOf(token), 1)
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
      previouslyFocused?.focus()
    }
  }, [token])

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
