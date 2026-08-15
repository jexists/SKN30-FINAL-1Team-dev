// demo/layout_v3.html §14 의 .drawer 입니다.
// 상세는 전부 오른쪽 드로어로 엽니다. 목록을 화면에 남겨 둔 채로 볼 수 있고,
// 히스토리처럼 세로로 긴 내용을 담을 자리가 나옵니다. 모달은 확인용으로 남깁니다.
//
// 동작은 ContractDrawer / ReportDrawer 와 같습니다. Escape 로 닫고 배경은
// 스크롤을 멈추며, 닫으면 눌렀던 자리로 포커스가 돌아갑니다.
import { useEffect, useId, useRef, type ReactNode } from 'react'

import { CloseIcon } from '@/components/icons'

import styles from './Drawer.module.scss'

interface Props {
  title: string
  /** 제목 아래 한 줄 */
  sub?: ReactNode
  /** 제목 아래 배지 줄 */
  meta?: ReactNode
  /** layout_v3 의 .is-wide. 2열로 나눠 담을 내용이 있을 때만 씁니다. */
  wide?: boolean
  /** 닫기 버튼 왼쪽에 붙는 것. 상세의 '수정·삭제' 메뉴가 여기 옵니다. */
  actions?: ReactNode
  /** 머리말과 본문 사이에 고정으로 붙는 줄. 목록 드로어의 필터 칩이 여기 옵니다. */
  filters?: ReactNode
  footer?: ReactNode
  /** 값이 바뀌면 본문 스크롤을 맨 위로 되돌립니다. 필터를 갈아탈 때 씁니다. */
  resetKey?: string
  onClose: () => void
  children: ReactNode
}

export default function Drawer({
  title,
  sub,
  meta,
  wide,
  actions,
  filters,
  footer,
  resetKey,
  onClose,
  children,
}: Props) {
  const panelRef = useRef<HTMLElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

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

  // 본문에 누를 것이 없는 드로어(값만 늘어놓은 상세)도 있습니다.
  // 그럴 때는 패널 자체를 잡아 두어야 포커스가 드로어 밖에 남지 않습니다.
  useEffect(() => {
    const first = bodyRef.current?.querySelector<HTMLElement>(
      'a, button, [tabindex]:not([tabindex="-1"])',
    )
    ;(first ?? panelRef.current)?.focus()
  }, [])

  // 내용만 갈아 끼우면 스크롤이 남습니다. 새 목록은 항상 첫 줄부터 보여야 합니다.
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = 0
  }, [resetKey])

  return (
    <div className={styles.scrim} onPointerDown={onClose}>
      <aside
        ref={panelRef}
        className={`${styles.panel} ${wide ? styles.wide : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <header className={styles.head}>
          <div className={styles.heading}>
            <h2 id={titleId}>{title}</h2>
            {sub && <p className={styles.sub}>{sub}</p>}
            {meta && <div className={styles.meta}>{meta}</div>}
          </div>
          <div className={styles.tools}>
            {actions}
            <button type="button" className={styles.close} onClick={onClose} aria-label="닫기">
              <CloseIcon />
            </button>
          </div>
        </header>

        {filters && <div className={styles.filters}>{filters}</div>}

        <div className={styles.body} ref={bodyRef}>
          {children}
        </div>

        {footer && <div className={styles.foot}>{footer}</div>}
      </aside>
    </div>
  )
}
