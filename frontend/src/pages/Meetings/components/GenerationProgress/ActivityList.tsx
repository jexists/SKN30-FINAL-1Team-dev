// 활동 한 줄들. 진행 화면과 딜 카드가 같은 것을 씁니다 — 같은 종류의 소식이
// 자리에 따라 다른 모양으로 나오면 사람이 두 번 배워야 합니다.
import styles from './GenerationProgress.module.scss'
import type { ActivityRow } from './progressModel'

const MARK: Record<ActivityRow['state'], string> = {
  done: styles.done,
  live: styles.live,
  running: styles.running,
}

export default function ActivityList({ rows, label }: { rows: ActivityRow[]; label?: string }) {
  if (!rows.length) return null
  return (
    <ol className={styles.feed} aria-label={label}>
      {rows.map((row) => (
        <li
          key={row.key}
          className={MARK[row.state]}
          aria-current={row.state === 'live' ? 'step' : undefined}
        >
          <span className={styles.mark} aria-hidden="true" />
          <span className={styles.rowLabel}>{row.label}</span>
          {row.detail && <span className={styles.detail}>{row.detail}</span>}
        </li>
      ))}
    </ol>
  )
}
