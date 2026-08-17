import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { clearProfileId, profile as mockProfile, readProfileId, writeProfileId } from '@/mocks'
import { clearScope } from '@/scope/scopeStorage'

import { type Session, SessionContext } from './sessionContext'

interface AuthUser {
  id: string
  display_name: string
  role_code: Session['role']
  job_title: string | null
}

const PROFILE_ID_BY_ROLE: Record<Session['role'], string> = {
  manager: 'sample-manager',
  member: 'sample-member',
}

const toSession = ({ display_name, role_code, job_title }: AuthUser): Session => ({
  role: role_code,
  profile: { name: display_name, title: job_title ?? '' },
})

/** 인증과 무관한 합성 데이터 선택값만 실제 역할에 맞춥니다. */
function syncMockProfile(role: Session['role']): 'ready' | 'reload' | 'failed' {
  const expectedId = PROFILE_ID_BY_ROLE[role]
  if (readProfileId() !== expectedId) writeProfileId(expectedId)

  if (mockProfile.id === expectedId) return 'ready'
  return readProfileId() === expectedId ? 'reload' : 'failed'
}

export default function SessionProvider({ children }: { children: ReactNode }) {
  // undefined 는 서버 세션 복원 중입니다. 이때 라우트를 렌더하면 로그인 화면으로 잘못 튕깁니다.
  const [session, setSession] = useState<Session | null>()
  const [restoreFailed, setRestoreFailed] = useState(false)

  useEffect(() => {
    let active = true

    client
      .get<AuthUser>('/auth/me')
      .then(({ data }) => {
        if (!active) return
        const next = toSession(data)
        const mockSync = syncMockProfile(next.role)
        if (mockSync === 'reload') {
          window.location.reload()
          return
        }
        if (mockSync === 'failed') {
          setRestoreFailed(true)
          return
        }
        setSession(next)
      })
      .catch((error: unknown) => {
        if (!active) return
        if (isAxiosError(error) && error.response?.status === 401) {
          setSession(null)
          return
        }
        setRestoreFailed(true)
      })

    return () => {
      active = false
    }
  }, [])

  const login = useCallback(async (loginId: string, password: string) => {
    const { data } = await client.post<AuthUser>('/auth/login', {
      login_id: loginId,
      password,
    })
    const next = toSession(data)
    clearScope()
    const mockSync = syncMockProfile(next.role)
    if (mockSync === 'reload') {
      window.location.reload()
      return
    }
    if (mockSync === 'failed') {
      await client.post('/auth/logout')
      throw new Error('mock profile storage unavailable')
    }
    setSession(next)
  }, [])

  const logout = useCallback(async () => {
    try {
      await client.post('/auth/logout')
    } catch {
      return
    }
    clearProfileId()
    clearScope()
    setSession(null)
  }, [])

  if (restoreFailed) {
    return (
      <main role="alert">
        서버에 연결할 수 없습니다.{' '}
        <button type="button" onClick={() => window.location.reload()}>
          다시 시도
        </button>
      </main>
    )
  }
  if (session === undefined) return null

  return <SessionContext value={{ session, login, logout }}>{children}</SessionContext>
}
