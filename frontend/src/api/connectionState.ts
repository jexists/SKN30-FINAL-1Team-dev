/**
 * 백엔드에 닿지 못하는 상태를 앱 전체가 공유하는 최소 저장소입니다.
 *
 * 페이지마다 연결 실패를 따로 판정하면 안내가 어긋나므로, 인터셉터 한 곳에서만
 * 값을 바꾸고 화면은 구독만 합니다. 상태 관리 라이브러리를 새로 넣지 않습니다.
 */

type Listener = () => void

let unreachable = false
// 실패할 때마다 올라갑니다. 안내를 닫은 뒤 새로 실패했는지 구분하는 유일한 단서입니다.
let failureCount = 0
const listeners = new Set<Listener>()

function notify() {
  for (const listener of listeners) listener()
}

export function subscribeConnection(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getConnectionUnreachable(): boolean {
  return unreachable
}

export function getConnectionFailureCount(): number {
  return failureCount
}

/**
 * 이미 실패 상태여도 매번 알립니다.
 *
 * 첫 실패에서만 알리면, 사용자가 안내를 닫은 뒤로는 계속 실패해도 화면이
 * 조용해집니다. 복구되기 전에는 markReachable 이 불릴 일도 없어서 영영
 * 닫힌 채로 남습니다.
 */
export function markUnreachable() {
  unreachable = true
  failureCount += 1
  notify()
}

/** 응답이 한 번이라도 정상으로 돌아오면 해제합니다. */
export function markReachable() {
  if (!unreachable) return
  unreachable = false
  notify()
}

/**
 * 세션이 서버 기준으로 끊겼음을 알립니다.
 *
 * 인터셉터는 SessionProvider 를 직접 알지 못하므로 이 구독으로만 전달합니다.
 */
const sessionExpiredListeners = new Set<Listener>()

export function subscribeSessionExpired(listener: Listener): () => void {
  sessionExpiredListeners.add(listener)
  return () => {
    sessionExpiredListeners.delete(listener)
  }
}

export function notifySessionExpired() {
  for (const listener of sessionExpiredListeners) listener()
}
