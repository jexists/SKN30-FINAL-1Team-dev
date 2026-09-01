import { useSyncExternalStore } from 'react'
import { Link } from 'react-router'

import { CheckIcon, CloseIcon, InfoIcon } from '@/components/icons'
import { dismissToast, getToasts, subscribeToasts } from '@/shared/toast'

import styles from './ToastHost.module.scss'

/**
 * 화면 밖 작업의 성공·실패 안내가 뜨는 자리입니다. App 에 한 번만 붙습니다.
 *
 * 안내를 띄운 화면이 곧바로 닫히는 일이 많아(등록 모달) 저장소를 구독만 하고,
 * 무엇을 띄울지는 showToast 를 부른 쪽이 정합니다.
 */
export default function ToastHost() {
  const toasts = useSyncExternalStore(subscribeToasts, getToasts)

  if (toasts.length === 0) return null

  return (
    <div className={styles.host}>
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={styles.toast}
          data-tone={toast.tone}
          role={toast.tone === 'error' ? 'alert' : 'status'}
          aria-live={toast.tone === 'error' ? 'assertive' : 'polite'}
        >
          <span className={styles.mark} aria-hidden="true">
            {toast.tone === 'error' ? (
              <InfoIcon width={14} height={14} />
            ) : (
              <CheckIcon width={13} height={13} />
            )}
          </span>
          <span className={styles.text}>{toast.message}</span>
          {toast.to && toast.actionLabel && (
            <Link className={styles.action} to={toast.to} onClick={() => dismissToast(toast.id)}>
              {toast.actionLabel}
            </Link>
          )}
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
