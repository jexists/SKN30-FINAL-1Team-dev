import { useEffect, useState } from 'react'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import type { ActivityRead, AiBriefing } from '@/types'

const POLL_INTERVAL_MS = 5_000

/** 드로어가 닫히면 남은 타이머도 즉시 정리한다. */
const wait = (milliseconds: number, signal: AbortSignal) =>
  new Promise<boolean>((resolve) => {
    const onAbort = () => {
      window.clearTimeout(timer)
      resolve(false)
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort)
      resolve(true)
    }, milliseconds)
    signal.addEventListener('abort', onAbort, { once: true })
  })

interface Options {
  activityId: string
  /** 브리핑을 만들 수 있는 대상인지 — 미팅 타입이면서 연락처가 연결돼 있어야 한다. */
  eligible: boolean
}

/**
 * 미팅 상세를 열 때 서버가 준비한 AI 브리핑을 읽는다.
 *
 * 생성과 갱신은 자료·업무 변경 트리거와 worker의 책임이다. 화면은 실행을 만들지 않는다.
 * 이전 성공본 뒤에서 갱신이 돌 때 응답의 status는 completed이고 refreshing만 true이므로,
 * status가 아니라 refreshing을 기준으로 재조회해야 한다.
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

    const controller = new AbortController()
    setBriefing(null)
    setLoading(true)
    setError(null)

    async function load() {
      let { data } = await client.get<ActivityRead>(`/activities/${activityId}`, {
        signal: controller.signal,
      })
      if (controller.signal.aborted) return

      let current = data.ai_briefing ?? null
      setBriefing(current)
      setLoading(false)

      while (current?.refreshing === true) {
        if (!(await wait(POLL_INTERVAL_MS, controller.signal))) return

        try {
          ;({ data } = await client.get<ActivityRead>(`/activities/${activityId}`, {
            signal: controller.signal,
          }))
        } catch {
          // 갱신 상태 조회가 잠깐 끊겨도 마지막 성공 본문을 가리지 않는다. 드로어가 열려
          // 있으면 같은 간격으로 다시 확인하고, 닫혔으면 아래 signal 확인으로 끝낸다.
          if (controller.signal.aborted) return
          continue
        }
        if (controller.signal.aborted) return

        current = data.ai_briefing ?? null
        setBriefing(current)
      }
    }

    load().catch((cause: unknown) => {
      if (controller.signal.aborted) return
      setError(errorMessage(cause, 'AI 브리핑을 불러오지 못했습니다.'))
      setLoading(false)
    })

    return () => {
      controller.abort()
    }
  }, [activityId, eligible])

  return { briefing, loading, error }
}
