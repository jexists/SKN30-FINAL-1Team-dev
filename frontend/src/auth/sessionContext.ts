// 실제 인증이 붙기 전까지 세션은 로그인 화면의 데모 역할 버튼으로만 만들어집니다.
// 백엔드 인증이 들어오면 SessionProvider 의 login 이 API 를 호출하도록 바꾸면 됩니다.
import { createContext, useContext } from 'react'

export type Role = 'manager' | 'member'

export interface Profile {
  name: string
  title: string
}

/** 역할별 표시용 프로필. 실제 사용자 정보가 붙기 전까지 쓰는 시연 값입니다. */
export const PROFILES: Record<Role, Profile> = {
  manager: { name: '김서현', title: '영업팀장' },
  member: { name: '김지훈', title: '영업 담당자' },
}

export interface Session {
  role: Role
  profile: Profile
}

export interface SessionContextValue {
  session: Session | null
  login: (role: Role) => void
  logout: () => void
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
