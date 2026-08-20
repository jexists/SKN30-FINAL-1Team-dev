import { TEAM_API_ERROR } from '@/shared/team'

import styles from './Team.module.scss'

export default function Team() {
  return (
    <section className={styles.page}>
      <h1 className="sr-only">팀 관리</h1>
      <div className={styles.card} role="alert">
        <p className={styles.note}>{TEAM_API_ERROR}</p>
      </div>
    </section>
  )
}
