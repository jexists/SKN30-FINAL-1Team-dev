import type { ReactNode } from 'react'

import type { ReportActivity } from '@/types'

import styles from './ActivityList.module.scss'

interface Props {
  activities: ReportActivity[]
  renderAside?: (item: ReportActivity) => ReactNode
}

export default function ActivityList({ activities, renderAside }: Props) {
  return activities.length === 0 ? (
    <p className={styles.empty}>이 기간에 제출된 관련 보고서가 없습니다.</p>
  ) : (
    <ul className={styles.list}>
      {activities.map((item) => (
        <li key={item.id} className={`${styles.item} ${styles.bare}`}>
          <div className={styles.body}>
            <strong className={styles.title}>{item.title}</strong>
            <span className={styles.desc}>{item.desc}</span>
          </div>
          <span className={styles.source}>{item.source}</span>
          {renderAside && <span className={styles.aside}>{renderAside(item)}</span>}
        </li>
      ))}
    </ul>
  )
}
