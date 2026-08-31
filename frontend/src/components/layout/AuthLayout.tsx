import type { CSSProperties, ReactNode } from 'react'

import fullLogo from '@/assets/full-logo.png'
import { DailyReportIcon, DashboardIcon, VisitIcon } from '@/components/icons'

import styles from './AuthLayout.module.scss'
import AuthNetwork from './AuthNetwork'

interface AuthLayoutProps {
  /** 오른쪽 카드 안에 들어갈 폼. */
  children: ReactNode
}

/**
 * 왼쪽 소개의 방문 사이클. 01·02·03 은 장식이 아니라 실제 순서
 * (방문 전 준비 → 방문 후 분석 → 보고)라서 번호를 그대로 둡니다.
 */
const STEPS = [
  {
    Icon: VisitIcon,
    title: '방문 전 브리핑',
    desc: '회사·고객·지난 기록을 방문 직전에 한 장으로 정리',
  },
  {
    Icon: DashboardIcon,
    title: '영업활동 분석',
    desc: '일정과 미팅 기록을 이어 붙인 활동 흐름',
  },
  {
    Icon: DailyReportIcon,
    title: '보고서 자동화',
    desc: '남긴 기록을 그대로 옮긴 업무보고 초안',
  },
]

/**
 * 로그인 전 화면의 껍데기. /login, /signup, /set-password 가 이 한 벌을 함께 씁니다.
 *
 * 왼쪽 소개는 세 화면이 똑같아서 화면이 넘기지 않고 여기가 통째로 갖습니다.
 *
 * 좁은 화면에서는 왼쪽을 감춥니다. 로그인하러 온 사람이 소개를 스크롤로
 * 지나쳐야 폼을 만나는 일이 없어야 합니다. 소개가 사라지면 브랜드도 같이
 * 사라지므로 카드 안쪽에 같은 락업을 한 번 더 둡니다.
 */
export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <section className={styles.shell}>
      <div className={styles.story}>
        <AuthNetwork />

        <div className={styles.brand} style={{ '--d': '0ms' } as CSSProperties}>
          <img src={fullLogo} alt="SalesLuv" className={styles.brandFull} />
        </div>

        <div className={styles.copy}>
          <h1 style={{ '--d': '80ms' } as CSSProperties}>
            흩어진 영업기록을
            <br />
            <span>하나의 흐름</span>으로
          </h1>
          <p style={{ '--d': '160ms' } as CSSProperties}>
            회사·고객·일정·미팅 기록을 한 흐름으로 연결하는 영업 관리 서비스
          </p>
          <i className={styles.rule} style={{ '--d': '220ms' } as CSSProperties} />
        </div>

        <ul className={styles.steps}>
          {STEPS.map(({ Icon, title, desc }, i) => (
            <li
              key={title}
              className={styles.step}
              style={{ '--d': `${280 + i * 90}ms` } as CSSProperties}
            >
              <span className={styles.stepIcon}>
                <Icon width={18} height={18} />
              </span>
              <div className={styles.stepText}>
                <strong>{title}</strong>
                <small>{desc}</small>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelBrand}>
          <img src={fullLogo} alt="SalesLuv" className={styles.brandFull} />
        </div>
        {children}
      </div>
    </section>
  )
}
