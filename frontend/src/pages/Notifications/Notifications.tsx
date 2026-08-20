import { BellIcon } from '@/components/icons'
import { NOTIFICATION_API_ERROR } from '@/shared/notifications'

import styles from './Notifications.module.scss'

export default function Notifications() {
  return (
    <section className={styles.page}>
      <h1 className="sr-only">알림</h1>
      <div className={styles.card}>
        <div className={styles.empty} role="alert">
          <BellIcon width={34} height={34} strokeWidth={1.5} />
          <p>{NOTIFICATION_API_ERROR}</p>
        </div>
      </div>
    </section>
  )
}
