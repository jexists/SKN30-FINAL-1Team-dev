// 작성 리스트의 찾기 줄입니다. 유형은 기간 탭이 정하므로 여기에는 없고,
// 상태·보고 대상·고객사·기간은 Popover 안에 접어 둡니다. (Customers 의 도구 줄과 같은 방식)
//
// 보고 대상과 고객사는 서로 다른 탭의 값이라 한 번에 하나만 뜹니다.
// 업무 보고에는 고객사가 없고 업무보고서에는 결재선이 없습니다.
import { useState } from 'react'

import Button from '@/components/Button'
import { FilterIcon } from '@/components/icons'
import Popover from '@/components/Popover'
import SearchInput from '@/components/SearchInput'

import {
  countFilters,
  FILTER_RANGES,
  FILTER_STATUSES,
  NO_FILTERS,
  showsApprover,
  showsHospital,
  type HistoryFilters,
} from '../../historyFilters'
import type { Period } from '../../periods'

import styles from './HistoryToolbar.module.scss'

interface Props {
  query: string
  onQueryChange: (next: string) => void
  filters: HistoryFilters
  onFiltersChange: (next: HistoryFilters) => void
  approvers: string[]
  /** 미팅 탭의 고객사 선택지 */
  hospitals: string[]
  /** 지금 보고 있는 탭. 어느 그룹을 그릴지 정합니다. */
  period: Period
}

export default function HistoryToolbar({
  query,
  onQueryChange,
  filters,
  onFiltersChange,
  approvers,
  hospitals,
  period,
}: Props) {
  const [open, setOpen] = useState(false)
  const filterCount = countFilters(filters)

  const toggle = (key: 'status' | 'approver' | 'hospital', value: string) => {
    const current: string[] = filters[key]
    onFiltersChange({
      ...filters,
      [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value],
    })
  }

  return (
    <div className={styles.root}>
      <SearchInput
        className={styles.search}
        value={query}
        placeholder="보고서 검색"
        label="보고서 검색"
        onChange={onQueryChange}
      />

      <Popover
        open={open}
        onClose={() => setOpen(false)}
        align="end"
        label="이력 필터"
        trigger={
          <Button
            variant="outline"
            className={filterCount > 0 ? styles.isOn : ''}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            <FilterIcon width={15} height={15} />
            필터
            {filterCount > 0 && <span className={styles.badge}>{filterCount}</span>}
          </Button>
        }
      >
        <div className={styles.panel}>
          <fieldset className={styles.group}>
            <legend className={styles.legend}>상태</legend>
            <div className={styles.chips}>
              {FILTER_STATUSES.filter((value) => period !== 'meeting' || value !== '작성중').map(
                (value) => {
                  const on = filters.status.includes(value)
                  return (
                    <button
                      key={value}
                      type="button"
                      className={`${styles.chip} ${on ? styles.isChipOn : ''}`}
                      aria-pressed={on}
                      onClick={() => toggle('status', value)}
                    >
                      {value}
                    </button>
                  )
                },
              )}
            </div>
          </fieldset>

          {showsApprover(period) && (
            <fieldset className={styles.group}>
              <legend className={styles.legend}>보고 대상</legend>
              <div className={styles.chips}>
                {approvers.map((value) => {
                  const on = filters.approver.includes(value)
                  return (
                    <button
                      key={value}
                      type="button"
                      className={`${styles.chip} ${on ? styles.isChipOn : ''}`}
                      aria-pressed={on}
                      onClick={() => toggle('approver', value)}
                    >
                      {value}
                    </button>
                  )
                })}
              </div>
            </fieldset>
          )}

          {showsHospital(period) && (
            <fieldset className={styles.group}>
              <legend className={styles.legend}>고객사</legend>
              <div className={styles.chips}>
                {hospitals.map((value) => {
                  const on = filters.hospital.includes(value)
                  return (
                    <button
                      key={value}
                      type="button"
                      className={`${styles.chip} ${on ? styles.isChipOn : ''}`}
                      aria-pressed={on}
                      onClick={() => toggle('hospital', value)}
                    >
                      {value}
                    </button>
                  )
                })}
              </div>
            </fieldset>
          )}

          <fieldset className={styles.group}>
            <legend className={styles.legend}>기간</legend>
            <div className={styles.chips}>
              {FILTER_RANGES.map((item) => {
                const on = filters.range === item.value
                return (
                  <button
                    key={item.value}
                    type="button"
                    className={`${styles.chip} ${on ? styles.isChipOn : ''}`}
                    aria-pressed={on}
                    onClick={() => onFiltersChange({ ...filters, range: item.value })}
                  >
                    {item.label}
                  </button>
                )
              })}
            </div>
          </fieldset>

          <button
            type="button"
            className={styles.clear}
            disabled={filterCount === 0}
            onClick={() => onFiltersChange(NO_FILTERS)}
          >
            필터 초기화
          </button>
        </div>
      </Popover>
    </div>
  )
}
