/**
 * 화면이 바뀐 뒤에도 남아야 하는 성공·실패 안내를 앱 전체가 공유합니다.
 * 저장소가 목록을 들고, 호스트 하나가 App 에 붙어 그립니다.
 *
 * 상태 관리 라이브러리를 새로 넣지 않습니다. connectionState 와 같은 방식입니다.
 */

export interface ToastItem {
  id: number
  message: string
  tone: 'success' | 'error'
  persistent: boolean
  to?: string
  actionLabel?: string
}

/** 일반 안내가 보이는 시간. 작업 완료·실패 알림은 사용자가 닫을 때까지 남습니다. */
const LIFETIME = 3000

let items: ToastItem[] = []
let nextId = 1
const listeners = new Set<() => void>()
const timers = new Map<number, ReturnType<typeof setTimeout>>()

function notify() {
  for (const listener of listeners) listener()
}

export function subscribeToasts(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/**
 * 같은 배열 참조를 돌려줍니다.
 *
 * useSyncExternalStore 는 스냅샷을 참조로 비교하므로, 매번 새 배열을 만들면
 * 바뀐 것이 없어도 무한히 다시 그립니다. 바뀔 때만 items 를 교체합니다.
 */
export function getToasts(): ToastItem[] {
  return items
}

export function showToast(
  message: string,
  options: {
    tone?: ToastItem['tone']
    persistent?: boolean
    to?: string
    actionLabel?: string
  } = {},
) {
  const id = nextId++
  const item: ToastItem = {
    id,
    message,
    tone: options.tone ?? 'success',
    persistent: options.persistent ?? false,
    ...(options.to && options.actionLabel
      ? { to: options.to, actionLabel: options.actionLabel }
      : {}),
  }
  items = [...items, item]
  notify()
  if (!item.persistent)
    timers.set(
      id,
      setTimeout(() => dismissToast(id), LIFETIME),
    )
  return id
}

export function dismissToast(id: number) {
  clearTimeout(timers.get(id))
  timers.delete(id)
  const next = items.filter((item) => item.id !== id)
  // 이미 손으로 닫은 뒤 타이머가 뒤늦게 도착하는 일이 흔합니다. 그때 헛되이
  // 알리면 화면만 다시 그립니다.
  if (next.length === items.length) return
  items = next
  notify()
}
