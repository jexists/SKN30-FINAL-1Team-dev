// 작성 리스트의 찾기 줄입니다. 유형은 기간 탭이 정하므로 여기에는 없고,
// 검색어 → 상태 → 기간 순으로 넓은 조건이 먼저 옵니다. 검색어만 한 줄을 쓰고
// 나머지 조건은 둘째 줄에 나란히 섭니다 — 조건마다 한 줄씩 쓰면 목록이 화면
// 아래로 밀려납니다.
//
// 조건을 접어 두지 않습니다. 보이지 않는 필터가 목록을 걸러 버리면 왜 비었는지
// 알 길이 없습니다. 검색어만 기존대로 검색 버튼·Enter 로 확정하고, 상태와 기간은
// 고르는 즉시 목록에 걸립니다(딜·계약 화면의 탭·드롭다운과 같은 방식).
//
// 초기화 버튼은 두지 않습니다. 상태의 '전체'와 기간의 '전체'가 이미 되돌리는
// 자리라 같은 일을 하는 버튼이 하나 더 서 있을 뿐이었습니다. 목록이 비었을 때는
// Daily 가 빈 자리에 '필터 초기화'를 띄웁니다 — 그때는 되돌릴 곳이 멀어집니다.
import { useMemo } from 'react'

import DayPicker from '@/components/DayPicker'
import SearchInput from '@/components/SearchInput'
import Tabs, { type TabItem } from '@/components/Tabs'
import { iso, parseISO } from '@/utils/date'

import {
  activePreset,
  presetRange,
  RANGE_PRESETS,
  statusesFor,
  STATUS_TONE,
  type FilterStatus,
  type HistoryFilters,
} from '../../historyFilters'
import type { Period } from '../../periods'

import styles from './HistoryToolbar.module.scss'

type StatusValue = FilterStatus | ''

interface Props {
  query: string
  onSearch: (next: string) => void
  filters: HistoryFilters
  onFiltersChange: (next: HistoryFilters) => void
  /** 지금 보고 있는 탭. 상태 칩의 어휘를 이 값이 정합니다. */
  period: Period
}

/** 빈 문자열은 조건 없음이라 달력에는 아무것도 고르지 않은 것으로 넘깁니다. */
const toDate = (value: string) => (value === '' ? null : parseISO(value))
const toISO = (date: Date | null) => (date === null ? '' : iso(date))

export default function HistoryToolbar({
  query,
  onSearch,
  filters,
  onFiltersChange,
  period,
}: Props) {
  // 미팅 탭은 '전체·작성중·작성완료', 나머지는 검토 단계까지 넷입니다.
  const statusItems = useMemo<TabItem<StatusValue>[]>(
    () => [
      { value: '', label: '전체' },
      ...statusesFor(period).map((value) => ({ value, label: value, tone: STATUS_TONE[value] })),
    ],
    [period],
  )

  return (
    <div className={styles.root}>
      <SearchInput
        className={styles.search}
        value={query}
        placeholder="보고서 검색"
        label="보고서 검색"
        onSearch={onSearch}
      />

      <div className={styles.filters}>
        <Tabs
          className={styles.status}
          items={statusItems}
          value={filters.status}
          label="보고서 상태"
          onChange={(status) => onFiltersChange({ ...filters, status })}
        />

        {/* 성격이 다른 두 조건이 한 줄에 서므로 눈으로 갈라 줍니다. */}
        <span className={styles.divider} aria-hidden="true" />

        <DayPicker
          className={styles.day}
          selected={toDate(filters.start)}
          maxDate={toDate(filters.end) ?? undefined}
          label="조회 시작일"
          placeholderText="시작일"
          isClearable
          onChange={(date) => onFiltersChange({ ...filters, start: toISO(date) })}
        />
        <span className={styles.tilde} aria-hidden="true">
          ~
        </span>
        <DayPicker
          className={styles.day}
          selected={toDate(filters.end)}
          minDate={toDate(filters.start) ?? undefined}
          label="조회 종료일"
          placeholderText="종료일"
          isClearable
          onChange={(date) => onFiltersChange({ ...filters, end: toISO(date) })}
        />

        {/* 자주 보는 구간을 한 번에. 누르면 시작·끝을 함께 갈아 끼웁니다.
            날짜를 직접 고치면 어느 칸과도 맞지 않게 되어 모두 꺼집니다. */}
        <Tabs
          variant="segmented"
          items={RANGE_PRESETS}
          value={activePreset(filters) ?? ''}
          label="기간 빠른 선택"
          onChange={(value) => onFiltersChange({ ...filters, ...presetRange(value) })}
        />
      </div>
    </div>
  )
}
