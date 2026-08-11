import { useEffect, useState } from 'react'

import { ChevronDownIcon } from '@/components/icons'
import { notices } from '@/content/notices'
import useMediaQuery from '@/hooks/useMediaQuery'

import styles from './NoticeTicker.module.scss'

const ROLL_MS = 4000

export default function NoticeTicker() {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const reduceMotion = useMediaQuery('(prefers-reduced-motion: reduce)')

  // 읽고 있는 동안(hover/focus)과 모션을 줄인 환경에서는 넘기지 않습니다.
  useEffect(() => {
    if (paused || reduceMotion || notices.length < 2) return
    const timer = setInterval(() => setIndex((i) => (i + 1) % notices.length), ROLL_MS)
    return () => clearInterval(timer)
  }, [paused, reduceMotion])

  if (notices.length === 0) return null

  return (
    <section
      className={styles.notice}
      tabIndex={0}
      aria-label="팀 공지사항"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <span className={styles.badge}>공지</span>

      <div className={styles.viewport} aria-live="polite">
        <ul className={styles.track} style={{ '--i': index } as React.CSSProperties}>
          {notices.map((n) => (
            <li key={n.text}>
              <strong>{n.text}</strong> <em>· {n.author}</em>
            </li>
          ))}
        </ul>
      </div>

      <span className={`${styles.count} tnum`}>
        {index + 1} / {notices.length}
      </span>
      <ChevronDownIcon className={styles.caret} width={14} height={14} />

      <div className={styles.panel}>
        <ul>
          {notices.map((n) => (
            <li key={n.text}>
              <p>
                <strong>[{n.tag}]</strong> {n.text}
              </p>
              <small>
                {n.author} · {n.time}
              </small>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
