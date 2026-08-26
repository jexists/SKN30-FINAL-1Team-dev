import { useState } from 'react'

import Button from '@/components/Button'
import { CloseIcon } from '@/components/icons'

import styles from './ErrorToast.module.scss'

interface Props {
  /** 표시할 오류 문구. 없으면 아무것도 그리지 않습니다. */
  message: string | null | undefined
  onRetry?: () => void
}

/**
 * 목록·집계를 받아 오지 못했을 때 헤더 바로 아래에 뜨는 안내입니다.
 *
 * 본문 자리를 대체하지 않고 위에 얹기만 합니다. 받아 온 것이 없어 화면이
 * 비어 보이더라도, 왜 비었는지는 이 토스트가 말합니다.
 */
export default function ErrorToast({ message, onRetry }: Props) {
  // 닫은 문구 자체를 들고 있으면 효과 없이도 다른 오류에서 다시 뜹니다.
  // ponytail: 같은 문구가 재시도 후 또 나오면 다시 뜨지 않습니다.
  //           실패 횟수까지 보려면 ConnectionAlert 처럼 카운터를 받으세요.
  const [dismissed, setDismissed] = useState<string | null>(null)

  if (!message || message === dismissed) return null

  return (
    <div className={styles.toast} role="alert">
      <span className={styles.mark} aria-hidden="true">
        !
      </span>
      <span className={styles.text}>{message}</span>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          다시 시도
        </Button>
      )}
      <button
        type="button"
        className={styles.close}
        onClick={() => setDismissed(message)}
        aria-label="닫기"
      >
        <CloseIcon />
      </button>
    </div>
  )
}
