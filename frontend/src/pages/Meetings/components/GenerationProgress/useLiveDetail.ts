import { useEffect, useRef, useState } from 'react'

const TICK_MS = 1000
// 문구가 넘어가는 간격. 읽을 만큼은 머물러야 하고, 멈춘 것처럼 보이지 않아야 합니다.
const PHRASE_TICKS = 4

function reducedMotion() {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 살아 있는 줄이 얼마나 오래 서 있었는지와, 지금 보여 줄 문구를 냅니다.
 *
 * 분석 단계는 몇십 초씩 걸리는데 그동안 서버가 보내 줄 중간 결과가 없습니다. 초는 실제로
 * 흐른 시간이고, 문구는 그 단계가 실제로 하는 일들입니다 — 단계 밖의 일은 넣지 않습니다.
 *
 * @param key 살아 있는 단계를 가리키는 값. 바뀌면 초와 문구가 처음부터 다시 셉니다.
 */
export default function useLiveDetail(key: string, phrases: string[]) {
  const [ticks, setTicks] = useState(0)
  const since = useRef(key)
  if (since.current !== key) {
    since.current = key
    // 렌더 중에 되돌립니다. 단계가 바뀐 첫 그림에서 이전 단계의 초가 잠깐 비치지 않습니다.
    if (ticks !== 0) setTicks(0)
  }

  useEffect(() => {
    const timer = setInterval(() => setTicks((count) => count + 1), TICK_MS)
    return () => clearInterval(timer)
  }, [key])

  // 초는 애니메이션이 아니라 정보라 계속 셉니다. 돌아가는 문구만 멈춥니다.
  const at =
    phrases.length && !reducedMotion() ? Math.floor(ticks / PHRASE_TICKS) % phrases.length : 0
  return { seconds: ticks, phrase: phrases[at] }
}
