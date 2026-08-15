import { ChevronDownIcon } from '@/components/icons'

import { COLUMN_BY_ID } from '../../columns'
import type { ColumnPrefs } from '../../useColumnPrefs'

import styles from './ColumnSettings.module.scss'

interface ColumnSettingsProps {
  prefs: ColumnPrefs
  onToggle: (id: string) => void
  onMove: (id: string, delta: -1 | 1) => void
  onReset: () => void
}

export default function ColumnSettings({ prefs, onToggle, onMove, onReset }: ColumnSettingsProps) {
  const items = prefs.order.map((id) => COLUMN_BY_ID.get(id)).filter((c) => c !== undefined)

  return (
    <div className={styles.root}>
      <p className={styles.hint}>
        표에 넣을 항목과 순서를 정합니다. 너비는 표 헤더 경계를 끌어 조절합니다.
      </p>

      <ul className={styles.list}>
        {items.map((col, index) => {
          const on = prefs.visible.includes(col.id)
          return (
            <li key={col.id} className={styles.item}>
              <label className={styles.toggle}>
                <input
                  type="checkbox"
                  checked={on || col.fixed === true}
                  disabled={col.fixed}
                  onChange={() => onToggle(col.id)}
                />
                <span>{col.header}</span>
                {col.fixed && <span className={styles.lock}>고정</span>}
              </label>

              <span className={styles.moves}>
                <button
                  type="button"
                  className={styles.move}
                  disabled={col.fixed || items[index - 1]?.fixed === true}
                  aria-label={`${col.header} 위로`}
                  onClick={() => onMove(col.id, -1)}
                >
                  <ChevronDownIcon width={14} height={14} className={styles.flip} />
                </button>
                <button
                  type="button"
                  className={styles.move}
                  disabled={col.fixed || index === items.length - 1}
                  aria-label={`${col.header} 아래로`}
                  onClick={() => onMove(col.id, 1)}
                >
                  <ChevronDownIcon width={14} height={14} />
                </button>
              </span>
            </li>
          )
        })}
      </ul>

      <button type="button" className={styles.reset} onClick={onReset}>
        기본값으로 되돌리기
      </button>
    </div>
  )
}
