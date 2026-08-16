import { forwardRef } from 'react'
import { Link } from 'react-router'

import Button from '@/components/Button'
import { CalendarIcon, CheckIcon } from '@/components/icons'
import { endTime, statusScope, useAgendaFor } from '@/shared/agenda'
import { useAgendaReportLink } from '@/shared/agendaReport'
import type { AgendaItem } from '@/types'
import { fmtDay, parseISO, TODAY } from '@/utils/date'

import styles from './DayAgenda.module.scss'

interface Props {
  dateISO: string
  /** 완료 표시한 일정 id. 메모리에만 있고 저장하지 않습니다. */
  doneIds: ReadonlySet<string>
  onToggleDone: (id: string) => void
  onOpen: (item: AgendaItem) => void
  onAddSchedule: () => void
  /** 오늘 방문 회사 타일이 이 카드로 스크롤할 때 잠깐 켜집니다. */
  flash?: boolean
}

const DAY = 86_400_000
const RELATIVE: Record<string, string> = { '-1': '어제', '0': '오늘', '1': '내일' }

const DayAgenda = forwardRef<HTMLElement, Props>(function DayAgenda(
  { dateISO, doneIds, onToggleDone, onOpen, onAddSchedule, flash },
  ref,
) {
  const list = useAgendaFor(dateISO)
  // 고객을 만나는 일과 사내에서 처리하는 일은 준비하는 것이 다릅니다. 미팅을
  // 먼저 훑고 그 아래에서 업무를 봅니다. 주간 줄의 파란 점·노란 점과 같은 구분입니다.
  const meetings = list.filter((it) => it.kind !== 'internal')
  const tasks = list.filter((it) => it.kind === 'internal')
  // 보고서로 가는 길은 RecordDrawer 와 같은 곳을 봅니다. AgendaItem.reported 는
  // 목업 시드의 고정값이라 이 자리에서 쓴 기록을 따라오지 못합니다.
  const reportLink = useAgendaReportLink()
  const date = parseISO(dateISO)
  const relative = RELATIVE[String(Math.round((date.getTime() - TODAY.getTime()) / DAY))]
  /** groupStart 는 업무 묶음의 첫 줄입니다. 미팅과의 경계를 선 하나로 긋습니다. */
  const renderItem = (it: AgendaItem, groupStart = false) => {
    const done = doneIds.has(it.id)
    const report = reportLink(it)
    // 업무는 고객이 없어 회사·담당자 자리가 비고, 대신 언제까지 어디서 하는지가 남습니다.
    const task = it.kind === 'internal'
    const until = task ? endTime(it.time, it.dur) : ''

    return (
      // 줄 어디를 눌러도 상세가 열립니다. 안쪽 버튼들은 각자 할 일이
      // 따로 있어 여기까지 올라오지 않게 막습니다.
      <article
        key={it.id}
        className={`${styles.item} ${done ? styles.isDone : ''} ${groupStart ? styles.groupStart : ''}`}
        onClick={() => onOpen(it)}
      >
        {/* 레일 위 첫 칸이 완료를 정하는 자리입니다. 목록을 훑다가
            바로 끝낼 수 있게 상세를 열지 않고 여기서 토글합니다. */}
        <button
          type="button"
          className={styles.doneBtn}
          aria-pressed={done}
          aria-label={done ? `${it.title} 완료 취소` : `${it.title} 완료로 표시`}
          onClick={(event) => {
            event.stopPropagation()
            onToggleDone(it.id)
          }}
        >
          {done && <CheckIcon width={13} height={13} />}
          완료
        </button>

        <div className={styles.rail}>
          <span className={`${styles.time} tnum`}>{it.time}</span>
          {until && <span className={`${styles.until} tnum`}>~{until}</span>}
        </div>

        <div className={styles.body}>
          <div className={styles.metaRow}>
            {task && <i className={styles.taskTag}>업무</i>}
            {it.stage && (
              <i
                className={`${styles.pill} ${statusScope(it.stage) === '외부' ? styles.scopeExternal : ''}`}
              >
                {it.stage}
              </i>
            )}
            {/* 끝냈다는 것은 왼쪽 버튼이 이미 말합니다. 여기서는 보고서를
                썼는지만 덧붙이는데, 그 자리를 배지 대신 링크가 맡습니다.
                '작성' 이라고 서 있는 것 자체가 아직 안 썼다는 뜻입니다.
                줄 전체는 상세를 열므로 링크에서 그 전파를 끊습니다. */}
            <Link
              className={styles.reportLink}
              to={report.to}
              onClick={(event) => event.stopPropagation()}
            >
              {report.label}
            </Link>
          </div>

          {/* 마우스는 줄 전체를 누르지만 키보드는 잡을 곳이 있어야 합니다.
              회사 이름이 그 자리이고, 하는 일은 줄을 누른 것과 같습니다.
              사내 업무는 회사가 없어 제목이 그 자리를, 장소가 담당자 자리를 대신합니다. */}
          <h3 className={styles.org}>
            <button
              type="button"
              className={styles.open}
              onClick={(event) => {
                event.stopPropagation()
                onOpen(it)
              }}
            >
              {it.hospital || it.title}
            </button>
            {task
              ? it.place && <span className={styles.who}>{it.place}</span>
              : (it.dept || it.contact) && (
                  <span className={styles.who}>
                    {[it.dept, it.contact].filter(Boolean).join(' · ')}
                  </span>
                )}
          </h3>

          {it.hospital && <p className={styles.title}>{it.title}</p>}
          {it.brief && <p className={styles.brief}>{it.brief}</p>}
        </div>
      </article>
    )
  }

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
          {meetings.map((it) => renderItem(it))}
          {tasks.map((it, i) => renderItem(it, i === 0))}
        </div>
      )}
    </article>
  )
})

export default DayAgenda
