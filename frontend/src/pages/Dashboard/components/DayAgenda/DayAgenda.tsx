import { forwardRef } from 'react'

import Button from '@/components/Button'
import { CalendarIcon } from '@/components/icons'
import { agendaFor, statusScope } from '@/content/agenda'
import type { AgendaItem } from '@/content/types'
import useMeetingReports from '@/pages/Meetings/useMeetingReports'
import { fmtDay, parseISO, TODAY } from '@/utils/date'

import styles from './DayAgenda.module.scss'

interface Props {
  dateISO: string
  /**
   * 완료 표시한 일정 id. 메모리에만 있고 저장하지 않습니다.
   * 여기서는 읽기만 합니다. 완료로 바꾸는 것은 상세 드로어가 맡습니다.
   */
  doneIds: ReadonlySet<string>
  onOpen: (item: AgendaItem) => void
  onAddSchedule: () => void
  /** 오늘 방문 회사 타일이 이 카드로 스크롤할 때 잠깐 켜집니다. */
  flash?: boolean
}

const DAY = 86_400_000
const RELATIVE: Record<string, string> = { '-1': '어제', '0': '오늘', '1': '내일' }

const DayAgenda = forwardRef<HTMLElement, Props>(function DayAgenda(
  { dateISO, doneIds, onOpen, onAddSchedule, flash },
  ref,
) {
  const list = agendaFor(dateISO)
  // 보고서를 썼는지는 RecordDrawer 와 같은 곳을 봅니다. AgendaItem.reported 는
  // 목업 시드의 고정값이라 이 자리에서 쓴 기록을 따라오지 못합니다.
  const { findByAgenda } = useMeetingReports()
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
        <Button variant="outline" onClick={onAddSchedule}>
          일정 추가
        </Button>
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
            const reported = Boolean(findByAgenda(it.id))
            return (
              // 줄 어디를 눌러도 상세가 열립니다. 안쪽 버튼들은 각자 할 일이
              // 따로 있어 여기까지 올라오지 않게 막습니다.
              <article
                key={it.id}
                className={`${styles.item} ${done ? styles.isDone : ''}`}
                onClick={() => onOpen(it)}
              >
                <span className={styles.node} aria-hidden="true" />

                <div className={styles.rail}>
                  <span className={`${styles.time} tnum`}>{it.time}</span>
                </div>

                <div className={styles.body}>
                  <div className={styles.metaRow}>
                    <i
                      className={`${styles.pill} ${statusScope(it.stage) === '외부' ? styles.scopeExternal : ''}`}
                    >
                      {it.stage}
                    </i>
                    {/* 끝냈는지, 그리고 끝냈는데 보고를 아직 안 썼는지를 이어
                        붙입니다. 누르는 자리가 아니라 읽는 자리라 배지입니다. */}
                    {done && <i className={`${styles.pill} ${styles.doneTag}`}>완료</i>}
                    {done && !reported && (
                      <i className={`${styles.pill} ${styles.needsReport}`}>보고서 미작성</i>
                    )}
                  </div>

                  {/* 마우스는 줄 전체를 누르지만 키보드는 잡을 곳이 있어야 합니다.
                      회사 이름이 그 자리이고, 하는 일은 줄을 누른 것과 같습니다. */}
                  <h3 className={styles.org}>
                    <button
                      type="button"
                      className={styles.open}
                      onClick={(event) => {
                        event.stopPropagation()
                        onOpen(it)
                      }}
                    >
                      {it.hospital}
                    </button>
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
