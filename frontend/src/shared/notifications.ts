import type { AppNotification } from '@/types'

export const NOTIFICATION_API_ERROR = '알림 조회 API가 백엔드에 제공되지 않습니다.'

const EMPTY_NOTIFICATIONS: AppNotification[] = []

export function markRead(_id: string) {
  // 알림 API가 추가되기 전에는 변경할 서버 데이터가 없습니다.
}

export function removeNotification(_id: string) {
  // 알림 API가 추가되기 전에는 변경할 서버 데이터가 없습니다.
}

export function useNotifications(): AppNotification[] {
  return EMPTY_NOTIFICATIONS
}

export function useHasUnread(): boolean {
  return false
}
