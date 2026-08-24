// 검색해서 고르는 입력들이 함께 쓰는 결과 목록입니다.
//
// 불러오는 중·실패·비어 있음을 여기서 답니다. 세 경우 모두 목록 자리에 그대로 뜨므로
// 입력칸 아래가 조용히 비어 있는 일이 없습니다.
import type { CSSProperties, ReactNode } from 'react'
import { createPortal } from 'react-dom'

import Button from '@/components/Button'

import styles from './ComboMenu.module.scss'

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
}: Props) {
  const settled = !loading && !loadError

  return createPortal(
    <div id={id} className={styles.menu} style={style} role="listbox" aria-label={label}>
      {loading && (
        <p className={styles.notice} role="status">
          {loadingText}
        </p>
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
      {settled && footer}
    </div>,
    document.body,
  )
}
