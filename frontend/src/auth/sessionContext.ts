import { createContext, useContext } from 'react'

import type { Role } from '@/types'

export interface Profile {
  name: string
  title: string
}

export interface Session {
  role: Role
  profile: Profile
}

/**
 * 세션 판정 결과입니다.
 *
 * - `loading`: 아직 서버에 물어보는 중입니다.
 * - `authenticated`: 백엔드가 확인해 준 세션이 있습니다.
 * - `unauthenticated`: 로그인하지 않았거나 연결된 구성원이 없습니다.
 * - `unavailable`: 백엔드에 닿지 못했습니다. 로그인하지 않은 것과 다릅니다.
 */
export type SessionStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'unavailable'

export interface SessionContextValue {
  session: Session | null
  status: SessionStatus
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const SessionContext = createContext<SessionContextValue | null>(null)

/** 로그인 전후 어디서나 쓸 수 있습니다. session 이 null 일 수 있습니다. */
export function useSession(): SessionContextValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession 은 SessionProvider 안에서만 쓸 수 있습니다.')
  return value
}

/**
 * 로그인이 보장된 화면 전용입니다.
 *
 * ProtectedRoute 안에서만 렌더되는 컴포넌트가 매번 null 검사를 하지 않도록
 * useSession 과 분리했습니다.
 */
export function useCurrentUser(): Session & { isManager: boolean } {
  const { session } = useSession()
  if (!session) throw new Error('useCurrentUser 는 로그인된 화면에서만 쓸 수 있습니다.')
  return { ...session, isManager: session.role === 'manager' }
}
