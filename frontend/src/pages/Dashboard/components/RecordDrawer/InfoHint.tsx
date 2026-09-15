import { useEffect, useState } from 'react'

import { InfoIcon } from '@/components/icons'

import styles from './RecordDrawer.module.scss'

/** 손을 뗀 뒤 말풍선이 남아 있는 시간입니다. */
const HIDE_DELAY = 3000

/**
 * 제목 옆에 붙는 부연 설명입니다.
 *
 * 한 번 읽으면 그만인 이야기라 물어볼 때만 폅니다. hover 와 키보드 포커스로 열고, 손을
 * 떼면 곧바로 지우지 않고 3초를 기다립니다 — 읽다 말고 마우스가 비켜난 것만으로 문장이
 * 사라지지 않도록 합니다. 다시 올려두는 동안에는 시간을 재지 않습니다.
 */
export default function InfoHint({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const [hovered, setHovered] = useState(false)

  useEffect(() => {
    if (!open || hovered) return

    const timer = window.setTimeout(() => setOpen(false), HIDE_DELAY)
    return () => window.clearTimeout(timer)
  }, [open, hovered])

  return (
    <span
      className={styles.hint}
      onMouseEnter={() => {
        setHovered(true)
        setOpen(true)
      }}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        className={styles.hintBtn}
        aria-label={text}
        // 드로어가 열릴 때 본문 첫 요소로 포커스가 넘어옵니다. 그냥 포커스로 열면
        // 아무도 묻지 않은 설명이 드로어를 열 때마다 떠 있습니다. 키보드로 짚어 온
        // 포커스(:focus-visible)일 때만 폅니다.
        onFocus={(event) => {
          if (event.target.matches(':focus-visible')) setOpen(true)
        }}
        onBlur={() => setOpen(false)}
      >
        <InfoIcon width={14} height={14} aria-hidden="true" />
      </button>
      <span className={`${styles.tip} ${open ? styles.tipOpen : ''}`} role="tooltip">
        {text}
      </span>
    </span>
  )
}
