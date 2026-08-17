import { useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router'

import { useCurrentUser } from '@/auth/sessionContext'
import { buttonClass } from '@/components/Button'
import { BellIcon, MenuIcon } from '@/components/icons'
import { useSidebar } from '@/components/layout/AppShell/sidebarContext'
import { SIDEBAR_ID } from '@/components/layout/Sidebar/Sidebar'
import { findNavLabel } from '@/constants/navigation'
import { ROUTES } from '@/constants/routes'
import { useHasUnread } from '@/shared/notifications'

import ScopeSwitcher from './ScopeSwitcher'

import styles from './Topbar.module.scss'

export default function Topbar() {
  const { mobileOpen, openMobile } = useSidebar()
  const { profile, isManager } = useCurrentUser()
  const { pathname } = useLocation()
  const hasUnread = useHasUnread()

  const hamburgerRef = useRef<HTMLButtonElement>(null)
  const wasOpen = useRef(false)

  // 드로어가 닫히면 포커스를 열었던 버튼으로 되돌립니다.
  useEffect(() => {
    if (wasOpen.current && !mobileOpen) hamburgerRef.current?.focus()
    wasOpen.current = mobileOpen
  }, [mobileOpen])

  const pageLabel = findNavLabel(pathname) ?? '페이지를 찾을 수 없음'
  const isDeals = pathname === ROUTES.DEALS || pathname.startsWith(`${ROUTES.DEALS}/`)
  const isOrders = pathname === ROUTES.ORDERS || pathname.startsWith(`${ROUTES.ORDERS}/`)
  const isComplaints =
    pathname === ROUTES.COMPLAINTS || pathname.startsWith(`${ROUTES.COMPLAINTS}/`)

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

      {/* 실제 팀원 UUID 목록이 붙기 전까지 DB 화면에는 목업 담당자 필터를 노출하지 않습니다. */}
      {isManager &&
        pathname !== ROUTES.CUSTOMERS &&
        pathname !== ROUTES.CALENDAR &&
        !isDeals &&
        !isOrders &&
        !isComplaints && (
          <div className={styles.scope}>
            <ScopeSwitcher />
          </div>
        )}

      {/* 알림은 화면 하나입니다. 벨은 그리로 가는 통로일 뿐이라 점만 얹습니다. */}
      <Link
        className={buttonClass({ variant: 'outline', iconOnly: true }, styles.iconBtn)}
        to={ROUTES.NOTIFICATIONS}
        aria-label={hasUnread ? '알림 (읽지 않음 있음)' : '알림'}
      >
        <BellIcon />
        {hasUnread && <span className={styles.dot} />}
      </Link>

      {/* 아바타는 마이페이지로 가는 통로입니다. */}
      <Link className={styles.avatar} to={ROUTES.MYPAGE} aria-label="마이페이지">
        {profile.name.charAt(0)}
      </Link>
    </header>
  )
}
