// 분류 탭. 자료실이 담는 문서 종류를 그대로 탭으로 씁니다.
//
// 옆의 건수는 검색·등록자·기간까지만 적용한 수입니다. 분류까지 적용하면 고른 탭만
// 숫자가 남고 나머지가 0 이 되어 어디에 몇 건이 있는지 알 수 없습니다.
import type { DocumentCategory } from '@/types'

import { type CategoryTone, DOCUMENT_CATEGORIES, TONE_OF } from '../../catalog'

import styles from './CategoryTabs.module.scss'

interface Props {
  /** 고른 분류. 빈 문자열이면 전체입니다. */
  value: string
  countOf: (category: DocumentCategory) => number
  total: number
  onChange: (category: string) => void
}

export default function CategoryTabs({ value, countOf, total, onChange }: Props) {
  return (
    <div className={styles.tabs} role="tablist" aria-label="자료 분류">
      <Tab label="전체" count={total} on={value === ''} onSelect={() => onChange('')} />
      {DOCUMENT_CATEGORIES.map((category) => (
        <Tab
          key={category}
          label={category}
          count={countOf(category)}
          tone={TONE_OF[category]}
          on={value === category}
          onSelect={() => onChange(category)}
        />
      ))}
    </div>
  )
}

interface TabProps {
  label: string
  count: number
  tone?: CategoryTone
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
