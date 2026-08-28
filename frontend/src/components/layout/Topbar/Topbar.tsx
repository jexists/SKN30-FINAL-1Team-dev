import { useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import { buttonClass } from '@/components/Button'
import { BellIcon, MenuIcon } from '@/components/icons'
import { useSidebar } from '@/components/layout/AppShell/sidebarContext'
import { SIDEBAR_ID } from '@/components/layout/Sidebar/Sidebar'
import ScopeSwitcher from '@/components/layout/Topbar/ScopeSwitcher'
import { findNavLabel } from '@/constants/navigation'
import { ROUTES } from '@/constants/routes'

import styles from './Topbar.module.scss'

export default function Topbar() {
  const { mobileOpen, openMobile } = useSidebar()
  const { profile } = useCurrentUser()
  const { pathname, search } = useLocation()

  const hamburgerRef = useRef<HTMLButtonElement>(null)
  const wasOpen = useRef(false)

  // 드로어가 닫히면 포커스를 열었던 버튼으로 되돌립니다.
  useEffect(() => {
    if (wasOpen.current && !mobileOpen) hamburgerRef.current?.focus()
    wasOpen.current = mobileOpen
  }, [mobileOpen])

  const pageLabel = findNavLabel(pathname, search) ?? '페이지를 찾을 수 없음'

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

      {/* 브랜드 이름은 사이드바 로고가 이미 말합니다. 여기는 지금 화면 이름만 둡니다. */}
      <p className={styles.pageName}>{pageLabel}</p>

      <div className={styles.spacer} />

      {/* 화면 전체가 누구의 현황을 보는지 정합니다. 페이지마다 따로 두지 않습니다. */}
      <ScopeSwitcher />

      {/* 알림 조회 API가 없어 읽지 않음 여부는 표시하지 않습니다. */}
      <Link
        className={buttonClass({ variant: 'outline', iconOnly: true }, styles.iconBtn)}
        to={ROUTES.NOTIFICATIONS}
        aria-label="알림"
      >
        <BellIcon />
      </Link>

      {/* 아바타는 마이페이지로 가는 통로입니다. */}
      <Link className={styles.avatar} to={ROUTES.MYPAGE} aria-label="마이페이지">
        {profile.name.charAt(0)}
      </Link>
    </header>
  )
}
