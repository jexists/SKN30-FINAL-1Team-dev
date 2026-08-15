// 스코프 보관. 세션과 같은 수명을 갖도록 sessionStorage 를 씁니다.
//
// auth 쪽에서 로그아웃 때 지울 수 있도록 컨텍스트와 분리해 두었습니다.
// 이 파일은 auth 를 참조하지 않습니다.
import { findMemberById } from '@/shared/team'

import { type Scope, SCOPE_ME } from './scopeContext'

const SCOPE_KEY = 'salesluv.scope'

const isKnown = (id: unknown): id is string =>
  typeof id === 'string' && (id === SCOPE_ME || findMemberById(id) !== undefined)

/**
 * 저장된 값이 없거나 읽을 수 없으면 null. 호출한 쪽이 기본값을 정합니다.
 * 명부에서 사라진 사람은 조용히 버립니다 — 남겨 두면 아무것도 안 걸리는 범위가 됩니다.
 */
export function readScope(): Scope | null {
  try {
    const saved = sessionStorage.getItem(SCOPE_KEY)
    if (saved === null) return null
    const parsed: unknown = JSON.parse(saved)
    if (!Array.isArray(parsed)) return null
    return parsed.filter(isKnown)
  } catch {
    // 사파리 프라이빗 모드나 깨진 값이면 기본 스코프로 시작합니다.
    return null
  }
}

export function writeScope(scope: Scope) {
  try {
    sessionStorage.setItem(SCOPE_KEY, JSON.stringify(scope))
  } catch {
    // 저장에 실패해도 이번 세션 동안은 그대로 동작합니다.
  }
}

export function clearScope() {
  try {
    sessionStorage.removeItem(SCOPE_KEY)
  } catch {
    // 위와 같음
  }
}
