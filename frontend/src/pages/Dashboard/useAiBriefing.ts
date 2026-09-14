import { useEffect, useState } from 'react'

import { client } from '@/api/client'
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
 * 이 훅은 브리핑을 **만들지 않습니다**. 미팅 상세를 열었다고 RAG 검색이나 LLM 생성을
 * 시작하면 그만큼 화면이 멈춰 있게 되므로, 만드는 일은 백엔드가 자료 처리·일정 변경
 * 시점에 미리 끝내 둡니다(`backend/app/services/briefing_refresh.py`). 화면이 하는 일은
 * 조회뿐입니다.
 *
 * - 열면 저장된 최신 성공 브리핑을 그대로 보여줍니다.
 * - 갱신이 도는 중(`refreshing`)이어도 이전 결과를 로딩 화면으로 덮지 않습니다. 그때만
 *   가벼운 GET polling 으로 완료된 결과와 바꿔 답니다. 이 polling 은 실행을 만들지 않습니다.
 * - 갱신이 실패해도 마지막 성공 브리핑은 그대로 남습니다(`refresh_error` 로만 알립니다).
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

  return { briefing, loading, error }
}
