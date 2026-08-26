import { forwardRef, useState } from 'react'
import { Link } from 'react-router'

import Button from '@/components/Button'
import {
  CalendarIcon,
  CheckIcon,
  DailyReportIcon,
  EditIcon,
  MoreIcon,
  TrashIcon,
} from '@/components/icons'
import Popover from '@/components/Popover'
import { InlineLoader } from '@/components/Skeleton'
import { endTime, statusScope, useAgendaFor } from '@/shared/agenda'
import { useAgendaReportLink } from '@/shared/agendaReport'
import type { AgendaItem } from '@/types'
import { fmtDay, parseISO, TODAY } from '@/utils/date'

import styles from './DayAgenda.module.scss'

interface Props {
  dateISO: string
  onToggleDone: (item: AgendaItem) => void
  onOpen: (item: AgendaItem) => void
  onAddSchedule: () => void
  /** 줄 메뉴의 '수정'. 일정 폼을 엽니다. */
  onEdit: (item: AgendaItem) => void
  /** 줄 메뉴의 '삭제'. 지우기 전 한 번 더 묻는 것은 호출부가 맡습니다. */
  onDelete: (item: AgendaItem) => void
  /** 오늘 방문 회사 타일이 이 카드로 스크롤할 때 잠깐 켜집니다. */
  flash?: boolean
}

const DAY = 86_400_000
const RELATIVE: Record<string, string> = { '-1': '어제', '0': '오늘', '1': '내일' }

const DayAgenda = forwardRef<HTMLElement, Props>(function DayAgenda(
  { dateISO, onToggleDone, onOpen, onAddSchedule, onEdit, onDelete, flash },
  ref,
) {
  const list = useAgendaFor(dateISO)
  /** 메뉴를 펴 둔 줄. 한 번에 한 줄만 폅니다. */
  const [menuId, setMenuId] = useState<string | null>(null)
  // 고객을 만나는 일과 사내에서 처리하는 일은 준비하는 것이 다릅니다. 미팅을
  // 먼저 훑고 그 아래에서 업무를 봅니다. 주간 줄의 파란 점·노란 점과 같은 구분입니다.
  const meetings = list.filter((it) => it.kind !== 'internal')
  const tasks = list.filter((it) => it.kind === 'internal')
  // 보고서로 가는 길은 RecordDrawer 와 같은 곳을 봅니다. AgendaItem.reported 는
  // 목업 시드의 고정값이라 이 자리에서 쓴 기록을 따라오지 못합니다.
  // 이 길은 펴 둔 메뉴 안에만 서므로 메뉴를 열 때 그 줄만 물어봅니다.
  const reportState = useAgendaReportLink(list.find((it) => it.id === menuId) ?? null)
  const date = parseISO(dateISO)
  const relative = RELATIVE[String(Math.round((date.getTime() - TODAY.getTime()) / DAY))]
  /** groupStart 는 업무 묶음의 첫 줄입니다. 미팅과의 경계를 선 하나로 긋습니다. */
  const renderItem = (it: AgendaItem, groupStart = false) => {
    const done = it.done
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
            onToggleDone(it)
          }}
        >
          {done && <CheckIcon width={13} height={13} />}
          {done ? '완료' : '미완료'}
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
            {/* 이 줄에 대고 할 수 있는 일을 배지 줄 끝의 '...' 하나로 모읍니다.
                보고서·수정·삭제가 각자 버튼으로 서면 줄마다 세 개가 늘어서
                정작 읽어야 할 회사와 제목보다 먼저 보입니다.
                줄 전체는 상세를 열므로 메뉴 안의 클릭은 여기서 끊습니다. */}
            <div className={styles.menuWrap} onClick={(event) => event.stopPropagation()}>
              <Popover
                open={menuId === it.id}
                onClose={() => setMenuId(null)}
                align="end"
                compact
                label={`${it.title} 일정 메뉴`}
                trigger={
                  <button
                    type="button"
                    className={styles.menuBtn}
                    aria-label={`${it.title} 일정 메뉴`}
                    aria-expanded={menuId === it.id}
                    onClick={() => setMenuId((prev) => (prev === it.id ? null : it.id))}
                  >
                    <MoreIcon width={17} height={17} />
                  </button>
                }
              >
                <div className={styles.menu}>
                  {/* '작성' 이라고 서 있으면 아직 안 쓴 것, '열기' 면 이미 쓴 것입니다.
                      메뉴를 연 뒤에 물어보므로 답을 받기 전까지는 이 자리가 비어 있습니다. */}
                  {reportState.error ? (
                    <button type="button" onClick={reportState.reload}>
                      <DailyReportIcon width={15} height={15} />
                      보고서 다시 조회
                    </button>
                  ) : reportState.link ? (
                    <Link to={reportState.link.to} onClick={() => setMenuId(null)}>
                      <DailyReportIcon width={15} height={15} />
                      {reportState.link.label}
                    </Link>
                  ) : (
                    <InlineLoader label="보고서 연결을 확인하는 중입니다." />
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setMenuId(null)
                      onEdit(it)
                    }}
                  >
                    <EditIcon width={15} height={15} />
                    수정
                  </button>
                  <button
                    type="button"
                    className={styles.danger}
                    onClick={() => {
                      setMenuId(null)
                      onDelete(it)
                    }}
                  >
                    <TrashIcon width={15} height={15} />
                    삭제
                  </button>
                </div>
              </Popover>
            </div>
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
