import type { ReactNode } from 'react'

import type { ReportActivity } from '@/types'

import styles from './ActivityList.module.scss'

interface Props {
  activities: ReportActivity[]
  renderAside?: (item: ReportActivity) => ReactNode
  /** 탭으로 이미 묶음을 가른 목록. 줄 사이 선을 빼고 꼬리를 가운데에 겁니다. */
  flush?: boolean
  /** 줄이 하나도 없을 때의 문구. 목록이 담는 것이 다르면 함께 바꿉니다. */
  empty?: string
}

export default function ActivityList({
  activities,
  renderAside,
  flush = false,
  empty = '이 기간에 제출된 관련 보고서가 없습니다.',
}: Props) {
  return activities.length === 0 ? (
    <p className={styles.empty}>{empty}</p>
  ) : (
    <ul className={styles.list}>
      {activities.map((item) => (
        <li
          key={item.id}
          className={`${styles.item} ${styles.bare}${flush ? ` ${styles.flush}` : ''}`}
        >
          <div className={styles.body}>
            <strong className={styles.title}>{item.title}</strong>
            <span className={styles.desc}>{item.desc}</span>
          </div>
          {renderAside && <span className={styles.aside}>{renderAside(item)}</span>}
        </li>
      ))}
    </ul>
  )
}
