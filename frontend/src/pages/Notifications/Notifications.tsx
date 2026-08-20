// 알림 화면. 헤더 벨로만 들어옵니다.
//
// 줄 하나가 알림 하나이고, 누르면 읽음으로 바꾼 뒤 그 알림이 가리키는 화면으로 보냅니다.
// 목록은 shared/notifications.ts 한 곳에 있습니다.
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { BellIcon, CloseIcon } from '@/components/icons'
import Tabs from '@/components/Tabs'
import { postedLabel } from '@/shared/notices'
import { markRead, removeNotification, useNotifications } from '@/shared/notifications'

import styles from './Notifications.module.scss'

export default function Notifications() {
  const navigate = useNavigate()
  const items = useNotifications()

  const [unreadOnly, setUnreadOnly] = useState(false)

  const rows = unreadOnly ? items.filter((n) => !n.read) : items

  return (
    <section className={styles.page}>
      <Tabs
        items={[
          { value: 'all', label: '전체' },
          { value: 'unread', label: '읽지 않음' },
        ]}
        value={unreadOnly ? 'unread' : 'all'}
        label="알림 종류"
        onChange={(next) => setUnreadOnly(next === 'unread')}
      />

      <div className={styles.card}>
        {rows.length === 0 ? (
          <div className={styles.empty}>
            <BellIcon width={34} height={34} strokeWidth={1.5} />
            <p>{unreadOnly ? '읽지 않은 알림이 없습니다.' : '받은 알림이 없습니다.'}</p>
          </div>
        ) : (
          <ul className={styles.list}>
            {rows.map((n) => (
              // 줄 전체가 이동 버튼이고, 삭제만 그 위에 따로 얹힙니다.
              // 버튼 안에 버튼을 넣을 수 없어 형제로 두고 배경만 줄 전체에 깝니다.
              <li key={n.id} className={`${styles.row} ${n.read ? '' : styles.unread}`}>
                <button
                  type="button"
                  className={styles.item}
                  onClick={() => {
                    markRead(n.id)
                    navigate(n.to)
                  }}
                >
                  <span className={styles.mark} />
                  <span className={styles.text}>{n.text}</span>
                  <span className={styles.time}>{postedLabel(n)}</span>
                </button>

                <button
                  type="button"
                  className={styles.remove}
                  onClick={() => removeNotification(n.id)}
                  aria-label="알림 삭제"
                >
                  <CloseIcon width={14} height={14} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
