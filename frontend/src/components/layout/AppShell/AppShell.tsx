import { useCallback, useEffect, useMemo, useState } from 'react'
import { Outlet, useLocation } from 'react-router'

import Scrim from '@/components/layout/Scrim'
import Sidebar from '@/components/layout/Sidebar'
import Topbar from '@/components/layout/Topbar'
import { BP_DESKTOP } from '@/constants/breakpoints'
import useMediaQuery from '@/hooks/useMediaQuery'

import { SidebarContext } from './sidebarContext'

import styles from './AppShell.module.scss'

const COLLAPSED_KEY = 'salesluv.sidebar.collapsed'

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === '1'
  } catch {
    // 사파리 프라이빗 모드 등에서 localStorage 접근이 막히면 펼친 상태로 시작합니다.
    return false
  }
}

export default function AppShell() {
  // 초기화 함수는 첫 페인트 전에 실행되므로 접힌 상태로 새로고침해도 깜빡이지 않습니다.
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [mobileOpen, setMobileOpen] = useState(false)

  const isDesktop = useMediaQuery(`(min-width: ${BP_DESKTOP}px)`)
  const { pathname } = useLocation()

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(COLLAPSED_KEY, next ? '1' : '0')
      } catch {
        // 저장에 실패해도 이번 세션 동안의 접힘 상태는 그대로 동작합니다.
      }
      return next
    })
  }, [])

  const openMobile = useCallback(() => setMobileOpen(true), [])
  const closeMobile = useCallback(() => setMobileOpen(false), [])

  // 이동하면 드로어를 닫습니다. 화면을 가린 채 남아 있으면 도착한 페이지가 보이지 않습니다.
  useEffect(() => setMobileOpen(false), [pathname])

  // 드로어를 연 채 창을 넓히면 사이드바가 정상 위치로 돌아오므로 열림 상태를 정리합니다.
  useEffect(() => {
    if (isDesktop) setMobileOpen(false)
  }, [isDesktop])

  useEffect(() => {
    if (!mobileOpen) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [mobileOpen])

  const sidebar = useMemo(
    () => ({ collapsed, toggleCollapsed, mobileOpen, openMobile, closeMobile }),
    [collapsed, toggleCollapsed, mobileOpen, openMobile, closeMobile],
  )

  return (
    <SidebarContext value={sidebar}>
      <div className={`${styles.shell} ${collapsed ? styles.isRail : ''}`}>
        <Sidebar />

        <div className={styles.main}>
          <Topbar />
          <div className={styles.content}>
            <Outlet />
          </div>
        </div>

        {mobileOpen && <Scrim onClick={closeMobile} />}
      </div>
    </SidebarContext>
  )
}
