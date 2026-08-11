import { CUSTOMER_OWNERS, CUSTOMER_SOURCES, CUSTOMER_STATUSES } from '@/content/customers'

import type { Filters } from '../../Customers'

import styles from './FilterPanel.module.scss'

interface FilterPanelProps {
  filters: Filters
  onChange: (next: Filters) => void
}

type ListKey = 'status' | 'owner' | 'source'

const GROUPS: { key: ListKey; label: string; options: string[] }[] = [
  { key: 'status', label: '상태', options: CUSTOMER_STATUSES },
  { key: 'owner', label: '담당 영업', options: CUSTOMER_OWNERS },
  { key: 'source', label: '유입 소스', options: CUSTOMER_SOURCES },
]

export default function FilterPanel({ filters, onChange }: FilterPanelProps) {
  const toggle = (key: ListKey, value: string) => {
    const current = filters[key]
    onChange({
      ...filters,
      [key]: current.includes(value) ? current.filter((v) => v !== value) : [...current, value],
    })
  }

  const active =
    filters.status.length + filters.owner.length + filters.source.length > 0 || filters.overdueOnly

  return (
    <div className={styles.root}>
      {GROUPS.map((group) => (
        <fieldset key={group.key} className={styles.group}>
          <legend className={styles.legend}>{group.label}</legend>
          <div className={styles.chips}>
            {group.options.map((option) => {
              const on = filters[group.key].includes(option)
              return (
                <button
                  key={option}
                  type="button"
                  className={`${styles.chip} ${on ? styles.isOn : ''}`}
                  aria-pressed={on}
                  onClick={() => toggle(group.key, option)}
                >
                  {option}
                </button>
              )
            })}
          </div>
        </fieldset>
      ))}

      <label className={styles.switch}>
        <input
          type="checkbox"
          checked={filters.overdueOnly}
          onChange={(event) => onChange({ ...filters, overdueOnly: event.target.checked })}
        />
        후속이 늦은 고객만
      </label>

      <p className={styles.hint}>
        같은 항목끼리는 하나만 맞아도, 다른 항목끼리는 모두 맞아야 걸립니다.
      </p>

      <button
        type="button"
        className={styles.clear}
        disabled={!active}
        onClick={() => onChange({ status: [], owner: [], source: [], overdueOnly: false })}
      >
        필터 초기화
      </button>
    </div>
  )
}
