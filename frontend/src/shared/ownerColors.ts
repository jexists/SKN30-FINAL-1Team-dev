/**
 * 담당자 이름표에 칠할 색입니다. 팀장이 팀 관리에서 정해 둔 값을 그대로 받아 둡니다.
 *
 * 이름표는 목록의 줄마다 서므로 컴포넌트마다 useTeamMembers 를 부르면 한 화면에서
 * 같은 요청이 수십 번 나갑니다. scope.ts, connectionState.ts 와 같은 방식으로 모듈 한
 * 곳에 담아 두고 처음 필요해진 때 한 번만 받습니다. 상태 관리 라이브러리는 넣지 않습니다.
 *
 * 색은 보조 정보라 못 받아도 화면을 막지 않습니다. 실패하면 빈 명부로 두어 이름표가
 * 지금과 같은 회색으로 섭니다.
 */
import { useSyncExternalStore } from 'react'

import { client } from '@/api/client'
import type { TeamMemberOption } from '@/types'

type Listener = () => void

const listeners = new Set<Listener>()

let colors: ReadonlyMap<string, string> = new Map()
let loading: Promise<void> | null = null

function emit() {
  for (const listener of listeners) listener()
}

async function load(): Promise<void> {
  try {
    const { data } = await client.get<TeamMemberOption[]>('/team-members')
    const next = new Map<string, string>()
    for (const member of data) {
      if (member.badge_color !== null) next.set(member.id, member.badge_color)
    }
    colors = next
  } catch {
    // 색을 못 받은 것뿐입니다. 목록 화면은 그대로 돌아가야 합니다.
    colors = new Map()
  } finally {
    emit()
  }
}

/** 아직 안 받았으면 한 번 받습니다. 받는 중이면 그 약속에 얹힙니다. */
function ensureLoaded() {
  if (loading !== null) return
  loading = load()
}

/** 팀 관리에서 색을 고친 뒤 부릅니다. 다시 받아 열려 있는 이름표를 갱신합니다. */
export function refreshOwnerColors(): Promise<void> {
  loading = load()
  return loading
}

/** 로그아웃. 다음 사람의 팀 색을 물려주지 않도록 비웁니다. */
export function resetOwnerColors() {
  colors = new Map()
  loading = null
  emit()
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function snapshot(): ReadonlyMap<string, string> {
  return colors
}

/**
 * 팀 전체의 색 명부입니다. 한 화면에서 여러 사람의 색을 한꺼번에 봐야 할 때 씁니다.
 *
 * 캘린더 격자처럼 담당자별 색을 줄마다 칠하고 범례까지 세우는 자리에서는, 사람마다
 * useOwnerColor 를 부르면 훅을 반복문 안에서 부르게 됩니다. 명부를 통째로 받아
 * 화면에서 찾아 씁니다.
 */
export function useOwnerColors(): ReadonlyMap<string, string> {
  ensureLoaded()
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

/**
 * 이 담당자의 이름표 색입니다. 정해 두지 않았으면 null 이고, 그때 이름표는 기본 회색입니다.
 */
export function useOwnerColor(memberId?: string): string | null {
  // 렌더 중에 부르지만 상태를 건드리지 않고 요청만 띄웁니다. 이름표가 실제로 서는
  // 화면에서만 명부를 받게 하려고 effect 대신 여기에 둡니다.
  ensureLoaded()
  const map = useSyncExternalStore(subscribe, snapshot, snapshot)
  if (memberId === undefined) return null
  return map.get(memberId) ?? null
}
