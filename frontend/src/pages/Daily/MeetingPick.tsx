// 업무보고서를 쓰기 전에 기준 날짜와 일정을 고르는 화면입니다.
//
// 업무보고서는 일정 하나에 붙는 기록이라 빈 폼으로 열 수 없습니다. 그래서 종류를
// 고른 다음 바로 작성으로 보내지 않고 여기서 어느 일정인지 먼저 정합니다.
import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'

import { buttonClass } from '@/components/Button'
import DayHeader from '@/components/DayHeader'
import ErrorToast from '@/components/ErrorToast'
import { ChevronRightIcon } from '@/components/icons'
import Skeleton from '@/components/Skeleton'
import { dailyComposePath, ROUTES } from '@/constants/routes'
import { useAgendaState } from '@/shared/agenda'
import { useMeetingReportsOn } from '@/pages/Meetings/useMeetingReports'
import { TODAY_ISO } from '@/utils/date'

import DailyListLink from './components/DailyListLink'
import { meetingLinkFor } from './sources'

import styles from './MeetingPick.module.scss'

/** 목록을 기다리는 동안 잡아 두는 높이. 네 줄쯤 들어가는 자리입니다. */
const LIST_H = 240

export default function MeetingPick() {
  const [params, setParams] = useSearchParams()

  // 아직 오지 않은 날은 기록할 것이 없습니다. 주소를 직접 쳐도 오늘로 당깁니다.
  const asked = params.get('date') ?? TODAY_ISO
  const dateISO = asked > TODAY_ISO ? TODAY_ISO : asked

  const {
    items,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaState(dateISO, dateISO, true)
  const agenda = items.filter((item) => item.date === dateISO)
  // 이 날 것만 봅니다. 하루치라 한 쪽에 다 들어옵니다.
  const {
    reports: meetings,
    loading: meetingLoading,
    error: meetingError,
    reload: reloadMeetings,
  } = useMeetingReportsOn(dateISO)
  const byAgenda = useMemo(() => {
    const grouped = new Map<string, typeof meetings>()
    for (const report of meetings) {
      const group = grouped.get(report.agendaId) ?? []
      group.push(report)
      grouped.set(report.agendaId, group)
    }
    return grouped
  }, [meetings])
  const changeDate = (next: string) => {
    if (next === '' || next > TODAY_ISO) return
    const query = new URLSearchParams(params)
    query.set('date', next)
    setParams(query, { replace: true })
  }

  return (
    <section>
      <h1 className="sr-only">업무보고서 작성</h1>

      {/* 하루의 일정을 모두 고르는 화면이라 목록도 '전체' 로 엽니다. */}
      <DailyListLink back tab="meeting" className={styles.back} />

      <div className={styles.card}>
        {/* 날짜가 이 카드의 머리말입니다. 눌러 바꿀 수 있고 달력은 브라우저 것을 씁니다. */}
        <DayHeader dateISO={dateISO} maxISO={TODAY_ISO} onDateChange={changeDate} />

        <ErrorToast
          message={agendaError ?? meetingError}
          onRetry={() => {
            reloadAgenda()
            reloadMeetings()
          }}
        />
        {!agendaError && !meetingError && (agendaLoading || meetingLoading) && (
          <div role="status" className={styles.loading}>
            <span className="sr-only">일정과 보고서를 불러오는 중입니다.</span>
            <Skeleton height={LIST_H} radius="var(--r-lg)" />
          </div>
        )}

        {!agendaLoading &&
          !meetingLoading &&
          !agendaError &&
          !meetingError &&
          (agenda.length === 0 ? (
            <div className={styles.empty}>
              <p>이 날짜에 등록된 일정이 없습니다.</p>
              <Link
                className={buttonClass({ variant: 'outline' }, styles.emptyCta)}
                to={ROUTES.CALENDAR}
              >
                캘린더에서 일정 등록하기
                <ChevronRightIcon />
              </Link>
            </div>
          ) : (
            <ul className={styles.rows}>
              {agenda.map((item) => {
                const link = meetingLinkFor(item.id, byAgenda.get(item.id))

                return (
                  <li key={item.id}>
                    {/* 이 화면은 보고서를 쓰러 온 곳이라 줄 전체가 그 보고서로 가는 길입니다.
                        이미 쓴 줄은 같은 자리에서 그 보고서로 갑니다. */}
                    <Link
                      className={`${styles.row} ${item.done ? styles.isDone : ''}`}
                      to={link.to ?? dailyComposePath(dateISO, '일일')}
                      aria-label={`${item.hospital || item.title} ${link.label}`}
                    >
                      <div className={styles.rail}>
                        <span className={`${styles.time} tnum`}>{item.time}</span>
                      </div>

                      <div className={styles.body}>
                        <h3 className={styles.org}>
                          {item.hospital || item.title}
                          {(item.dept || item.contact) && (
                            <span className={styles.who}>
                              {[item.dept, item.contact].filter(Boolean).join(' · ')}
                            </span>
                          )}
                        </h3>

                        {item.hospital && <p className={styles.title}>{item.title}</p>}
                        {item.brief && <p className={styles.brief}>{item.brief}</p>}
                      </div>
                    </Link>
                  </li>
                )
              })}
            </ul>
          ))}
      </div>
    </section>
  )
}
