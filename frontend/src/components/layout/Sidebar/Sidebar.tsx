import { useEffect, useRef } from 'react'
import { Link, NavLink } from 'react-router'

import fullLogo from '@/assets/full-logo.png'
import logoMark from '@/assets/logo-mark.png'
import { useCurrentUser, useSession } from '@/auth/sessionContext'
import { ChevronLeftIcon, CloseIcon, LogoutIcon } from '@/components/icons'
import { useSidebar } from '@/components/layout/AppShell/sidebarContext'
import { NAV_SECTIONS } from '@/constants/navigation'
import { ROUTES } from '@/constants/routes'

import styles from './Sidebar.module.scss'

export const SIDEBAR_ID = 'app-sidebar'

export default function Sidebar() {
  const { collapsed, toggleCollapsed, mobileOpen, closeMobile } = useSidebar()
  const { isManager, profile } = useCurrentUser()
  const { logout } = useSession()
  const asideRef = useRef<HTMLElement>(null)

  // 드로어가 열리면 포커스를 안으로 옮깁니다. 그러지 않으면 키보드 사용자는
  // 화면 밖에 있던 메뉴를 탭으로 한참 뒤에야 만나게 됩니다.
  useEffect(() => {
    if (mobileOpen) asideRef.current?.focus()
  }, [mobileOpen])

  const sections = NAV_SECTIONS.filter((section) => !section.managerOnly || isManager)

  const className = [styles.sidebar, collapsed && styles.isRail, mobileOpen && styles.isOpen]
    .filter(Boolean)
    .join(' ')

  return (
    <aside id={SIDEBAR_ID} ref={asideRef} tabIndex={-1} className={className} aria-label="주 메뉴">
      <div className={styles.brand}>
        <Link to={ROUTES.DASHBOARD} className={styles.brandLockup} aria-label="대시보드로 이동">
          <img src={logoMark} alt="" className={styles.brandMark} />
          <img src={fullLogo} alt="SalesLuv" className={styles.brandFull} />
        </Link>

        <button
          type="button"
          className={styles.railToggle}
          onClick={(event) => {
            toggleCollapsed()
            // 포인터로 눌렀으면 포커스를 떼어 냅니다. 남겨 두면 :focus-within 이
            // 레일을 계속 펼쳐 놓습니다. 키보드 조작(detail 0)은 포커스를 유지합니다.
            if (!collapsed && event.detail > 0) event.currentTarget.blur()
          }}
          aria-controls={SIDEBAR_ID}
          aria-expanded={!collapsed}
          aria-label={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
        >
          <ChevronLeftIcon />
        </button>

        <button
          type="button"
          className={styles.drawerClose}
          onClick={closeMobile}
          aria-label="메뉴 닫기"
        >
          <CloseIcon />
        </button>
      </div>

      <nav className={styles.nav}>
        {sections.map((section) => (
          <div
            key={section.id}
            className={styles.section}
            role="group"
            aria-label={section.title ?? section.ariaLabel}
          >
            {/* 레일에서는 짧은 이름이 같은 자리에 대신 들어갑니다. 상자 크기는
                양쪽이 같아 펼쳐도 아래 메뉴가 움직이지 않습니다. */}
            {section.title && (
              <p className={styles.sectionTitle}>
                <span className={styles.sectionTitleFull}>{section.title}</span>
                <span className={styles.sectionTitleShort} aria-hidden="true">
                  {section.shortTitle ?? section.title}
                </span>
              </p>
            )}

            {section.items.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === ROUTES.DASHBOARD}
                title={label}
                className={({ isActive }) =>
                  isActive ? `${styles.navBtn} ${styles.isActive}` : styles.navBtn
                }
              >
                <Icon className={styles.navIcon} />
                <span className={styles.navText}>{label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      {/* 이름을 누르면 마이페이지로 갑니다. 로그아웃은 링크 밖 형제로 둡니다. */}
      <div className={styles.foot}>
        <Link to={ROUTES.MYPAGE} className={styles.footLink} title="마이페이지">
          <span className={styles.avatar}>{profile.name.charAt(0)}</span>
          <span className={styles.footCopy}>
            <strong>{profile.name}</strong>
            <span>{profile.title}</span>
          </span>
        </Link>
        <button type="button" className={styles.logout} onClick={logout} aria-label="로그아웃">
          <LogoutIcon />
        </button>
      </div>
    </aside>
  )
}
