import { type ReactNode, useCallback, useMemo, useState } from 'react'

import { PROFILES, type Role, type Session, SessionContext } from './sessionContext'

// 탭을 닫으면 사라지도록 sessionStorage 를 씁니다. 실제 인증이 붙으면
// 토큰 보관 방식과 함께 다시 정해야 합니다.
const SESSION_KEY = 'salesluv.session'

function readSession(): Session | null {
  try {
    const role = sessionStorage.getItem(SESSION_KEY)
    if (role === 'manager' || role === 'member') return { role, profile: PROFILES[role] }
  } catch {
    // 사파리 프라이빗 모드 등에서 접근이 막히면 로그인 화면에서 시작합니다.
  }
  return null
}

export default function SessionProvider({ children }: { children: ReactNode }) {
  // 초기화 함수는 첫 페인트 전에 실행되므로 새로고침해도 로그인 화면이 스쳐 지나가지 않습니다.
  const [session, setSession] = useState<Session | null>(readSession)

  const login = useCallback((role: Role) => {
    try {
      sessionStorage.setItem(SESSION_KEY, role)
    } catch {
      // 저장에 실패해도 이번 세션 동안은 그대로 동작합니다.
    }
    setSession({ role, profile: PROFILES[role] })
  }, [])

  const logout = useCallback(() => {
    try {
      sessionStorage.removeItem(SESSION_KEY)
    } catch {
      // 위와 같음
    }
    setSession(null)
  }, [])

  const value = useMemo(() => ({ session, login, logout }), [session, login, logout])

  return <SessionContext value={value}>{children}</SessionContext>
}
