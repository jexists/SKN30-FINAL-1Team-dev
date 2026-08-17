import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { createPortal } from 'react-dom'

import type { BoardDeal } from '../../board'
import { fmtDotShort, parseISO } from '@/utils/date'
import { won } from '@/utils/format'

import styles from './DealCard.module.scss'

interface Props {
  deal: BoardDeal
  /** 실제 API에서는 UUID, 목업에서는 deal.no 입니다. */
  identity?: string
  isDragging: boolean
  onOpen: (identity: string) => void
  onGrab: (event: ReactPointerEvent, deal: BoardDeal, identity: string) => void
  /** 키보드로 앞뒤 컬럼에 옮기기. 드래그를 못 쓰는 경우의 길입니다. */
  onNudge: (identity: string, delta: -1 | 1) => void
  onEdit: (identity: string) => void
  onDelete: (identity: string) => void
  readOnly?: boolean
}

export default function DealCard({
  deal,
  identity = deal.no,
  isDragging,
  onOpen,
  onGrab,
  onNudge,
  onEdit,
  onDelete,
  readOnly = false,
}: Props) {
  return (
    // ⋯ 는 카드 버튼 안에 못 둡니다. 버튼 안의 버튼은 만들 수 없어 형제로 두고
    // 카드 위에 겹칩니다.
    <div className={styles.wrap}>
      <button
        type="button"
        className={[styles.card, isDragging && styles.isDragging].filter(Boolean).join(' ')}
        aria-keyshortcuts={readOnly ? undefined : '[ ]'}
        onPointerDown={(event) => {
          if (!readOnly) onGrab(event, deal, identity)
        }}
        onClick={() => onOpen(identity)}
        onKeyDown={(event) => {
          if (readOnly || (event.key !== '[' && event.key !== ']')) return
          event.preventDefault()
          onNudge(identity, event.key === '[' ? -1 : 1)
        }}
      >
        <span className={styles.org}>{deal.org}</span>
        <span className={styles.product}>{deal.product}</span>

        <span className={styles.amount}>
          <span className="tnum">{won(deal.amount)}</span>
          <span className={styles.kind}>{deal.kind}</span>
        </span>

        <span className={styles.meta}>
          <span>{deal.owner}</span>
          <span className="tnum">{fmtDotShort(parseISO(deal.date))}</span>
        </span>
      </button>

      {!readOnly && (
        <CardMenu identity={identity} deal={deal} onEdit={onEdit} onDelete={onDelete} />
      )}
    </div>
  )
}

/** 열린 메뉴가 설 자리. 화면 기준입니다. */
interface MenuAt {
  top: number
  right: number
}

interface CardMenuProps {
  identity: string
  deal: BoardDeal
  onEdit: (identity: string) => void
  onDelete: (identity: string) => void
}

/**
 * 카드의 ⋯. 상세를 거치지 않고 바로 고치거나 지웁니다.
 *
 * 공용 Popover 를 쓰지 않습니다. 카드 목록이 스크롤 상자(.list 의 overflow-y)라
 * 그 안에 붙은 패널은 아래쪽 카드에서 잘립니다. body 로 내보내고 화면 좌표로
 * 세웁니다. 좌표는 열 때 한 번만 재므로 스크롤하면 자리가 어긋납니다. 따라다니게
 * 만들기보다 닫습니다.
 */
function CardMenu({ identity, deal, onEdit, onDelete }: CardMenuProps) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState<MenuAt | null>(null)

  const close = () => {
    setAt(null)
    triggerRef.current?.focus()
  }

  const open = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    setAt({ top: rect.bottom + 6, right: window.innerWidth - rect.right })
  }

  useEffect(() => {
    if (at === null) return

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (panelRef.current?.contains(target) || triggerRef.current?.contains(target)) return
      setAt(null)
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    const dismiss = () => setAt(null)

    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    // 캡처로 받아야 컬럼 목록처럼 안쪽에서 나는 스크롤도 잡힙니다.
    window.addEventListener('scroll', dismiss, true)
    window.addEventListener('resize', dismiss)

    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('scroll', dismiss, true)
      window.removeEventListener('resize', dismiss)
    }
  }, [at])

  useEffect(() => {
    if (at !== null) panelRef.current?.querySelector('button')?.focus()
  }, [at])

  const label = `${deal.org} ${deal.product} 영업 딜 관리`

  return (
    <div className={styles.menu}>
      <button
        ref={triggerRef}
        type="button"
        className={styles.trigger}
        aria-label={label}
        aria-expanded={at !== null}
        onClick={() => (at === null ? open() : setAt(null))}
      >
        ⋯
      </button>

      {at !== null &&
        createPortal(
          <div
            ref={panelRef}
            className={styles.panel}
            style={{ top: at.top, right: at.right }}
            role="dialog"
            aria-label={label}
          >
            <button
              type="button"
              className={styles.action}
              onClick={() => {
                setAt(null)
                onEdit(identity)
              }}
            >
              수정
            </button>
            <button
              type="button"
              className={`${styles.action} ${styles.danger}`}
              onClick={() => {
                setAt(null)
                onDelete(identity)
              }}
            >
              삭제
            </button>
          </div>,
          document.body,
        )}
    </div>
  )
}
