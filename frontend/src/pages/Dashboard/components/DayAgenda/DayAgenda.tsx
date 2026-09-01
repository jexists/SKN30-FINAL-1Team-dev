import { forwardRef, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'

import Button from '@/components/Button'
import DayHeader from '@/components/DayHeader'
import { CalendarIcon, DailyReportIcon, EditIcon, MoreIcon, TrashIcon } from '@/components/icons'
import OwnerName from '@/components/OwnerName'
import Popover from '@/components/Popover'
import { InlineLoader } from '@/components/Skeleton'
import StatusBadge from '@/components/StatusBadge'
import { useCurrentUser } from '@/auth/sessionContext'
import { meetingComposePath, meetingReportPath } from '@/constants/routes'
import { useMeetingReportsOn } from '@/pages/Meetings/useMeetingReports'
import { isOwnAgendaItem, useAgendaFor } from '@/shared/agenda'
import { reviewLabel } from '@/shared/reviewDecision'
import { useShowOwner } from '@/shared/scope'
import type { AgendaItem } from '@/types'

import styles from './DayAgenda.module.scss'

interface Props {
  dateISO: string
  onOpen: (item: AgendaItem) => void
  /** 팀장이 보고서를 확인·검토하러 들어가는 자리. 팀원에게는 전달되지 않습니다. */
  onOpenReport?: (reportId: string) => void
  /** 값이 바뀌면 그 날 보고서를 다시 받아 배지를 새로 세웁니다. 검토가 끝난 뒤입니다. */
  reportsKey?: number
  onAddSchedule: () => void
  /** 줄 메뉴의 '수정'. 일정 폼을 엽니다. */
  onEdit: (item: AgendaItem) => void
  /** 줄 메뉴의 '삭제'. 지우기 전 한 번 더 묻는 것은 호출부가 맡습니다. */
  onDelete: (item: AgendaItem) => void
  /** 오늘 방문 거래처 타일이 이 카드로 스크롤할 때 잠깐 켜집니다. */
  flash?: boolean
}

const DayAgenda = forwardRef<HTMLElement, Props>(function DayAgenda(
  { dateISO, onOpen, onOpenReport, reportsKey, onAddSchedule, onEdit, onDelete, flash },
  ref,
) {
  const { items: list, loading } = useAgendaFor(dateISO)
  const showOwner = useShowOwner()
  const { memberId, isManager } = useCurrentUser()
  /** 메뉴를 펴 둔 줄. 한 번에 한 줄만 폅니다. */
  const [menuId, setMenuId] = useState<string | null>(null)
  // 미작성 줄에는 '보고서 작성', 초안이 있는 줄에는 '계속 작성' 을 세웁니다. 줄마다
  // 따로 물으면 요청이 늘어나므로 그 날 쓴 보고서를 한 번에 받아 일정 번호로 맞춥니다.
  const {
    reports,
    loading: reportsLoading,
    reload: reloadReports,
  } = useMeetingReportsOn(dateISO, {
    includeDrafts: true,
  })

  // 다시 받는 함수는 렌더마다 새로 만들어집니다. 그것을 아래 효과의 의존성으로 두면 효과가
  // 매 렌더 다시 돌고, 그 안의 setState 가 또 렌더를 부르는 고리가 생깁니다. Modal 의
  // onCloseRef 와 같은 까닭으로 최신 함수는 ref 로만 들고 효과는 열쇠만 봅니다.
  const reloadReportsRef = useRef(reloadReports)
  useEffect(() => {
    reloadReportsRef.current = reloadReports
  })

  // 검토가 끝나면 그 날 보고서만 다시 받습니다. 일정 목록은 바뀐 것이 없어 그대로 둡니다.
  useEffect(() => {
    if (reportsKey !== undefined && reportsKey > 0) reloadReportsRef.current()
  }, [reportsKey])

  // 이미 쓴 줄에는 '보고서 확인' 이 섭니다. 한 일정에 딜마다 보고서가 여러 건일 수
  // 있으므로 먼저 쓴 것을 세웁니다. 나머지는 상세에서 모두 볼 수 있습니다.
  const reportByAgenda = useMemo(() => {
    const found = new Map<string, (typeof reports)[number]>()
    for (const report of reports) {
      if (report.agendaId !== '' && !found.has(report.agendaId)) found.set(report.agendaId, report)
    }
    return found
  }, [reports])
  const renderItem = (it: AgendaItem) => {
    const done = it.done
    const report = reportByAgenda.get(it.id)
    const isOwn = isOwnAgendaItem(it, memberId, isManager)
    // 답을 받기 전에는 세우지 않습니다. 먼저 세웠다가 거두면 이미 쓴 줄에서 깜빡입니다.
    //
    // 내가 한 일에만 섭니다. 보고는 남이 한 일을 대신 적는 문서가 아니라서,
    // 팀 전체를 보고 있는 팀장에게도 팀원의 일정에는 이 길이 서지 않습니다.
    const needsReport = !reportsLoading && !report && isOwn
    const canContinue =
      !reportsLoading &&
      !!report &&
      report.ownerMemberId === memberId &&
      (report.apiStatus === 'draft' || report.apiStatus === 'changes_requested')
    const written = !reportsLoading && report?.apiStatus !== 'draft' ? report : undefined

    return (
      // 줄 어디를 눌러도 상세가 열립니다. 안쪽 버튼들은 각자 할 일이
      // 따로 있어 여기까지 올라오지 않게 막습니다.
      <article
        key={it.id}
        className={`${styles.item} ${done ? styles.isDone : ''}`}
        onClick={() => onOpen(it)}
      >
        <div className={styles.rail}>
          <span className={`${styles.time} tnum`}>{it.time}</span>
        </div>

        <div className={styles.body}>
          {/* 이 줄에 대고 할 수 있는 일을 오른쪽 끝에 모읍니다. 아직 안 쓴 보고서가
              앞에, 수정·삭제는 '...' 하나에 접어 그 뒤에 섭니다.
              줄 전체는 상세를 열므로 이 안의 클릭은 여기서 끊습니다. */}
          <div className={styles.actions} onClick={(event) => event.stopPropagation()}>
            {/* 미작성 또는 수정중인 보고서는 그 일정의 작성 화면으로 엽니다. */}
            {(needsReport || canContinue) && (
              <Link
                to={meetingComposePath(it.id)}
                className={styles.reportBtn}
                aria-label={`${it.title} 업무보고서 ${canContinue ? '계속 작성' : '작성'}`}
              >
                <DailyReportIcon width={13} height={13} />
                {canContinue ? '계속 작성' : '보고서 작성'}
              </Link>
            )}

            {/* 보고서가 있는 줄에는 상태 배지와 확인 길이 함께 섭니다.
                팀장은 여기서 바로 확정·반려하고, 팀원은 자기 보고서 상세로 갑니다. */}
            {written !== undefined && (
              <>
                <StatusBadge
                  label={reviewLabel(written.apiStatus ?? 'draft').label}
                  tone={reviewLabel(written.apiStatus ?? 'draft').tone}
                />
                {onOpenReport === undefined ? (
                  <Link
                    to={meetingReportPath(written.id)}
                    className={styles.reportBtn}
                    aria-label={`${it.title} 보고서 확인`}
                  >
                    <DailyReportIcon width={13} height={13} />
                    보고서 확인
                  </Link>
                ) : (
                  <button
                    type="button"
                    className={styles.reportBtn}
                    aria-label={`${it.title} 보고서 확인`}
                    onClick={() => onOpenReport(written.id)}
                  >
                    <DailyReportIcon width={13} height={13} />
                    보고서 확인
                  </button>
                )}
              </>
            )}

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
              {it.hospital || it.title}
            </button>
            {/* 여러 사람의 일정이 섞여 보일 때만 섭니다. 옆의 흐린 글씨는 고객 쪽
                부서·담당자라, 우리 쪽 사람은 다른 모양으로 세워 구분합니다. */}
            {showOwner && <OwnerName name={it.owner} />}
            {(it.dept || it.contact) && (
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
      <DayHeader dateISO={dateISO}>
        <Button variant="outline" onClick={onAddSchedule}>
          일정 추가
        </Button>
      </DayHeader>

      {/* 아직 받아 오는 중이면 '없음' 을 세우지 않습니다. 세웠다가 목록으로 바뀌면
          일정이 있는 날에도 없다는 문구가 한 번 스칩니다. */}
      {loading ? (
        <InlineLoader label="일정을 불러오는 중입니다." className={styles.loading} />
      ) : list.length === 0 ? (
        <div className={styles.empty}>
          <CalendarIcon width={34} height={34} strokeWidth={1.5} />
          <p>이 날짜에는 등록된 일정이 없습니다.</p>
        </div>
      ) : (
        <div className={styles.list}>{list.map((it) => renderItem(it))}</div>
      )}
    </article>
  )
})

export default DayAgenda
