import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { ActivityDocuments } from '@/types'

const EMPTY: ActivityDocuments = { related: [], product: [] }

/**
 * 미팅에 관련된 자료실 문서를 가져옵니다.
 *
 * AI 브리핑과 분리된 조회입니다. 브리핑은 실행 시점에 박제되지만 이 목록은 드로어를 열
 * 때마다 다시 물어보므로, 브리핑을 만든 뒤에 올린 자료도 곧바로 보입니다. LLM 을 거치지
 * 않아 실패해도 브리핑과 서로 영향을 주지 않습니다.
 */
export default function useActivityDocuments(activityId: string) {
  const [documents, setDocuments] = useState<ActivityDocuments>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    client
      .get<ActivityDocuments>(`/activities/${activityId}/documents`)
      .then(({ data }) => {
        if (cancelled) return
        setDocuments(data)
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        setDocuments(EMPTY)
        setError(errorMessage(cause, '관련 자료를 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activityId])

  return { documents, loading, error }
}
