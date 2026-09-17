import { useEffect, useRef, useState } from 'react'

import { client } from '@/api/client'
import { regenerateBriefing } from '@/api/contractAgent'
import { errorMessage } from '@/api/errorMessage'
import type { ActivityRead, AiBriefing } from '@/types'

/** 갱신이 도는 중일 때만 결과를 바꿔 받는 간격. 조회(GET)만 하고 실행을 만들지 않는다. */
const POLL_INTERVAL_MS = 5_000
/** 갱신이 끝나지 않아도 조회를 계속 붙들지 않는다. 화면은 이미 이전 브리핑을 보여주고 있다. */
const MAX_POLLS = 24

const wait = (milliseconds: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds))

interface Options {
  activityId: string
  /** 브리핑이 붙을 수 있는 대상인지 — 미팅 타입이면서 연락처가 연결돼 있어야 한다. */
  eligible: boolean
}

/**
 * 저장돼 있는 AI 브리핑을 읽어 옵니다.
 *
 * 이 훅은 열 때 브리핑을 **만들지 않습니다**. 브리핑은 일정 등록 때 한 번 만들어지고,
 * 그 뒤에는 사용자가 새로고침(`regenerate`)을 눌렀을 때만 다시 만듭니다. 자료가 바뀌었는지는
 * 조회 응답의 `outdated` 로만 알립니다.
 *
 * - 열면 저장된 최신 성공 브리핑을 그대로 보여줍니다.
 * - 재생성이 도는 중(`refreshing`)이어도 이전 결과를 로딩 화면으로 덮지 않습니다. 그때만
 *   가벼운 GET polling 으로 완료된 결과와 바꿔 답니다. 이 polling 은 실행을 만들지 않습니다.
 * - 갱신이 실패해도 마지막 성공 브리핑은 그대로 남습니다(`refresh_error` 로만 알립니다).
 */
export default function useAiBriefing({ activityId, eligible }: Options) {
  const [briefing, setBriefing] = useState<AiBriefing | null>(null)
  const [loading, setLoading] = useState(eligible)
  const [error, setError] = useState<string | null>(null)
  const [regenerating, setRegenerating] = useState(false)
  const [regenerateError, setRegenerateError] = useState<string | null>(null)
  // 폴링을 다 썼는데도 갱신이 끝나지 않은 상태. 화면은 진행 줄을 걷고 이전 브리핑을
  // 다시 제대로 읽게 합니다 — 더 볼 것이 오지 않는데 초만 세고 있을 이유가 없습니다.
  const [stalled, setStalled] = useState(false)
  const currentActivityId = useRef(activityId)
  currentActivityId.current = activityId

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
    setRegenerating(false)
    setRegenerateError(null)
    setStalled(false)

    async function read() {
      let { data } = await client.get<ActivityRead>(`/activities/${activityId}`)
      if (cancelled) return

      // 첫 조회 결과를 곧바로 겁니다. 갱신이 돌고 있어도 본문을 기다리지 않습니다.
      setBriefing(data.ai_briefing ?? null)
      setLoading(false)

      for (let poll = 0; data.ai_briefing?.refreshing && poll < MAX_POLLS; poll += 1) {
        await wait(POLL_INTERVAL_MS)
        if (cancelled) return
        ;({ data } = await client.get<ActivityRead>(`/activities/${activityId}`))
        if (cancelled) return
        setBriefing(data.ai_briefing ?? null)
      }
      if (data.ai_briefing?.refreshing) setStalled(true)
    }

    read().catch((cause: unknown) => {
      if (cancelled) return
      setError(errorMessage(cause, 'AI 브리핑을 불러오지 못했습니다.'))
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [activityId, eligible])

  async function regenerate() {
    if (!eligible || regenerating || briefing?.refreshing) return
    const requestedActivityId = activityId
    setRegenerating(true)
    setRegenerateError(null)
    setError(null)
    setStalled(false)
    try {
      await regenerateBriefing(requestedActivityId)
      let { data } = await client.get<ActivityRead>(`/activities/${requestedActivityId}`)
      if (currentActivityId.current !== requestedActivityId) return
      setBriefing(data.ai_briefing ?? null)
      for (let poll = 0; data.ai_briefing?.refreshing && poll < MAX_POLLS; poll += 1) {
        await wait(POLL_INTERVAL_MS)
        ;({ data } = await client.get<ActivityRead>(`/activities/${requestedActivityId}`))
        if (currentActivityId.current !== requestedActivityId) return
        setBriefing(data.ai_briefing ?? null)
      }
      if (data.ai_briefing?.refreshing) setStalled(true)
    } catch (cause: unknown) {
      if (currentActivityId.current === requestedActivityId) {
        setRegenerateError(errorMessage(cause, 'AI 브리핑을 다시 만들지 못했습니다.'))
      }
    } finally {
      if (currentActivityId.current === requestedActivityId) setRegenerating(false)
    }
  }

  return { briefing, loading, error, regenerate, regenerating, regenerateError, stalled }
}
