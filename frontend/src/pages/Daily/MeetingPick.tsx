// 미팅/업무보고서를 쓰기 전에 기준 날짜와 일정을 고르는 화면입니다.
//
// 미팅보고서는 일정 하나에 붙는 기록이라 빈 폼으로 열 수 없습니다. 그래서 종류를
// 고른 다음 바로 작성으로 보내지 않고 여기서 어느 일정인지 먼저 정합니다.
//
// 사내 업무는 일정마다 보고서를 따로 내지 않습니다. 그날 하루를 묶는 일일업무보고로
// 보내되 그 업무가 미리 체크된 채로 열리게 합니다.
import { Link, useSearchParams } from 'react-router'

import { buttonClass } from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import { ChevronRightIcon } from '@/components/icons'
import Skeleton from '@/components/Skeleton'
import { dailyComposePath, dailyReportPath, ROUTES } from '@/constants/routes'
import { KIND_LABEL, useAgendaState } from '@/shared/agenda'
import useMeetingReports from '@/pages/Meetings/useMeetingReports'
import { fmtDot, parseISO, TODAY_ISO } from '@/utils/date'

import DailyListLink from './components/DailyListLink'
import ReportStatusBadge from './components/ReportStatusBadge'
import { meetingLinkFor, type SourceMeta } from './sources'
import useDailyReports from './useDailyReports'

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
  const {
    findByAgenda,
    loading: meetingLoading,
    error: meetingError,
    reload: reloadMeetings,
  } = useMeetingReports()
  const {
    findByDate,
    loading: dailyLoading,
    error: dailyError,
    reload: reloadDaily,
  } = useDailyReports()

  /**
   * 사내 업무가 가는 곳. 단건 보고서를 만들지 않고 그날 일일업무보고로 묶습니다.
   * 이미 제출한 날이면 그 보고서를, 아니면 이 업무가 체크된 작성 화면을 엽니다.
   */
  const internalLink = (agendaId: string): SourceMeta => {
    const daily = findByDate(dateISO, '일일')
    const status = daily?.status ?? null
    if (daily && (status === '검토 대기' || status === '확정')) {
      return { status, to: dailyReportPath(daily.id), label: '일일업무보고서 열기' }
    }
    return {
      status,
      to: dailyComposePath(dateISO, '일일', agendaId),
      label:
        status === '반려'
          ? '수정하기'
          : status === '작성중'
            ? '이어서 작성'
            : '일일업무보고서에서 작성',
    }
  }

  const changeDate = (next: string) => {
    if (next === '' || next > TODAY_ISO) return
    const query = new URLSearchParams(params)
    query.set('date', next)
    setParams(query, { replace: true })
  }

  return (
    <section>
      <h1 className="sr-only">미팅/업무보고서 작성</h1>

      <header className={styles.head}>
        <h2 className={styles.title}>미팅/업무보고서 작성</h2>

        <label className={styles.dateField}>
          <span>기준 날짜</span>
          <input
            type="date"
            value={dateISO}
            max={TODAY_ISO}
            onChange={(event) => changeDate(event.target.value)}
          />
        </label>

        {/* 미팅과 사내 업무를 함께 고르는 화면이라 목록도 '전체' 로 엽니다. */}
        <DailyListLink />
      </header>

      <p className={styles.note}>
        {fmtDot(parseISO(dateISO))}의 미팅과 사내 업무입니다. 기록할 일정을 고르세요.
      </p>

      <ErrorToast
        message={agendaError ?? meetingError ?? dailyError}
        onRetry={() => {
          reloadAgenda()
          reloadMeetings()
          reloadDaily()
        }}
      />
      {!agendaError &&
        !meetingError &&
        !dailyError &&
        (agendaLoading || meetingLoading || dailyLoading) && (
          <div role="status">
            <span className="sr-only">일정과 보고서를 불러오는 중입니다.</span>
            <Skeleton height={LIST_H} radius="var(--r-lg)" />
          </div>
        )}

      {!agendaLoading &&
        !meetingLoading &&
        !dailyLoading &&
        !agendaError &&
        !meetingError &&
        !dailyError &&
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
              // 사내 업무는 단건 보고서를 만들지 않습니다. 그날 일일보고로 보냅니다.
              const internal = item.kind === 'internal'
              const link = internal
                ? internalLink(item.id)
                : meetingLinkFor(item.id, findByAgenda(item.id))

              return (
                <li key={item.id} className={styles.row}>
                  <span className={styles.kind}>{KIND_LABEL[item.kind]}</span>
                  <span className={`${styles.time} tnum`}>{item.time}</span>

                  <div className={styles.body}>
                    <strong>{item.hospital || item.title}</strong>
                    <span>{item.hospital ? item.title : item.place}</span>
                  </div>

                  <span className={item.done ? styles.done : styles.todo}>
                    {item.done ? '완료' : '예정'}
                  </span>

                  {/* 상태는 실제 보고서에서 봅니다. 일정의 reported 값은 믿지 않습니다. */}
                  <ReportStatusBadge status={link.status} />

                  <Link
                    className={buttonClass({ variant: 'outline', size: 'sm' }, styles.action)}
                    to={link.to ?? dailyComposePath(dateISO, '일일')}
                  >
                    {link.label}
                  </Link>
                </li>
              )
            })}
          </ul>
        ))}
    </section>
  )
}
