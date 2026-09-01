// 업무 보고 한 화면. 위에서부터 기간 탭 → 제출 이력 달력 → 작성 리스트입니다.
// 작성만 별도 화면(/daily/new)으로 나갑니다.
//
// 업무보고서도 여기서 함께 봅니다. 목록에는 두 종류가 섞이므로 rows.ts 가 한 모양으로
// 정리한 뒤 넘깁니다. 조건(tab·q·status·approver·hospital·range)은 주소에 둡니다.
import { useCallback, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import Button, { buttonClass } from '@/components/Button'
import ErrorToast from '@/components/ErrorToast'
import { ChevronLeftIcon, ChevronRightIcon } from '@/components/icons'
import OwnerName from '@/components/OwnerName'
import Skeleton from '@/components/Skeleton'
import Tabs from '@/components/Tabs'
import WeekStrip from '@/components/WeekStrip'
import { dailyComposePath, meetingPickPath } from '@/constants/routes'
import { useShowOwner } from '@/shared/scope'
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
import ReportKindMenu, { type ComposeKind } from './components/ReportKindMenu'
import ReportStatusBadge from './components/ReportStatusBadge'
import { countFilters, parseFilters, writeFilters, type HistoryFilters } from './historyFilters'
import { PERIOD_KIND, PERIOD_LABEL, PERIODS, toPeriod } from './periods'
import { useReportFilterOptions, useReportList, useReportMarks } from './useReportHistory'

import styles from './Daily.module.scss'

/** 보고서를 기다리는 동안 잡아 두는 카드 높이. 실제 카드와 같아야 화면이 밀리지 않습니다. */
const WEEK_H = 210
const LIST_H = 340

// 이력은 지나간 걸 보는 것이라 일–토 한 주를 통째로 봅니다.
// (대시보드 주간 달력의 "오늘이 셋째 칸" 롤링 범위와는 성격이 다릅니다.)
const weekDays = (offset: number) => {
  const first = addDays(startOfWeek(TODAY), offset * 7)
  return Array.from({ length: 7 }, (_, i) => addDays(first, i))
}

export default function Daily() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const period = toPeriod(params.get('tab'))
  const showOwner = useShowOwner()
  const kind = PERIOD_KIND[period]

  /**
   * 이 탭이 이미 정한 종류로 가는 길. '전체' 탭만 무엇을 쓸지 모르므로 그때만
   * 드롭다운으로 묻습니다. 미팅은 일정 하나에 붙는 기록이라 일정 선택 화면으로 갑니다.
   */
  const composeTo =
    period === 'meeting'
      ? meetingPickPath(TODAY_ISO)
      : kind
        ? dailyComposePath(TODAY_ISO, kind)
        : null

  const [weekOffset, setWeekOffset] = useState(0)
  const [showMonth, setShowMonth] = useState(false)
  const [cursor, setCursor] = useState(() => startOfMonth(TODAY))
  // 달력에서 고른 날짜. 요약 패널이 열려 있는 동안에만 값이 있습니다.
  // 작성 리스트는 패널 없이 곧장 전문으로 갑니다.
  const [openISO, setOpenISO] = useState('')

  const query = params.get('q') ?? ''
  const filters = useMemo(() => {
    const parsed = parseFilters(params)
    return period === 'meeting'
      ? { ...parsed, status: parsed.status.filter((status) => status !== '작성중') }
      : parsed
  }, [params, period])

  const days = weekDays(weekOffset)

  // 목록은 조건을 다 걸어 서버가 좁혀 준 것을 그대로 그립니다. 예전에는 전건을 받아
  // 여기서 걸렀는데, 한 쪽만 받는 지금 그러면 첫 쪽에 없는 일치 항목이 통째로 빠집니다.
  const {
    rows: visible,
    total,
    loading,
    loadingMore,
    loadError,
    hasMore,
    loadMore,
    reload,
    ready,
  } = useReportList(period, query, filters)

  // 달력은 그 달에 무엇이 있었는지가 목적이라 검색어·필터를 걸지 않고 보이는 구간만
  // 따로 묻습니다. 한 달 달력은 앞뒤로 옆 달 칸까지 그리므로 한 주씩 넉넉히 봅니다.
  const [markFrom, markTo] = showMonth
    ? [iso(addDays(cursor, -7)), iso(addDays(addMonths(cursor, 1), 6))]
    : [iso(days[0]), iso(days[6])]
  const inKind = useReportMarks(period, markFrom, markTo)

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

  // 미팅은 일정 하나를 고르는 화면으로, 나머지는 그 종류의 자료를 모으는 작성 화면으로.
  // 기준 기간은 오늘로 시작합니다. 작성 화면이 종류에 맞는 주·월로 맞춰 읽습니다.
  const onPickKind = useCallback(
    (next: ComposeKind) =>
      navigate(next === '미팅' ? meetingPickPath(TODAY_ISO) : dailyComposePath(TODAY_ISO, next)),
    [navigate],
  )

  const resetAll = () => {
    const query = new URLSearchParams()
    const tab = params.get('tab')
    if (tab) query.set('tab', tab)
    setParams(query, { replace: true })
  }

  /** 필터 선택지. 목록에 있는 값만 내놓아야 고르고도 0건이 되지 않습니다. */
  const { approvers, hospitals } = useReportFilterOptions()

  // 칸마다 점 하나. 평일인데 지나갔고 일일보고가 비었으면 미작성 표시입니다.
  const renderMark = (dateISO: string, isSelected: boolean) => {
    const row = inKind.get(dateISO)?.[0]
    const dow = parseISO(dateISO).getDay()
    const tone = (() => {
      if (row?.status === '확정') return styles.markDone
      if (row?.status === '검토 대기') return styles.markPending
      if (row?.status === '작성중' || row?.status === '수정중') return styles.markDraft
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

  // 첫 진입입니다. 탭·달력·리스트가 차례로 나타나면 화면이 여러 번 들썩이므로
  // 한 장을 통째로 자리표시자로 두고 다 받은 뒤 한 번에 바꿉니다.
  if (!ready) {
    return (
      <section aria-busy>
        <h1 className="sr-only">업무 보고</h1>
        <div className={styles.headSkeleton}>
          <Skeleton width={220} height={36} radius="var(--r-pill)" />
          <Skeleton width={148} height={36} radius="var(--r-sm)" />
        </div>
        <Skeleton className={styles.weekSkeleton} height={WEEK_H} radius="var(--r-lg)" />
        <Skeleton height={LIST_H} radius="var(--r-lg)" />
      </section>
    )
  }

  return (
    <section aria-busy={loading}>
      {/* Topbar 빵부스러기가 이미 화면 이름을 말하므로 제목은 읽어 주기만 합니다. */}
      <h1 className="sr-only">업무 보고</h1>

      <div className={styles.head}>
        <Tabs
          variant="segmented"
          items={PERIODS.map((item) => ({ value: item, label: PERIOD_LABEL[item] }))}
          value={period}
          label="업무 보고 기간"
          onChange={setPeriod}
        />

        {/* 탭이 종류를 이미 골랐으면 한 번 더 묻지 않고 그 화면으로 바로 갑니다.
            일정에 붙는 업무보고서와 달리 기간 보고서는 언제나 본인 것이라 소유를 따지지
            않습니다. 서버도 작성자를 로그인한 사람으로 박습니다. */}
        {composeTo ? (
          <Link className={buttonClass()} to={composeTo}>
            보고서 작성하기
            <ChevronRightIcon />
          </Link>
        ) : (
          <ReportKindMenu onSelect={onPickKind} />
        )}
      </div>

      <article className={styles.week}>
        <div className={styles.weekHead}>
          <p className={`${styles.range} tnum`}>
            {showMonth ? fmtMonth(cursor) : weekRangeLabel(days)}
          </p>

          <div className={styles.weekTools}>
            <Button
              variant="outline"
              iconOnly
              onClick={() =>
                showMonth ? setCursor(addMonths(cursor, -1)) : setWeekOffset(weekOffset - 1)
              }
              aria-label={showMonth ? '이전 달' : '이전 주'}
            >
              <ChevronLeftIcon width={15} height={15} />
            </Button>
            {/* 문구와 톤을 대시보드 주간 달력과 맞춥니다. 같은 줄을 넘기는 버튼입니다. */}
            <Button
              variant="ghost"
              onClick={() => (showMonth ? setCursor(startOfMonth(TODAY)) : setWeekOffset(0))}
              disabled={showMonth ? iso(cursor) === iso(startOfMonth(TODAY)) : weekOffset === 0}
            >
              {showMonth ? '이번 달' : '오늘'}
            </Button>
            <Button
              variant="outline"
              iconOnly
              onClick={() =>
                showMonth ? setCursor(addMonths(cursor, 1)) : setWeekOffset(weekOffset + 1)
              }
              aria-label={showMonth ? '다음 달' : '다음 주'}
            >
              <ChevronRightIcon width={15} height={15} />
            </Button>

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
            onSelect={setOpenISO}
          />
        ) : (
          <div className={styles.strip}>
            <WeekStrip
              days={days}
              selectedISO={openISO}
              onSelect={setOpenISO}
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

      <ErrorToast message={loadError} onRetry={reload} />

      <HistoryToolbar
        query={query}
        onQueryChange={setQuery}
        filters={filters}
        onFiltersChange={setFilters}
        approvers={approvers}
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
            // 줄 어디를 눌러도 그 보고서 전문으로 넘어갑니다.
            <li key={row.id} className={styles.row} onClick={() => navigate(row.to)}>
              <span className={styles.type}>{row.kindLabel}</span>

              <div className={styles.rowBody}>
                {/* 줄 전체를 누르지만 li 는 키보드로 못 잡습니다. 제목이 그
                    손잡이이고, 하는 일은 줄을 누른 것과 같습니다. */}
                <strong>
                  <Link
                    className={styles.openButton}
                    to={row.to}
                    onClick={(event) => event.stopPropagation()}
                  >
                    {row.title}
                  </Link>
                </strong>
                <span className={styles.rowMeta}>
                  {/* 여러 사람의 보고서가 섞여 보일 때만 누가 썼는지 세웁니다. */}
                  {showOwner && <OwnerName name={row.author} />}
                  {row.meta}
                </span>
              </div>

              <span className={styles.approver}>{row.aside}</span>
              <span className={`${styles.date} tnum`}>{fmtDotShort(parseISO(row.date))}</span>
              <ReportStatusBadge status={row.status} />
            </li>
          ))}

          {/* 한 쪽씩 이어 받습니다. 다 받으면 이 줄이 사라집니다. */}
          {hasMore && (
            <li>
              <button
                type="button"
                className={styles.loadMore}
                disabled={loadingMore}
                onClick={loadMore}
              >
                {loadingMore ? '불러오는 중…' : `${total - visible.length}건 더 보기`}
              </button>
            </li>
          )}
        </ul>
      )}

      <p className={styles.count}>
        전체 <b className="tnum">{total}</b>건 중 {visible.length}건 표시
      </p>

      {openISO !== '' && (
        <ReportDrawer
          dateISO={openISO}
          rows={inKind.get(openISO) ?? []}
          // '전체' 탭은 종류를 고르지 않았으므로 머리말 CTA 와 같이 일일로 봅니다.
          kind={kind ?? '일일'}
          onClose={() => setOpenISO('')}
        />
      )}
    </section>
  )
}
