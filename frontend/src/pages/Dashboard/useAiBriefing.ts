import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { ActivityRead, AiBriefing } from '@/types'

const POLL_INTERVAL_MS = 2_000
const MAX_POLLS = 30

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

interface Options {
  activityId: string
  /** 브리핑을 만들 수 있는 대상인지 — 미팅 타입이면서 연락처가 연결돼 있어야 한다. */
  eligible: boolean
}

/**
 * 미팅 상세를 열 때 AI 브리핑을 자동으로 준비한다.
 *
 * 버튼 없이, 열 때 이 활동에 걸린 브리핑 실행이 없으면(`ai_briefing == null`) 그 자리에서
 * 딱 한 번만 생성을 요청한다. 이미 있으면(완료·진행 중 무엇이든) 다시 만들지 않고 그 상태를
 * 그대로 보여준다 — 그래서 다른 곳을 봤다 돌아와도 내용이 바뀌지 않는다.
 * 자세한 배경은 docs/technical/multiagent/계약에이전트_설계.md 7장 참고.
 */
export default function useAiBriefing({ activityId, eligible }: Options) {
  const [briefing, setBriefing] = useState<AiBriefing | null>(null)
  const [loading, setLoading] = useState(eligible)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!eligible) {
      setBriefing(null)
      setLoading(false)
      setError(null)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)

    async function ensure() {
      let { data } = await client.get<ActivityRead>(`/activities/${activityId}`)
      if (cancelled) return

      if (data.ai_briefing == null) {
        await client.post('/agent-runs', {
          agent_code: 'contract_management_briefing',
          activity_id: activityId,
          idempotency_key: crypto.randomUUID(),
        })
        if (cancelled) return
        ;({ data } = await client.get<ActivityRead>(`/activities/${activityId}`))
        if (cancelled) return
      }

      for (
        let poll = 0;
        data.ai_briefing?.status === 'queued' || data.ai_briefing?.status === 'running';
        poll += 1
      ) {
        if (poll >= MAX_POLLS) throw new Error('briefing_timeout')
        await wait(POLL_INTERVAL_MS)
        if (cancelled) return
        ;({ data } = await client.get<ActivityRead>(`/activities/${activityId}`))
        if (cancelled) return
      }

      setBriefing(data.ai_briefing ?? null)
      setLoading(false)
    }

    ensure().catch((cause: unknown) => {
      if (cancelled) return
      setError(errorMessage(cause, 'AI 브리핑을 불러오지 못했습니다.'))
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [activityId, eligible])

  return { briefing, loading, error }
}
