// AI 가 보고서를 쓰는 동안 지금 어디쯤인지 말해 주는 단계 표시.
//
// 서버는 queued / running / completed 세 가지만 알려 줍니다. 그래서 퍼센트를 만들지
// 않습니다 — 근거 없는 숫자는 "87% 에서 멈췄다" 는 오해만 만듭니다. 대신 실행이
// 시작됐다는 사실(running)과 흐른 시간으로 문구만 넘깁니다.
//
// 마지막 단계에서는 멈춥니다. 끝나지도 않았는데 "다 됐다" 고 말하지 않기 위해서입니다.
import { useCallback, useEffect, useState } from 'react'

import type { AgentRunStatus } from '@/types'

export const GENERATION_STEPS = [
  '자료를 분석하는 중입니다',
  '내용을 구성하는 중입니다',
  '보고서를 정리하는 중입니다',
] as const

/** 다음 단계로 넘어가는 시점. 실제 실행은 대개 10~30초 걸립니다. */
const STEP_AT_MS = [6_000, 15_000]

export default function useGenerationSteps(active: boolean) {
  const [step, setStep] = useState(0)

  useEffect(() => {
    setStep(0)
    if (!active) return

    const timers = STEP_AT_MS.map((delay, at) =>
      window.setTimeout(() => setStep((now) => Math.max(now, at + 1)), delay),
    )
    return () => timers.forEach((timer) => window.clearTimeout(timer))
  }, [active])

  /**
   * 서버가 말한 상태를 반영합니다. 실행이 시작됐으면 최소한 '내용을 구성하는 중' 입니다.
   * 뒤로 돌리지는 않습니다 — 문구가 앞뒤로 오가면 진행 중이라는 인상 자체가 깨집니다.
   */
  const onStatus = useCallback((status: AgentRunStatus) => {
    if (status === 'running') setStep((now) => Math.max(now, 1))
  }, [])

  return { step, onStatus }
}
