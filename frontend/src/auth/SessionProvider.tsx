import { type ReactNode, useCallback, useEffect, useState } from 'react'
import { isAxiosError } from 'axios'

import { client } from '@/api/client'
import { subscribeSessionExpired } from '@/api/connectionState'
import { clearProfileId, profile as mockProfile, readProfileId, writeProfileId } from '@/mocks'
import { clearScope } from '@/scope/scopeStorage'

import { type Session, SessionContext, type SessionStatus } from './sessionContext'
import { clearSignedInHint, hasSignedInHint } from './signedInHint'

interface AuthUser {
  id: string
  team_id: string
  display_name: string
  role_code: Session['role']
  job_title: string | null
}

const FILLED_TEAM_ID = '6d0f1b76-6b1a-4b72-9ba3-1df477a62d78'
const EMPTY_TEAM_ID = 'dc153ea5-9ba6-4b96-a4df-845a44798003'
const TEST_TEAM_ID = '95d7978d-5281-45fa-9412-14db072f5c01'

const PROFILE_ID_BY_TEAM_AND_ROLE: Record<string, Record<Session['role'], string>> = {
  [FILLED_TEAM_ID]: {
    manager: 'sample-manager',
    member: 'sample-member',
  },
  [EMPTY_TEAM_ID]: {
    manager: 'empty-manager',
    member: 'empty-member',
  },
  // 테스트팀도 데이터가 없는 팀이라 첫 세팅 팀과 같은 목업 프로필을 씁니다.
  [TEST_TEAM_ID]: {
    manager: 'empty-manager',
    member: 'empty-member',
  },
}

const toSession = ({ display_name, role_code, job_title }: AuthUser): Session => ({
  role: role_code,
  profile: { name: display_name, title: job_title ?? '' },
})

function resolveMockProfileId(teamId: string, role: Session['role']): string | undefined {
  return PROFILE_ID_BY_TEAM_AND_ROLE[teamId]?.[role]
}

/** 인증과 무관한 합성 데이터 선택값만 실제 역할에 맞춥니다. */
function syncMockProfile(user: AuthUser): 'ready' | 'reload' | 'failed' {
  const expectedId = resolveMockProfileId(user.team_id, user.role_code)
  if (expectedId === undefined) return 'failed'

  if (readProfileId() !== expectedId) {
    clearScope()
    writeProfileId(expectedId)
  }

  if (mockProfile.id === expectedId) return 'ready'
  return readProfileId() === expectedId ? 'reload' : 'failed'
}

export default function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [status, setStatus] = useState<SessionStatus>('loading')
  // 합성 데이터 저장 실패는 백엔드 장애가 아니므로 연결 상태와 섞지 않습니다.
  const [mockUnavailable, setMockUnavailable] = useState(false)

  useEffect(() => {
    let active = true

    // 로그인한 적이 없으면 물어볼 세션도 없습니다. 백엔드를 부르지 않습니다.
    if (!hasSignedInHint()) {
      setStatus('unauthenticated')
      return
    }

    client
      .get<AuthUser>('/auth/me')
      .then(({ data }) => {
        if (!active) return
        const mockSync = syncMockProfile(data)
        if (mockSync === 'reload') {
          window.location.reload()
          return
        }
        if (mockSync === 'failed') {
          setMockUnavailable(true)
          setStatus('unauthenticated')
          return
        }
        setSession(toSession(data))
        setStatus('authenticated')
      })
      .catch((error: unknown) => {
        if (!active) return
        if (!isAxiosError(error)) {
          setStatus('unavailable')
          return
        }
        const responseStatus = error.response?.status
        // 401 은 정상적인 비로그인, 403 은 연결되지 않은 계정입니다. 둘 다 장애가 아닙니다.
        if (responseStatus === 401 || responseStatus === 403) {
          // 서버 세션이 이미 끝났으므로 다음 진입부터는 묻지 않습니다.
          clearSignedInHint()
          setStatus('unauthenticated')
          return
        }
        // 닿지 못한 것뿐이라 표시는 남깁니다. 복구되면 다시 확인해야 합니다.
        setStatus('unavailable')
      })

    return () => {
      active = false
    }
  }, [])

  // 갱신까지 실패하면 화면에 남아 있던 세션을 내립니다.
  useEffect(
    () =>
      subscribeSessionExpired(() => {
        clearSignedInHint()
        setSession(null)
        setStatus('unauthenticated')
      }),
    [],
  )

  const login = useCallback(async (email: string, password: string) => {
    // 로그인 응답이 세션 표시 쿠키까지 함께 설정하므로, 아래 reload 를 타도
    // 다시 뜬 앱이 세션을 되찾을 수 있습니다.
    const { data } = await client.post<AuthUser>('/auth/login', { email, password })
    clearScope()
    const mockSync = syncMockProfile(data)
    if (mockSync === 'reload') {
      window.location.reload()
      return
    }
    if (mockSync === 'failed') {
      await client.post('/auth/logout').catch(() => undefined)
      clearSignedInHint()
      setMockUnavailable(true)
      throw new Error('mock profile storage unavailable')
    }
    setMockUnavailable(false)
    setSession(toSession(data))
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    // 서버 호출이 실패해도 이 브라우저의 로그인 상태는 반드시 내립니다.
    // 실패는 인터셉터가 먼저 잡아 연결 실패 모달로 알립니다.
    await client.post('/auth/logout').catch(() => undefined)
    clearSignedInHint()
    clearProfileId()
    clearScope()
    setSession(null)
    setStatus('unauthenticated')
  }, [])

  return (
    <SessionContext value={{ session, status, mockUnavailable, login, logout }}>
      {children}
    </SessionContext>
  )
}
