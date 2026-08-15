// 상태 탭. 발주가 지나는 단계를 그대로 탭으로 씁니다.
//
// 옆의 건수는 검색·공급처·기간까지만 적용한 수입니다. 상태까지 적용하면 고른 탭만
// 숫자가 남고 나머지가 0 이 되어 어디에 몇 건이 있는지 알 수 없습니다.
import type { OrderStatus } from '@/types'

import { ORDER_STATUSES, TONE_OF, type StatusTone } from '../../pipeline'

import styles from './StatusTabs.module.scss'

interface Props {
  /** 고른 상태. 빈 문자열이면 전체입니다. */
  value: string
  countOf: (status: OrderStatus) => number
  total: number
  onChange: (status: string) => void
}

export default function StatusTabs({ value, countOf, total, onChange }: Props) {
  return (
    <div className={styles.tabs} role="tablist" aria-label="발주 상태">
      <Tab label="전체" count={total} on={value === ''} onSelect={() => onChange('')} />
      {ORDER_STATUSES.map((status) => (
        <Tab
          key={status}
          label={status}
          count={countOf(status)}
          tone={TONE_OF[status]}
          on={value === status}
          onSelect={() => onChange(status)}
        />
      ))}
    </div>
  )
}

interface TabProps {
  label: string
  count: number
  tone?: StatusTone
  on: boolean
  onSelect: () => void
}

function Tab({ label, count, tone, on, onSelect }: TabProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={on}
      className={[styles.tab, on ? styles.isActive : ''].filter(Boolean).join(' ')}
      onClick={onSelect}
    >
      {tone && <i className={[styles.dot, styles[tone]].join(' ')} aria-hidden="true" />}
      {label}
      <span className={`${styles.count} tnum`}>{count}</span>
    </button>
  )
}
