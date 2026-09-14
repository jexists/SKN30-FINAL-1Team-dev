import { useEffect, useState } from 'react'

const STEP_MS = 24
// 한 번에 드러낼 몫을 남은 양에서 구합니다. 고정 속도로는 안 됩니다 — 서버가
// 토큰이 아니라 본문 전체를 몇 초 간격 덩어리로 보내기 때문에(api/meetingStream.ts),
// 초당 몇 글자로 묶어 두면 화면이 서버보다 계속 뒤처집니다.
const CATCH_UP = 24

function reducedMotion() {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** 도착한 본문을 타자 치듯 드러냅니다. 값은 항상 body 의 앞부분입니다. */
export default function useStreamedText(body: string): string {
  /*
   * 처음 붙을 때 이미 와 있던 만큼은 그대로 내놓고, 그 뒤로 자란 부분만 칩니다.
   * 0 에서 시작하면 새로고침으로 다시 붙었을 때 이미 다 쓰인 본문을 처음부터
   * 다시 치게 되고, 첫 그림에서는 아무것도 없는 상태로 한 번 깜빡입니다.
   */
  const [shown, setShown] = useState(body.length)
  // 본문이 짧아지면(초안 교체·rollback) 드러낸 길이도 함께 잘립니다.
  const at = Math.min(shown, body.length)

  useEffect(() => {
    if (at >= body.length) return
    if (reducedMotion()) {
      setShown(body.length)
      return
    }
    const timer = setTimeout(() => {
      setShown(Math.min(body.length, at + Math.max(1, Math.ceil((body.length - at) / CATCH_UP))))
    }, STEP_MS)
    return () => clearTimeout(timer)
  }, [body, at])

  return body.slice(0, at)
}
