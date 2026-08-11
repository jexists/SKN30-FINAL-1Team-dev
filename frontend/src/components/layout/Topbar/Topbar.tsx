import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import { BellIcon, MenuIcon } from '@/components/icons'
import { useSidebar } from '@/components/layout/AppShell/sidebarContext'
import { SIDEBAR_ID } from '@/components/layout/Sidebar/Sidebar'
import { findNavLabel } from '@/constants/navigation'

import styles from './Topbar.module.scss'

export default function Topbar() {
  const { mobileOpen, openMobile } = useSidebar()
  const { profile } = useCurrentUser()
  const { pathname } = useLocation()

  const hamburgerRef = useRef<HTMLButtonElement>(null)
  const wasOpen = useRef(false)

  // 드로어가 닫히면 포커스를 열었던 버튼으로 되돌립니다.
  useEffect(() => {
    if (wasOpen.current && !mobileOpen) hamburgerRef.current?.focus()
    wasOpen.current = mobileOpen
  }, [mobileOpen])

  const pageLabel = findNavLabel(pathname) ?? '페이지를 찾을 수 없음'

  return (
    <header className={styles.topbar}>
      <button
        type="button"
        ref={hamburgerRef}
        className={styles.hamburger}
        onClick={openMobile}
        aria-controls={SIDEBAR_ID}
        aria-expanded={mobileOpen}
        aria-label="메뉴 열기"
      >
        <MenuIcon />
      </button>

      <p className={styles.breadcrumb}>
        SalesLuv / <strong>{pageLabel}</strong>
      </p>

      <div className={styles.spacer} />

      <button type="button" className={styles.iconBtn} aria-label="알림">
        <BellIcon />
      </button>

      <span className={styles.avatar}>{profile.name.charAt(0)}</span>
    </header>
  )
}
