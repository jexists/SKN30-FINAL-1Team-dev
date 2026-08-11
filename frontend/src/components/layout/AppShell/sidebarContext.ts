// 사이드바 상태는 두 개이고 서로 독립입니다.
//
//   collapsed  — 데스크톱 아이콘 레일. 사용자가 직접 접은 것이라 localStorage 에 남깁니다.
//   mobileOpen — 모바일 오프캔버스 드로어. 이동하면 닫히므로 저장하지 않습니다.
//
// 어느 쪽이 화면에 의미를 갖는지는 CSS 미디어쿼리가 정합니다.
// 그래서 "지금 모바일인가"를 JS 로 판단할 필요가 거의 없습니다.
import { createContext, useContext } from 'react'

export interface SidebarContextValue {
  collapsed: boolean
  toggleCollapsed: () => void
  mobileOpen: boolean
  openMobile: () => void
  closeMobile: () => void
}

export const SidebarContext = createContext<SidebarContextValue | null>(null)

export function useSidebar(): SidebarContextValue {
  const value = useContext(SidebarContext)
  if (!value) throw new Error('useSidebar 는 AppShell 안에서만 쓸 수 있습니다.')
  return value
}
