// 단계 탭. 영업·견적·계약·발주 네 목록이 같은 탭을 씁니다.
//
// 옆의 건수는 단계를 뺀 나머지 조건까지만 적용한 수입니다. 단계까지 적용하면 고른 탭만
// 숫자가 남고 나머지가 0 이 되어 어디에 몇 건이 있는지 알 수 없습니다.
import type { ColumnTone, Stage } from '@/types'

import styles from './StageTabs.module.scss'

interface Props {
  stages: Stage[]
  /** 탭 묶음의 이름. 화면마다 '계약 단계'·'발주 상태' 처럼 다릅니다. */
  label: string
  /** 고른 단계. 빈 문자열이면 전체입니다. */
  value: string
  countOf: (stageId: string) => number
  total: number
  onChange: (stageId: string) => void
}

export default function StageTabs({ stages, label, value, countOf, total, onChange }: Props) {
  return (
    <div className={styles.tabs} role="tablist" aria-label={label}>
      <Tab label="전체" count={total} on={value === ''} onSelect={() => onChange('')} />
      {stages.map((stage) => (
        <Tab
          key={stage.id}
          label={stage.name}
          count={countOf(stage.id)}
          tone={stage.tone}
          on={value === stage.id}
          onSelect={() => onChange(stage.id)}
        />
      ))}
    </div>
  )
}

interface TabProps {
  label: string
  count: number
  tone?: ColumnTone
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
