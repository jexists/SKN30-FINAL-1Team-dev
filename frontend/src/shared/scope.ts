/**
 * 앱 전체가 공유하는 보기 범위입니다. Topbar 의 스위처가 고르고 모든 목록 화면이 따릅니다.
 *
 * 페이지마다 따로 들면 메뉴를 옮길 때마다 범위가 풀리므로 모듈 한 곳에 둡니다.
 * agenda.ts, connectionState.ts 와 같은 방식이고 상태 관리 라이브러리를 새로 넣지 않습니다.
 *
 * 여기서 정하는 것은 "무엇을 보여줄지" 뿐입니다. "무엇을 볼 수 있는지" 는 백엔드가
 * 정합니다. 화면이 보낸 담당자 목록은 서버가 매번 같은 팀인지 다시 확인합니다.
 */
import { useSyncExternalStore } from 'react'

/**
 * `users` 는 고른 사람들입니다. 본인도 그 안에 들어갑니다.
 *
 * '내 현황' 을 따로 둔 모드로 만들면 본인과 팀원을 함께 볼 수 없습니다. 화면의 '내 현황'
 * 은 본인을 가리키는 한 줄일 뿐이고, 팀원 줄과 똑같이 켜고 끕니다. 배타적인 것은
 * '팀 전체' 하나뿐입니다.
 */
export type ScopeMode = 'all' | 'users'

export interface Scope {
  mode: ScopeMode
  memberIds: readonly string[]
}

interface StoredScope {
  mode: ScopeMode
  memberIds: string[]
}

type Listener = () => void

const STORAGE_PREFIX = 'salesluv.scope.'
const NO_MEMBERS: readonly string[] = []

const ALL: Scope = { mode: 'all', memberIds: NO_MEMBERS }

let scope: Scope = ALL
let ownMemberId: string | null = null
let isManager = false

// 커밋할 때마다 다시 계산해 둡니다. useSyncExternalStore 는 렌더마다 같은 참조를
// 돌려받아야 하므로 getSnapshot 안에서 새 배열을 만들면 안 됩니다.
let ownerIds: readonly string[] | undefined
let scopeKey = 'all'

const listeners = new Set<Listener>()

function storageKey(memberId: string): string {
  return `${STORAGE_PREFIX}${memberId}`
}

/**
 * 서버로 보낼 담당자 목록입니다. undefined 는 "담당자를 좁히지 않는다" 는 뜻이고,
 * axios 가 알아서 파라미터를 뺍니다.
 *
 * 팀원이면 모드와 상관없이 언제나 undefined 입니다. 백엔드는 팀원이 담당자 파라미터를
 * 보내는 것 자체를 거절하므로(scope_not_allowed), 하나라도 실어 보내면 모든 목록이
 * 403 이 됩니다. 저장소를 손으로 고쳐도 여기서 역할을 다시 보기 때문에 통과하지 못합니다.
 */
function computeOwnerIds(): readonly string[] | undefined {
  if (!isManager || ownMemberId === null) return undefined
  return scope.mode === 'all' ? undefined : scope.memberIds
}

function computeScopeKey(): string {
  if (!isManager || ownMemberId === null) return 'all'
  return scope.mode === 'all' ? 'all' : `users:${scope.memberIds.join(',')}`
}

function persist() {
  // 팀원의 범위는 고정이라 남길 것이 없습니다.
  if (!isManager || ownMemberId === null) return
  const value: StoredScope = { mode: scope.mode, memberIds: [...scope.memberIds] }
  try {
    localStorage.setItem(storageKey(ownMemberId), JSON.stringify(value))
  } catch {
    // 사파리 비공개 모드처럼 저장이 막힌 환경입니다. 이번 세션 안에서는 그대로 동작합니다.
  }
}

function read(memberId: string): Scope | null {
  try {
    const raw = localStorage.getItem(storageKey(memberId))
    if (raw === null) return null
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return null
    const { mode, memberIds } = parsed as Partial<StoredScope>
    if (mode === 'all') return ALL
    if (mode !== 'users') return null
    if (!Array.isArray(memberIds)) return null
    const ids = memberIds.filter((id): id is string => typeof id === 'string')
    return ids.length === 0 ? null : { mode: 'users', memberIds: ids }
  } catch {
    return null
  }
}

function commit(next: Scope, { save = true } = {}) {
  scope = next
  ownerIds = computeOwnerIds()
  scopeKey = computeScopeKey()
  if (save) persist()
  for (const listener of listeners) listener()
}

/**
 * 로그인한 사람에 맞춰 범위를 세웁니다.
 *
 * 저장 키가 구성원마다 다르므로 다른 계정으로 로그인해도 앞 사람의 선택을 물려받지
 * 않습니다. 기본값은 팀장이 팀 전체, 팀원이 내 현황입니다.
 */
export function initScope(memberId: string, manager: boolean) {
  ownMemberId = memberId
  isManager = manager
  // 팀원은 늘 본인 것만 봅니다. 서버가 그렇게 좁히므로 여기서는 좁히지 않는 상태로 둡니다.
  commit(manager ? (read(memberId) ?? ALL) : ALL, { save: false })
}

/** 로그아웃. 저장 키는 구성원별이라 지우지 않고 메모리 상태만 내립니다. */
export function resetScope() {
  ownMemberId = null
  isManager = false
  commit(ALL, { save: false })
}

export function subscribeScope(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function scopeSnapshot(): Scope {
  return scope
}

/** agenda.ts 처럼 훅 밖에서 읽어야 하는 곳을 위한 통로입니다. */
export function getScopeOwnerIds(): readonly string[] | undefined {
  return ownerIds
}

export function getScopeKey(): string {
  return scopeKey
}

export function getOwnMemberIds(): readonly string[] | undefined {
  return isManager && ownMemberId !== null ? [ownMemberId] : undefined
}

export function setScopeAll() {
  if (scope.mode !== 'all') commit(ALL)
}

/**
 * 고른 사람을 통째로 바꿉니다.
 *
 * 어떤 집합이 되어야 하는지는 팀 명부를 아는 화면이 정합니다. 스토어는 명부를 들고
 * 있지 않아서 '팀 전체에서 한 명만 빼기' 같은 계산을 여기서 할 수 없습니다.
 * 빈 목록은 보여 줄 것이 없다는 뜻이라 팀 전체로 되돌립니다.
 */
export function setScopeMembers(memberIds: readonly string[]) {
  const next = [...new Set(memberIds)]
  commit(next.length === 0 ? ALL : { mode: 'users', memberIds: next })
}

/**
 * 팀에서 빠지거나 비활성화된 사람을 선택에서 덜어냅니다.
 *
 * 저장해 둔 선택을 그대로 보내면 서버가 "지금 팀에 없는 사람" 이라며 목록 전체를
 * 거절합니다. 팀원 목록을 받은 뒤 한 번 맞춰 둡니다.
 */
export function reconcileScope(availableIds: readonly string[]) {
  if (scope.mode !== 'users') return
  const next = scope.memberIds.filter((id) => availableIds.includes(id))
  if (next.length === scope.memberIds.length) return
  commit(next.length === 0 ? ALL : { mode: 'users', memberIds: next })
}

export function useScope(): Scope {
  return useSyncExternalStore(subscribeScope, scopeSnapshot, scopeSnapshot)
}

/** 목록을 부르는 모든 훅이 쓰는 하나뿐인 입구입니다. */
export function useScopeOwnerIds(): readonly string[] | undefined {
  return useSyncExternalStore(subscribeScope, getScopeOwnerIds, getScopeOwnerIds)
}

/**
 * 범위가 바뀐 것을 effect 가 알아채는 값입니다.
 *
 * 배열이 아니라 문자열에 기대는 까닭은, 같은 선택인데 참조만 달라져서 effect 가
 * 다시 도는 일을 막기 위해서입니다. 화면마다 쓰던 reloadKey 와 같은 역할입니다.
 */
export function useScopeKey(): string {
  return useSyncExternalStore(subscribeScope, getScopeKey, getScopeKey)
}
