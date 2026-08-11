import { forwardRef } from 'react'

import { CalendarIcon } from '@/components/icons'
import { agendaFor, KIND_LABEL } from '@/content/agenda'
import type { AgendaKind } from '@/content/types'
import { fmtDay, parseISO, TODAY } from '@/utils/date'

import styles from './DayAgenda.module.scss'

interface Props {
  dateISO: string
  /** 완료 표시한 일정 id. 메모리에만 있고 저장하지 않습니다. */
  doneIds: ReadonlySet<string>
  onToggleDone: (id: string) => void
  /** 오늘 방문 회사 타일이 이 카드로 스크롤할 때 잠깐 켜집니다. */
  flash?: boolean
}

const KIND_TONE: Partial<Record<AgendaKind, string>> = {
  visit: styles.kindBlue,
  demo: styles.kindPurple,
  booth: styles.kindPurple,
  edu: styles.kindGreen,
  delivery: styles.kindOrange,
}

const DAY = 86_400_000
const RELATIVE: Record<string, string> = { '-1': '어제', '0': '오늘', '1': '내일' }

const DayAgenda = forwardRef<HTMLElement, Props>(function DayAgenda(
  { dateISO, doneIds, onToggleDone, flash },
  ref,
) {
  const list = agendaFor(dateISO)
  const date = parseISO(dateISO)
  const relative = RELATIVE[String(Math.round((date.getTime() - TODAY.getTime()) / DAY))]

  return (
    <article ref={ref} className={`${styles.agenda} ${flash ? styles.isFlash : ''}`}>
      <div className={styles.head}>
        <h2>
          {fmtDay(date)}
          {relative && (
            <i className={`${styles.pill} ${relative === '오늘' ? styles.now : ''}`}>{relative}</i>
          )}
        </h2>
      </div>

      {list.length === 0 ? (
        <div className={styles.empty}>
          <CalendarIcon width={34} height={34} strokeWidth={1.5} />
          <p>이 날짜에는 등록된 일정이 없습니다.</p>
        </div>
      ) : (
        <div className={styles.list}>
          {list.map((it) => {
            const done = doneIds.has(it.id)
            return (
              <article key={it.id} className={`${styles.item} ${done ? styles.isDone : ''}`}>
                <button
                  type="button"
                  className={styles.check}
                  aria-pressed={done}
                  aria-label={`${it.hospital} ${it.title} 완료 표시`}
                  onClick={() => onToggleDone(it.id)}
                >
                  <svg
                    width="13"
                    height="13"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </button>

                <div className={styles.rail}>
                  <span className={`${styles.time} tnum`}>{it.time}</span>
                </div>

                <div className={styles.body}>
                  <div className={styles.metaRow}>
                    <span className={`${styles.kind} ${KIND_TONE[it.kind] ?? ''}`}>
                      {KIND_LABEL[it.kind]}
                    </span>
                    <i className={styles.pill}>{it.stage}</i>
                    {it.tags.map((t) => (
                      <i key={t} className={styles.pill}>
                        {t}
                      </i>
                    ))}
                  </div>

                  <h3 className={styles.org}>
                    {it.hospital}
                    <span className={styles.who}>
                      {it.dept} · {it.contact}
                    </span>
                  </h3>

                  <p className={styles.title}>{it.title}</p>
                  <p className={styles.brief}>{it.brief}</p>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </article>
  )
})

export default DayAgenda
