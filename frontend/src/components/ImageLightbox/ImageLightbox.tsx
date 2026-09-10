// 화면에 보이는 콘텐츠 이미지를 그 자리에서 크게 보는 오버레이입니다.
// 명함처럼 작게 눌러 놓은 사진을 새 탭으로 나가지 않고 앱 안에서 확인하려고 만들었습니다.
//
// 동작 규칙은 Modal / Drawer 와 맞춥니다. Escape 로 닫고 배경은 스크롤을 멈추며,
// 닫으면 눌렀던 자리로 포커스가 돌아갑니다. 다만 이 오버레이는 늘 그 둘 "위"에 뜨므로
// overlayStack 으로 자기가 꼭대기일 때만 답합니다.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import { CloseIcon } from '@/components/icons'
import { pushOverlay } from '@/shared/overlayStack'
import { lockScroll } from '@/shared/scrollLock'

import styles from './ImageLightbox.module.scss'

interface Props {
  src: string
  alt: string
  /** 이미지 아래 한 줄. 파일명·용량 같은 것. */
  caption?: ReactNode
  onClose: () => void
}

export default function ImageLightbox({ src, alt, caption, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const overlayRef = useRef<{ isTop: () => boolean; release: () => void } | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  // Modal 과 같은 이유로 최신 닫기 함수는 ref 로만 듭니다. 호출부가 매 렌더 새로 만드는
  // 함수를 의존성에 두면 효과가 풀렸다 다시 걸리며 스크롤 잠금과 포커스가 흔들립니다.
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    const overlay = pushOverlay()
    overlayRef.current = overlay

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && overlay.isTop()) onCloseRef.current()
    }
    document.addEventListener('keydown', onKeyDown)

    const previouslyFocused = document.activeElement as HTMLElement | null
    const unlockScroll = lockScroll()
    closeRef.current?.focus()

    return () => {
      overlay.release()
      overlayRef.current = null
      document.removeEventListener('keydown', onKeyDown)
      unlockScroll()
      previouslyFocused?.focus()
    }
  }, [])

  // 주소가 바뀌면 다시 여는 것과 같습니다. 앞 이미지의 성패를 물려받지 않게 되돌립니다.
  useEffect(() => {
    setStatus('loading')
  }, [src])

  return createPortal(
    <div
      className={styles.scrim}
      role="dialog"
      aria-modal="true"
      aria-label={alt}
      // portal 로 꺼내도 React 이벤트는 컴포넌트 트리를 타므로, 여기서 멈추지 않으면
      // 이 오버레이를 연 드로어·모달의 스크림까지 눌린 것으로 칩니다.
      onPointerDown={(event) => {
        event.stopPropagation()
        if (overlayRef.current?.isTop() === true) onClose()
      }}
    >
      <button
        ref={closeRef}
        type="button"
        className={styles.close}
        aria-label="닫기"
        onPointerDown={(event) => event.stopPropagation()}
        onClick={onClose}
      >
        <CloseIcon />
      </button>

      <figure className={styles.frame} onPointerDown={(event) => event.stopPropagation()}>
        {status === 'error' ? (
          <p className={styles.notice} role="alert">
            원본을 미리 볼 수 없습니다.
          </p>
        ) : (
          <>
            {status === 'loading' && <p className={styles.notice}>원본을 여는 중…</p>}
            <img
              className={styles.image}
              src={src}
              alt={alt}
              onLoad={() => setStatus('ready')}
              onError={() => setStatus('error')}
            />
          </>
        )}
        {caption && <figcaption className={styles.caption}>{caption}</figcaption>}
      </figure>
    </div>,
    document.body,
  )
}
