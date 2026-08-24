/**
 * 성공·완료를 알리는 짧은 안내를 앱 전체가 공유하는 최소 저장소입니다.
 *
 * 오류는 ErrorToast 가 맡습니다. 그쪽은 화면이 들고 있는 오류 문구를 그대로
 * 그리는 선언형이라, 모달이 닫히며 사라지는 성공 알림에는 맞지 않습니다.
 * 여기서는 부르는 쪽이 화면에서 사라진 뒤에도 안내가 남아야 하므로
 * 저장소가 목록을 들고, 호스트 하나가 App 에 붙어 그립니다.
 *
 * 상태 관리 라이브러리를 새로 넣지 않습니다. connectionState 와 같은 방식입니다.
 */

export interface ToastItem {
  id: number
  message: string
}

/** 보이는 시간. 짧은 한 문장을 읽고도 남을 만큼입니다. */
const LIFETIME = 3000

let items: ToastItem[] = []
let nextId = 1
const listeners = new Set<() => void>()

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

export function showToast(message: string) {
  const id = nextId++
  items = [...items, { id, message }]
  notify()
  setTimeout(() => dismissToast(id), LIFETIME)
}

export function dismissToast(id: number) {
  const next = items.filter((item) => item.id !== id)
  // 이미 손으로 닫은 뒤 타이머가 뒤늦게 도착하는 일이 흔합니다. 그때 헛되이
  // 알리면 화면만 다시 그립니다.
  if (next.length === items.length) return
  items = next
  notify()
}
