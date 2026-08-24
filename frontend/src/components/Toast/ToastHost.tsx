import { useSyncExternalStore } from 'react'

import { CheckIcon, CloseIcon } from '@/components/icons'
import { dismissToast, getToasts, subscribeToasts } from '@/shared/toast'

import styles from './ToastHost.module.scss'

/**
 * 성공 안내가 뜨는 자리입니다. App 에 한 번만 붙습니다.
 *
 * 안내를 띄운 화면이 곧바로 닫히는 일이 많아(등록 모달) 저장소를 구독만 하고,
 * 무엇을 띄울지는 showToast 를 부른 쪽이 정합니다.
 */
export default function ToastHost() {
  const toasts = useSyncExternalStore(subscribeToasts, getToasts)

  if (toasts.length === 0) return null

  return (
    <div className={styles.host} role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={styles.toast}>
          <span className={styles.mark} aria-hidden="true">
            <CheckIcon width={13} height={13} />
          </span>
          <span className={styles.text}>{toast.message}</span>
          <button
            type="button"
            className={styles.close}
            onClick={() => dismissToast(toast.id)}
            aria-label="닫기"
          >
            <CloseIcon />
          </button>
        </div>
      ))}
    </div>
  )
}
