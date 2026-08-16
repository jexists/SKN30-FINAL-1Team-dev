// 알림 도메인. 헤더 벨의 안 읽음 표시와 알림 화면이 같은 목록을 봐야 해서
// shared/counters.ts 의 CS 스토어와 같은 방식으로 목록을 여기 하나에 둡니다.
//
// 백엔드가 붙는 지점은 markRead / removeNotification 둘입니다. 저장은 메모리에만 합니다.
import { useSyncExternalStore } from 'react'

import { notificationSeed } from '@/mocks'
import type { AppNotification } from '@/types'

/** 최근에 온 것이 위로 옵니다. 같은 날이면 시각이 늦은 것이 위입니다. */
let items: AppNotification[] = [...notificationSeed].sort(
  (a, b) => b.postedOff - a.postedOff || b.postedAt.localeCompare(a.postedAt),
)

const listeners = new Set<() => void>()

function commit(next: AppNotification[]) {
  items = next
  for (const notify of listeners) notify()
}

function subscribe(notify: () => void) {
  listeners.add(notify)
  return () => {
    listeners.delete(notify)
  }
}

function snapshot(): AppNotification[] {
  return items
}

export function markRead(id: string) {
  if (items.find((n) => n.id === id)?.read) return // 이미 읽었으면 다시 그리지 않습니다.
  commit(items.map((n) => (n.id === id ? { ...n, read: true } : n)))
}

export function removeNotification(id: string) {
  commit(items.filter((n) => n.id !== id))
}

/** 목록이 바뀌면 다시 그립니다. */
export function useNotifications(): AppNotification[] {
  return useSyncExternalStore(subscribe, snapshot)
}

/** 헤더 벨의 점. 숫자는 세어 봐야 할 일이 달라지지 않아 있는지만 봅니다. */
export function useHasUnread(): boolean {
  return useNotifications().some((n) => !n.read)
}
