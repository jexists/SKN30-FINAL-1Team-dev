// 검색해서 고르는 입력들이 함께 쓰는 결과 목록입니다.
//
// 불러오는 중·실패·비어 있음을 여기서 답니다. 세 경우 모두 목록 자리에 그대로 뜨므로
// 입력칸 아래가 조용히 비어 있는 일이 없습니다.
import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import Button from '@/components/Button'
import Skeleton from '@/components/Skeleton'

import styles from './ComboMenu.module.scss'

/** 목록 한 줄의 높이. combo-option 믹스인의 여백 + 글자 높이입니다. */
const OPTION_H = 33

interface Props {
  id: string
  /** 화면 낭독기가 읽을 목록 이름 */
  label: string
  style?: CSSProperties
  loading: boolean
  loadingText: string
  loadError: string | null
  onRetry: () => void
  /** 고를 것이 하나도 없는지 */
  empty: boolean
  emptyText: string
  children?: ReactNode
  /** 목록 아래에 늘 붙는 줄. 검색 결과와 상관없이 보입니다. */
  footer?: ReactNode
  /** 아직 못 받은 쪽이 남았는지. 참이면 끝까지 스크롤할 때 onReachEnd 가 불립니다. */
  hasMore?: boolean
  loadingMore?: boolean
  onReachEnd?: () => void
}

export default function ComboMenu({
  id,
  label,
  style,
  loading,
  loadingText,
  loadError,
  onRetry,
  empty,
  emptyText,
  children,
  footer,
  hasMore = false,
  loadingMore = false,
  onReachEnd,
}: Props) {
  const settled = !loading && !loadError
  const menuRef = useRef<HTMLDivElement>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  // onReachEnd 는 호출부에서 매 렌더 새로 만들어질 수 있습니다. 관찰자를 다시 붙이지
  // 않도록 최신 것만 들고 있습니다.
  const reachEnd = useRef(onReachEnd)
  reachEnd.current = onReachEnd

  // 목록 끝이 보이면 다음 쪽을 부릅니다. 스크롤 이벤트를 세지 않아 붙였다 떼기만 하면
  // 됩니다. root 가 메뉴라 화면이 아니라 메뉴 안쪽 스크롤을 봅니다.
  useEffect(() => {
    const sentinel = sentinelRef.current
    const root = menuRef.current
    if (!settled || !hasMore || sentinel === null || root === null) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) reachEnd.current?.()
      },
      { root, rootMargin: '80px' },
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [settled, hasMore, children])

  return createPortal(
    <div
      ref={menuRef}
      id={id}
      className={styles.menu}
      style={style}
      role="listbox"
      aria-label={label}
    >
      {/* 후보 줄을 하나씩 흉내 내지 않습니다. 목록 자리 한 덩어리면 무엇이 들어올지
          충분히 읽히고, 좁은 메뉴에서 잔 막대가 겹치는 일도 없습니다. */}
      {loading && (
        <div role="status">
          <span className="sr-only">{loadingText}</span>
          <Skeleton height={OPTION_H * 3} radius="7px" />
        </div>
      )}

      {!loading && loadError && (
        <div className={styles.failure} role="alert">
          <span>{loadError}</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            // 목록은 입력칸 밖에 있어, 누르는 순간 포커스가 빠지면 클릭이 닿기 전에 닫힙니다.
            onMouseDown={(event) => event.preventDefault()}
            onClick={onRetry}
          >
            다시 시도
          </Button>
        </div>
      )}

      {settled && empty && <p className={styles.notice}>{emptyText}</p>}
      {settled && children}

      {settled && hasMore && (
        <div ref={sentinelRef} className={styles.sentinel} aria-hidden>
          {loadingMore && <Skeleton height={OPTION_H} radius="7px" />}
        </div>
      )}

      {settled && footer}
    </div>,
    document.body,
  )
}
