import { useCallback, useState } from 'react'

import { cancelAgentRun } from '@/api/reportAgent'

export default function useAgentRunCancellation(
  runId: string | undefined,
  abort: () => void,
  onCancelled: () => void,
) {
  const [cancelling, setCancelling] = useState(false)
  const [cancelled, setCancelled] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  const cancel = useCallback(async () => {
    if (!runId || cancelling) return
    setCancelled(false)
    setCancelling(true)
    setCancelError(null)
    try {
      const response = await cancelAgentRun(runId)
      if (response.cancelled_run_ids.length > 0) {
        setCancelled(true)
        onCancelled()
        abort()
      }
    } catch {
      setCancelError('생성 중단 요청을 처리하지 못했습니다. 생성은 계속 진행됩니다.')
    } finally {
      setCancelling(false)
    }
  }, [abort, cancelling, onCancelled, runId])

  return { cancel, cancelling, cancelled, cancelError }
}
