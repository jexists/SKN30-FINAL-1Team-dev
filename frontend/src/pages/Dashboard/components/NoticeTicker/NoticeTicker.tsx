import { useEffect, useState } from 'react'

import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import { notices as defaultNotices, postedLabel } from '@/shared/notices'
import type { Notice } from '@/types'
import useMediaQuery from '@/hooks/useMediaQuery'

import styles from './NoticeTicker.module.scss'

const ROLL_MS = 6000
/** 한 화면에 보여 주는 줄 수. 넘치면 다음 페이지로 넘깁니다. */
const PAGE_SIZE = 3

interface Props {
  /** 카드 머리에 찍히는 이름 */
  label?: string
  items?: Notice[]
  /** 줄을 누르면 전문을 펼칩니다. 목록은 한 줄로 잘려 있어 여기가 상세로 가는 유일한 길입니다. */
  onOpen: (notice: Notice) => void
}

export default function NoticeTicker({
  label = '공지',
  items: notices = defaultNotices,
  onOpen,
}: Props) {
  const [page, setPage] = useState(0)
  const [paused, setPaused] = useState(false)
  const reduceMotion = useMediaQuery('(prefers-reduced-motion: reduce)')

  const pageCount = Math.max(1, Math.ceil(notices.length / PAGE_SIZE))

  // 읽고 있는 동안(hover/focus)과 모션을 줄인 환경에서는 넘기지 않습니다.
  useEffect(() => {
    if (paused || reduceMotion || pageCount < 2) return
    const timer = setInterval(() => setPage((p) => (p + 1) % pageCount), ROLL_MS)
    return () => clearInterval(timer)
  }, [paused, reduceMotion, pageCount])

  if (notices.length === 0) return null

  const current = notices.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)
  const move = (step: number) => setPage((p) => (p + step + pageCount) % pageCount)

  return (
    <section
      className={styles.notice}
      aria-label={label}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <header className={styles.head}>
        <span className={styles.label}>{label}</span>

        {pageCount > 1 && (
          <div className={styles.nav}>
            <button type="button" onClick={() => move(-1)} aria-label={`${label} 이전`}>
              <ChevronLeftIcon width={14} height={14} />
            </button>
            <span className={styles.count}>
              {page + 1} / {pageCount}
            </span>
            <button type="button" onClick={() => move(1)} aria-label={`${label} 다음`}>
              <ChevronRightIcon width={14} height={14} />
            </button>
          </div>
        )}
      </header>

      <ul className={styles.list} aria-live="polite">
        {current.map((n) => (
          <li key={n.text}>
            <button type="button" onClick={() => onOpen(n)}>
              <p>{n.text}</p>
              <small>{postedLabel(n)}</small>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
