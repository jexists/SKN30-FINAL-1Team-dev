// 마이페이지. 사이드바 하단 이름과 헤더 아바타로 들어옵니다.
//
// 바꿀 수 있는 설정이 없어 '설정' 화면 대신 둔 자리입니다. 내 정보는 세션이 가진
// 값을 그대로 보여 주기만 하고, 수정 경로는 없습니다(프로필이 아직 목 데이터입니다).
import { Link } from 'react-router'

import { useCurrentUser, useSession } from '@/auth/sessionContext'
import { ChevronRightIcon, LogoutIcon } from '@/components/icons'
import { ROUTES } from '@/constants/routes'

import styles from './MyPage.module.scss'

const DOC_LINKS = [
  { to: ROUTES.TERMS, label: '이용약관' },
  { to: ROUTES.PRIVACY, label: '개인정보처리방침' },
  { to: ROUTES.LEGAL, label: '법적고지' },
]

export default function MyPage() {
  const { profile, isManager } = useCurrentUser()
  const { logout } = useSession()

  return (
    <section className={styles.page}>
      <div className={styles.card}>
        <div className={styles.profile}>
          <span className={styles.avatar}>{profile.name.charAt(0)}</span>
          <div className={styles.identity}>
            <strong>{profile.name}</strong>
            <span>{profile.title}</span>
          </div>
          <span className={styles.role}>{isManager ? '팀장' : '팀원'}</span>
        </div>
      </div>

      <div className={styles.card}>
        <p className={styles.cardTitle}>약관 및 정책</p>
        <ul className={styles.list}>
          {DOC_LINKS.map(({ to, label }) => (
            <li key={to}>
              <Link to={to} className={styles.row}>
                <span>{label}</span>
                <ChevronRightIcon width={16} height={16} />
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <button type="button" className={styles.logout} onClick={logout}>
        <LogoutIcon width={16} height={16} />
        로그아웃
      </button>
    </section>
  )
}
