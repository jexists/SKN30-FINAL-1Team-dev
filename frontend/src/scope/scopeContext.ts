// 지금 화면이 누구의 데이터를 보여주는가. 팀장은 Topbar 스위처로 고르고,
// 팀원에게는 늘 자기 자신으로 고정됩니다.
//
// 페이지별 필터(q·owner·range)와 달리 주소에 두지 않습니다. 스코프는 화면을 옮겨
// 다녀도 유지되는 세션 성격의 값이라 URL 에 두면 링크마다 따라 붙어야 합니다.
import { createContext, useContext, useMemo } from 'react'

import { useCurrentUser } from '@/auth/sessionContext'
import { findMemberById, TEAM } from '@/shared/team'

/** 로그인한 본인. 이름이 아니라 자리로 두어야 다른 사람이 로그인해도 그대로 맞습니다. */
export const SCOPE_ME = 'me'

/**
 * 고른 사람들. 각 항목은 SCOPE_ME 또는 TeamMember.id 입니다.
 * 빈 배열이 '팀 전체'입니다 — 아무도 안 골랐다는 뜻과 전부 본다는 뜻이 같습니다.
 */
export type Scope = string[]

export const SCOPE_TEAM: Scope = []

export interface ScopeContextValue {
  scope: Scope
  setScope: (scope: Scope) => void
}

export const ScopeContext = createContext<ScopeContextValue | null>(null)

export interface OwnerScope {
  scope: Scope
  setScope: (scope: Scope) => void
  /** 지금 보여야 할 담당자 이름 목록 */
  owners: string[]
  matchesOwner: (owner: string) => boolean
  /** 아무도 고르지 않은 상태. 팀 전체를 봅니다. */
  isTeamView: boolean
  /**
   * 담당자를 화면에 밝혀야 하는가. 둘 이상이 섞여 있을 때만 "누구 것인지"가 정보입니다.
   * 한 사람만 보고 있으면 모든 줄의 담당자가 같아 열이든 필터든 자리만 차지합니다.
   */
  showOwner: boolean
}

/**
 * 목록을 거를 때 씁니다. 기존 조건보다 먼저 통과시켜야
 * 스코프 밖의 건이 검색·정렬 결과에 섞이지 않습니다.
 */
export function useOwnerScope(): OwnerScope {
  const value = useContext(ScopeContext)
  if (!value) throw new Error('useOwnerScope 는 ScopeProvider 안에서만 쓸 수 있습니다.')

  const { scope, setScope } = value
  const { profile } = useCurrentUser()

  return useMemo(() => {
    const owners =
      scope.length === 0
        ? TEAM.filter((member) => member.active).map((member) => member.name)
        : // 같은 사람을 두 번 세지 않도록 Set 을 거칩니다. '내 현황'과 자기 이름이
          // 함께 골라지는 경우가 있습니다.
          [
            ...new Set(
              scope.map((id) => (id === SCOPE_ME ? profile.name : findMemberById(id)?.name)),
            ),
          ].filter((name) => name !== undefined)

    return {
      scope,
      setScope,
      owners,
      matchesOwner: (owner: string) => owners.includes(owner),
      isTeamView: scope.length === 0,
      showOwner: owners.length > 1,
    }
  }, [scope, setScope, profile.name])
}
