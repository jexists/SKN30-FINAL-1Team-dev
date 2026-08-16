// 업무 보고 한 화면. 위에서부터 기간 탭 → 제출 이력 달력 → 작성 리스트입니다.
// 작성만 별도 화면(/daily/new)으로 나갑니다.
//
// 미팅보고서도 여기서 함께 봅니다. 목록에는 두 종류가 섞이므로 rows.ts 가 한 모양으로
// 정리한 뒤 넘깁니다. 조건(tab·q·status·approver·hospital·range)은 주소에 둡니다.
import { useCallback, useDeferredValue, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import Button from '@/components/Button'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import WeekStrip from '@/components/WeekStrip'
import { dailyComposePath, ROUTES } from '@/constants/routes'
import { APPROVERS } from '@/shared/reports'
import useMeetingReports from '@/pages/Meetings/useMeetingReports'
import {
  addDays,
  addMonths,
  fmtDotShort,
  fmtMonth,
  iso,
  parseISO,
  startOfMonth,
  startOfWeek,
  TODAY,
  TODAY_ISO,
  weekRangeLabel,
} from '@/utils/date'

import HistoryToolbar from './components/HistoryToolbar'
import MonthCalendar from './components/MonthCalendar'
import ReportDrawer from './components/ReportDrawer'
import ReportStatusBadge from './components/ReportStatusBadge'
import { countFilters, parseFilters, writeFilters, type HistoryFilters } from './historyFilters'
import { PERIOD_KIND, PERIOD_LABEL, PERIODS, showsDaily, showsMeetings, toPeriod } from './periods'
import { byDateDesc, fromDailyReport, fromMeetingReport, type ListRow } from './rows'
import useDailyReports from './useDailyReports'

import styles from './Daily.module.scss'

// 이력은 지나간 걸 보는 것이라 일–토 한 주를 통째로 봅니다.
// (대시보드 주간 달력의 "오늘이 셋째 칸" 롤링 범위와는 성격이 다릅니다.)
const weekDays = (offset: number) => {
  const first = addDays(startOfWeek(TODAY), offset * 7)
  return Array.from({ length: 7 }, (_, i) => addDays(first, i))
}

/**
 * 열려 있는 요약 패널. 여는 길이 둘입니다.
 *
 * 달력은 그날 낸 것을 통째로 펴고, 작성 리스트는 고른 보고서 하나만 폅니다.
 * 어느 쪽이든 그 날짜가 달력에서 선택으로 보입니다.
 */
type OpenPanel = { by: 'date'; dateISO: string } | { by: 'row'; row: ListRow }

/** 기간 필터의 시작일. 'all' 이면 자르지 않습니다. */
function rangeStartISO(range: HistoryFilters['range']): string | null {
  if (range === 'week') return iso(startOfWeek(TODAY))
  if (range === 'month') return iso(startOfMonth(TODAY))
  if (range === 'quarter') return iso(addMonths(TODAY, -3))
  return null
}

export default function Daily() {
  const [params, setParams] = useSearchParams()
  const period = toPeriod(params.get('tab'))
  const kind = PERIOD_KIND[period]

  const { reports } = useDailyReports()
  const { reports: meetings } = useMeetingReports()

  const [weekOffset, setWeekOffset] = useState(0)
  const [showMonth, setShowMonth] = useState(false)
  const [cursor, setCursor] = useState(() => startOfMonth(TODAY))
  // drawer 가 열려 있는 동안에만 값이 있습니다.
  const [open, setOpen] = useState<OpenPanel | null>(null)
  const openISO = open === null ? '' : open.by === 'date' ? open.dateISO : open.row.date

  const query = params.get('q') ?? ''
  const filters = useMemo(() => parseFilters(params), [params])

  // 타이핑이 목록 계산에 막히지 않게 검색어만 뒤로 미룹니다.
  const deferredQuery = useDeferredValue(query)

  const days = weekDays(weekOffset)

  // 탭이 고른 것만 한 모양으로 폅니다. 달력과 리스트가 같은 목록에서 출발합니다.
  const rows = useMemo(() => {
    const picked: ListRow[] = []
    if (showsDaily(period)) {
      for (const report of reports) {
        if (kind && report.kind !== kind) continue
        picked.push(fromDailyReport(report))
      }
    }
    if (showsMeetings(period)) {
      for (const meeting of meetings) picked.push(fromMeetingReport(meeting))
    }
    return picked.sort(byDateDesc)
  }, [reports, meetings, period, kind])

  // 달력은 그 달에 무엇이 있었는지가 목적이라 검색어·필터를 걸지 않습니다.
  const inKind = useMemo(() => {
    const map = new Map<string, ListRow[]>()
    for (const row of rows) {
      const found = map.get(row.date)
      if (found) found.push(row)
      else map.set(row.date, [row])
    }
    return map
  }, [rows])

  // 리스트는 검색어와 필터까지 겁니다.
  const visible = useMemo(() => {
    const from = rangeStartISO(filters.range)
    const needle = deferredQuery.trim().toLowerCase()

    return rows.filter((row) => {
      if (filters.status.length > 0 && !filters.status.includes(row.status)) return false
      // 보고 대상과 고객사는 그 값을 가진 종류에만 겁니다.
      if (filters.approver.length > 0 && !filters.approver.includes(row.aside)) return false
      if (filters.hospital.length > 0 && !filters.hospital.includes(row.hospital ?? ''))
        return false
      if (from && row.date < from) return false
      // haystack 은 보고 본문까지 담고 있습니다. 제목만으로는 찾을 수 있는 게 거의 없습니다.
      return needle === '' || row.haystack.includes(needle)
    })
  }, [rows, filters, deferredQuery])

  const filterCount = countFilters(filters)
  const narrowed = filterCount > 0 || query.trim().length > 0

  // 기본값인 조건은 주소에서 지웁니다. 주소를 복사했을 때 조건이 그대로 살아나되 짧게 남습니다.
  const setQuery = useCallback(
    (next: string) => {
      const query = new URLSearchParams(params)
      if (next === '') query.delete('q')
      else query.set('q', next)
      setParams(query, { replace: true })
    },
    [params, setParams],
  )

  const setFilters = useCallback(
    (next: HistoryFilters) => setParams(writeFilters(params, next, period), { replace: true }),
    [params, setParams, period],
  )

  // 탭을 갈아탈 때 그 탭에 없는 조건은 함께 지웁니다. 보이지 않는 필터가 목록을
  // 걸러 버리면 왜 비었는지 알 길이 없습니다.
  const setPeriod = useCallback(
    (next: string) => {
      const query = new URLSearchParams(params)
      if (next === 'all') query.delete('tab')
      else query.set('tab', next)
      setParams(writeFilters(query, filters, toPeriod(next)), { replace: true })
    },
    [params, setParams, filters],
  )

  const resetAll = () => {
    const query = new URLSearchParams()
    const tab = params.get('tab')
    if (tab) query.set('tab', tab)
    setParams(query, { replace: true })
  }

  /** 미팅 탭의 고객사 선택지. 목록에 있는 값만 내놓아야 고르고도 0건이 되지 않습니다. */
  const hospitals = useMemo(
    () => [...new Set(meetings.map((meeting) => meeting.hospital))].sort(),
    [meetings],
  )

  // 칸마다 점 하나. 평일인데 지나갔고 일일보고가 비었으면 미작성 표시입니다.
  const renderMark = (dateISO: string, isSelected: boolean) => {
    const row = inKind.get(dateISO)?.[0]
    const dow = parseISO(dateISO).getDay()
    const tone = (() => {
      if (row?.status === '확정') return styles.markDone
      if (row?.status === '검토 대기') return styles.markPending
      if (row?.status === '작성중') return styles.markDraft
      if (row?.status === '반려') return styles.markMissing
      // 주간·월간·미팅은 매일 내는 보고가 아니므로 미작성으로 보지 않습니다.
      if (period !== 'all' && period !== 'daily') return null
      const past = dateISO < TODAY_ISO
      if (past && dow !== 0 && dow !== 6) return styles.markMissing
      return null
    })()

    if (!tone) return null
    return <i className={`${tone} ${isSelected ? styles.isOnBlue : ''}`} />
  }

  return (
    <section>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">업무 보고</h1>

      <div className={styles.head}>
        <div className={styles.tabs} role="tablist" aria-label="업무 보고 기간">
          {PERIODS.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={period === item}
              className={`${styles.tab} ${period === item ? styles.isActive : ''}`}
              onClick={() => setPeriod(item)}
            >
              {PERIOD_LABEL[item]}
            </button>
          ))}
        </div>

        {/* 미팅 기록은 캘린더 일정 하나를 받아 쓰는 것이라 빈 화면으로 열 수 없습니다.
            그래서 미팅 탭에서는 작성 대신 일정을 고르러 보냅니다. */}
        {period === 'meeting' ? (
          <Link className={styles.cta} to={ROUTES.CALENDAR}>
            일정에서 미팅 기록하기
            <ChevronRightIcon />
          </Link>
        ) : (
          <Link className={styles.cta} to={dailyComposePath(TODAY_ISO, kind ?? '일일')}>
            보고서 작성하기
            <ChevronRightIcon />
          </Link>
        )}
      </div>

      <article className={styles.week}>
        <div className={styles.weekHead}>
          <p className={`${styles.range} tnum`}>
            {showMonth ? fmtMonth(cursor) : weekRangeLabel(days)}
          </p>

          <div className={styles.weekTools}>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={() =>
                showMonth ? setCursor(addMonths(cursor, -1)) : setWeekOffset(weekOffset - 1)
              }
              aria-label={showMonth ? '이전 달' : '이전 주'}
            >
              <ChevronLeftIcon width={15} height={15} />
            </button>
            {/* 문구와 톤을 대시보드 주간 달력과 맞춥니다. 같은 줄을 넘기는 버튼입니다. */}
            <Button
              variant="ghost"
              onClick={() => (showMonth ? setCursor(startOfMonth(TODAY)) : setWeekOffset(0))}
              disabled={showMonth ? iso(cursor) === iso(startOfMonth(TODAY)) : weekOffset === 0}
            >
              {showMonth ? '이번 달' : '오늘'}
            </Button>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={() =>
                showMonth ? setCursor(addMonths(cursor, 1)) : setWeekOffset(weekOffset + 1)
              }
              aria-label={showMonth ? '다음 달' : '다음 주'}
            >
              <ChevronRightIcon width={15} height={15} />
            </button>

            <button
              type="button"
              className={styles.more}
              aria-expanded={showMonth}
              onClick={() => setShowMonth(!showMonth)}
            >
              {showMonth ? '주간으로 보기' : '달력 더보기'}
            </button>
          </div>
        </div>

        {showMonth ? (
          <MonthCalendar
            cursor={cursor}
            byDate={inKind}
            selectedISO={openISO}
            onSelect={(dateISO) => setOpen({ by: 'date', dateISO })}
          />
        ) : (
          <div className={styles.strip}>
            <WeekStrip
              days={days}
              selectedISO={openISO}
              onSelect={(dateISO) => setOpen({ by: 'date', dateISO })}
              onOutOfRange={(next) => setWeekOffset(weekOffset + (next < iso(days[0]) ? -1 : 1))}
              renderMarks={renderMark}
              label="제출 이력 주간 달력"
            />
          </div>
        )}

        {/* 상태 점은 주간 strip 에만 찍힙니다. 한 달 달력은 종류를 칩으로 보여 줍니다. */}
        {!showMonth && (
          <p className={styles.legend}>
            <span>
              <i className={styles.markDone} /> 확정
            </span>
            <span>
              <i className={styles.markPending} /> 검토 대기
            </span>
            <span>
              <i className={styles.markDraft} /> 작성중
            </span>
            <span>
              <i className={styles.markMissing} /> 미작성 · 반려
            </span>
          </p>
        )}
      </article>

      <div className={styles.listHead}>
        <h2 className={styles.listTitle}>작성 리스트</h2>
      </div>

      <HistoryToolbar
        query={query}
        onQueryChange={setQuery}
        filters={filters}
        onFiltersChange={setFilters}
        approvers={[...APPROVERS]}
        hospitals={hospitals}
        period={period}
      />

      {visible.length === 0 ? (
        <div className={styles.empty}>
          <p>조건에 맞는 보고서가 없습니다.</p>
          {narrowed && (
            <button type="button" className={styles.reset} onClick={resetAll}>
              필터 초기화
            </button>
          )}
        </div>
      ) : (
        <ul className={styles.rows}>
          {visible.map((row) => (
            // 줄 어디를 눌러도 요약이 섭니다. 전문으로는 그 안의 '전체 보기' 로 넘어갑니다.
            <li key={row.id} className={styles.row} onClick={() => setOpen({ by: 'row', row })}>
              <span className={styles.type}>{row.kindLabel}</span>

              <div className={styles.rowBody}>
                {/* 줄 전체를 누르지만 li 는 키보드로 못 잡습니다. 제목이 그
                    손잡이이고, 하는 일은 줄을 누른 것과 같습니다. */}
                <strong>
                  <button
                    type="button"
                    className={styles.openButton}
                    onClick={(event) => {
                      event.stopPropagation()
                      setOpen({ by: 'row', row })
                    }}
                  >
                    {row.title}
                  </button>
                </strong>
                <span>{row.meta}</span>
              </div>

              <span className={styles.approver}>{row.aside}</span>
              <span className={`${styles.date} tnum`}>{fmtDotShort(parseISO(row.date))}</span>
              <ReportStatusBadge status={row.status} />
            </li>
          ))}
        </ul>
      )}

      <p className={styles.count}>
        전체 {rows.length}건 중 <b className="tnum">{visible.length}</b>건
      </p>

      {open !== null && (
        <ReportDrawer
          dateISO={openISO}
          rows={open.by === 'row' ? [open.row] : (inKind.get(openISO) ?? [])}
          // '전체' 탭은 종류를 고르지 않았으므로 머리말 CTA 와 같이 일일로 봅니다.
          kind={kind ?? '일일'}
          onClose={() => setOpen(null)}
        />
      )}
    </section>
  )
}
