import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

import { client } from '@/api/client'
import {
  getConnectionFailureCount,
  getConnectionUnreachable,
  subscribeConnection,
} from '@/api/connectionState'
import Button from '@/components/Button'
import Modal from '@/components/Modal'

/**
 * 백엔드에 닿지 못할 때만 뜨는 안내입니다.
 *
 * 앱 화면을 대체하지 않고 위에만 얹습니다. 닫아도 뒤 화면은 그대로 남고,
 * 이후에 다시 실패하면 같은 모달이 다시 뜹니다.
 */
export default function ConnectionAlert() {
  const unreachable = useSyncExternalStore(subscribeConnection, getConnectionUnreachable)
  const failureCount = useSyncExternalStore(subscribeConnection, getConnectionFailureCount)
  const [dismissed, setDismissed] = useState(false)
  const [retrying, setRetrying] = useState(false)

  // 연결이 돌아오거나, 닫은 뒤 새로 실패하면 다시 알립니다.
  // 실패 횟수를 함께 보지 않으면 한 번 닫은 안내가 복구 전까지 영영 묻힙니다.
  useEffect(() => {
    setDismissed(false)
  }, [unreachable, failureCount])

  const retry = useCallback(() => {
    setRetrying(true)
    // 성공하면 인터셉터가 연결 상태를 되돌리므로 여기서는 결과를 따로 보지 않습니다.
    client
      .get('/auth/me')
      .catch(() => undefined)
      .finally(() => setRetrying(false))
  }, [])

  if (!unreachable || dismissed) return null

  return (
    <Modal
      title="서버에 연결할 수 없습니다"
      description="백엔드 서버 상태를 확인한 뒤 다시 시도해 주세요."
      onClose={() => setDismissed(true)}
      footer={
        <>
          <Button type="button" variant="outline" onClick={() => setDismissed(true)}>
            닫기
          </Button>
          <Button type="button" disabled={retrying} onClick={retry}>
            {retrying ? '확인 중…' : '다시 시도'}
          </Button>
        </>
      }
    >
      <p>저장하지 않은 입력은 사라지지 않습니다. 연결이 복구되면 다시 시도해 주세요.</p>
    </Modal>
  )
}
