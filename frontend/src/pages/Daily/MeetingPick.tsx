// 미팅 보고서를 쓰기 전에 날짜와 일정을 고르는 화면입니다.
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { buttonClass } from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import Skeleton from '@/components/Skeleton'
import WeekStrip from '@/components/WeekStrip'
import { dailyComposePath, ROUTES } from '@/constants/routes'
import { useMeetingReportsOn } from '@/pages/Meetings/useMeetingReports'
import { useAgendaState } from '@/shared/agenda'
import { addDays, iso, startOfWeek, TODAY, TODAY_ISO, weekRangeLabel } from '@/utils/date'

import { meetingLinkFor, type SourceMeta } from './sources'
import DailyListLink from './components/DailyListLink'

import styles from './MeetingPick.module.scss'

const LIST_H = 360
/** 표식 자리에 세울 수 있는 점 개수. 대시보드 주간 일정과 같습니다. */
const MAX_MARKS = 5
const FILTERS = ['전체', '미작성', '작성중', '확정'] as const
type Filter = (typeof FILTERS)[number]

/**
 * 목록 상태를 필터 세 갈래로 접습니다. 미팅 보고서는 팀장 확인 없이 작성자가 끝내므로
 * 제출('검토 대기')이 곧 확정이고, 반려는 다시 손봐야 하니 '작성중'입니다.
 */
const filterOf = (status: SourceMeta['status']): Filter =>
  status === null ? '미작성' : status === '확정' || status === '검토 대기' ? '확정' : '작성중'

const weekDays = (offset: number) => {
  const first = addDays(startOfWeek(TODAY), offset * 7)
  return Array.from({ length: 7 }, (_, index) => addDays(first, index))
}

const initialWeekOffset = (dateISO: string) => {
  const todayStart = startOfWeek(TODAY).getTime()
  return Math.round(
    (startOfWeek(new Date(`${dateISO}T00:00:00`)).getTime() - todayStart) / 604800000,
  )
}

export default function MeetingPick() {
  const [params, setParams] = useSearchParams()
  const asked = params.get('date') ?? TODAY_ISO
  const dateISO = asked > TODAY_ISO ? TODAY_ISO : asked
  const [weekOffset, setWeekOffset] = useState(() => initialWeekOffset(dateISO))
  const [filter, setFilter] = useState<Filter>('전체')
  const days = weekDays(weekOffset)

  // 주소의 날짜를 뒤로/앞으로 이동해도 그 날짜가 든 주를 계속 보여 줍니다.
  useEffect(() => {
    const next = initialWeekOffset(dateISO)
    setWeekOffset((current) => (current === next ? current : next))
  }, [dateISO])

  // 날짜 칸마다 그 날 일정이 몇 건인지 보여 주므로 하루가 아니라 보이는 주를 통째로
  // 받습니다. 고를 수 없는 미래 날짜는 셀 것도 없어 오늘까지만 묻습니다.
  const weekEnd = iso(days[6])
  const {
    items,
    loading: agendaLoading,
    error: agendaError,
    reload: reloadAgenda,
  } = useAgendaState(iso(days[0]), weekEnd > TODAY_ISO ? TODAY_ISO : weekEnd, true)
  const agenda = items.filter((item) => item.date === dateISO)
  const countByDate = useMemo(() => {
    const map = new Map<string, number>()
    for (const item of items) map.set(item.date, (map.get(item.date) ?? 0) + 1)
    return map
  }, [items])
  const {
    reports: meetings,
    loading: meetingLoading,
    error: meetingError,
    reload: reloadMeetings,
  } = useMeetingReportsOn(dateISO, { includeDrafts: true })

  const byAgenda = useMemo(() => {
    const grouped = new Map<string, typeof meetings>()
    for (const report of meetings) {
      const group = grouped.get(report.agendaId) ?? []
      group.push(report)
      grouped.set(report.agendaId, group)
    }
    return grouped
  }, [meetings])

  const rows = useMemo(
    () => agenda.map((item) => ({ item, link: meetingLinkFor(item.id, byAgenda.get(item.id)) })),
    [agenda, byAgenda],
  )
  const visible =
    filter === '전체' ? rows : rows.filter(({ link }) => filterOf(link.status) === filter)

  const changeDate = (next: string) => {
    if (next === '' || next > TODAY_ISO) return
    // 날짜가 바뀌면 이전 날짜에서 고른 상태 필터는 의미가 없습니다.
    setFilter('전체')
    const query = new URLSearchParams(params)
    query.set('date', next)
    setParams(query, { replace: true })
  }

  const changeWeek = (next: number) => {
    setWeekOffset(next)
    const first = weekDays(next)[0]
    if (iso(first) <= TODAY_ISO) changeDate(iso(first))
  }

  const onSelectDate = (next: string) => {
    changeDate(next)
    if (next < iso(days[0]) || next > iso(days[6])) setWeekOffset(initialWeekOffset(next))
  }

  const loading = agendaLoading || meetingLoading
  const error = agendaError ?? meetingError
  const canShowNextWeek = iso(weekDays(weekOffset + 1)[0]) <= TODAY_ISO

  return (
    <section className={styles.page} aria-busy={loading}>
      <h1 className="sr-only">미팅 보고서 작성</h1>

      <DailyListLink back tab="meeting" className={styles.back} />

      <article className={styles.calendar}>
        <div className={styles.calendarHead}>
          <p className={`${styles.range} tnum`}>{weekRangeLabel(days)}</p>
          <div className={styles.calendarTools}>
            <button type="button" onClick={() => changeWeek(weekOffset - 1)} aria-label="이전 주">
              <ChevronLeftIcon width={16} height={16} />
            </button>
            <button
              type="button"
              onClick={() => {
                setWeekOffset(0)
                changeDate(TODAY_ISO)
              }}
              disabled={weekOffset === 0 && dateISO === TODAY_ISO}
            >
              오늘
            </button>
            <button
              type="button"
              onClick={() => changeWeek(weekOffset + 1)}
              aria-label="다음 주"
              disabled={!canShowNextWeek}
            >
              <ChevronRightIcon width={16} height={16} />
            </button>
          </div>
        </div>

        <WeekStrip
          days={days}
          selectedISO={dateISO}
          onSelect={onSelectDate}
          onOutOfRange={(next) => setWeekOffset(initialWeekOffset(next))}
          renderMarks={(key) => {
            // 대시보드 주간 일정과 같은 읽기. 점 하나가 일정 하나이고, 넘치면 '+N'.
            const total = countByDate.get(key) ?? 0
            const shown = Math.min(total, total > MAX_MARKS ? MAX_MARKS - 1 : MAX_MARKS)
            const hidden = total - shown
            return (
              <>
                {Array.from({ length: shown }, (_, index) => (
                  <i key={index} aria-hidden="true" className={styles.markDot} />
                ))}
                {hidden > 0 && (
                  <span aria-hidden="true" className={`${styles.more} tnum`}>
                    +{hidden}
                  </span>
                )}
                <span className="sr-only">일정 {total}건</span>
              </>
            )
          }}
          label="미팅 보고서 날짜 선택"
          selectionStyle="outline"
          maxISO={TODAY_ISO}
        />
      </article>

      <div className={styles.filters} role="tablist" aria-label="미팅 보고서 상태">
        {FILTERS.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={filter === value}
            className={filter === value ? styles.isActive : ''}
            onClick={() => setFilter(value)}
          >
            {value}
          </button>
        ))}
      </div>

      <ErrorToast
        message={error}
        onRetry={() => {
          reloadAgenda()
          reloadMeetings()
        }}
      />

      {!error && loading && (
        <div role="status" className={styles.loading}>
          <span className="sr-only">일정과 보고서를 불러오는 중입니다.</span>
          <Skeleton height={LIST_H} radius="var(--r-lg)" />
        </div>
      )}

      {!loading &&
        !error &&
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
        ) : visible.length === 0 ? (
          <div className={styles.empty}>
            <p>{filter} 상태의 보고서가 없습니다.</p>
            <button type="button" onClick={() => setFilter('전체')}>
              전체 일정 보기
            </button>
          </div>
        ) : (
          <ol className={styles.timeline}>
            {visible.map(({ item, link }) => (
              <li key={item.id} className={styles.entry}>
                <Link
                  className={styles.card}
                  to={link.to ?? dailyComposePath(dateISO, '일일')}
                  aria-label={`${item.hospital || item.title} ${link.label}`}
                >
                  <span className={`${styles.time} tnum`}>{item.time}</span>
                  <div className={styles.content}>
                    <h2>{item.hospital || item.title}</h2>
                    {(item.dept || item.contact) && (
                      <p className={styles.who}>
                        {[item.dept, item.contact].filter(Boolean).join(' · ')}
                      </p>
                    )}
                    {item.hospital && <p className={styles.title}>{item.title}</p>}
                  </div>
                  <span className={styles.action}>
                    {link.label}
                    <ChevronRightIcon width={16} height={16} />
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        ))}
    </section>
  )
}
