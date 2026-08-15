import { type ReactNode, useCallback, useMemo, useState } from 'react'

import { ROUTES } from '@/constants/routes'
import { clearProfileId, readProfileId, writeProfileId } from '@/mocks'
import { findProfile } from '@/mocks/profiles'
import { clearScope } from '@/scope/scopeStorage'

import { type Session, SessionContext } from './sessionContext'

// 세션은 고른 데모 프로필 자체입니다. 탭을 닫으면 사라지도록 sessionStorage 에 두며,
// 읽고 쓰는 자리는 mocks/ 한 곳입니다 — 시드를 고르는 것과 같은 값이라야 하기 때문입니다.
function readSession(): Session | null {
  const id = readProfileId()
  if (id === null) return null
  const { role, name, title } = findProfile(id)
  return { role, profile: { name, title } }
}

export default function SessionProvider({ children }: { children: ReactNode }) {
  // 초기화 함수는 첫 페인트 전에 실행되므로 새로고침해도 로그인 화면이 스쳐 지나가지 않습니다.
  const [session, setSession] = useState<Session | null>(readSession)

  const login = useCallback((profileId: string) => {
    writeProfileId(profileId)
    // 앞사람이 보던 범위가 다음 로그인에 남지 않도록 지웁니다.
    clearScope()
    // 목업 시드는 모듈이 로드될 때 프로필에 맞춰 확정됩니다. setState 로는 이미 만들어진
    // 데이터셋이 바뀌지 않으므로 프로필을 저장한 뒤 통째로 새로고침합니다.
    window.location.assign(ROUTES.DASHBOARD)
  }, [])

  const logout = useCallback(() => {
    clearProfileId()
    clearScope()
    setSession(null)
  }, [])

  const value = useMemo(() => ({ session, login, logout }), [session, login, logout])

  return <SessionContext value={value}>{children}</SessionContext>
}
