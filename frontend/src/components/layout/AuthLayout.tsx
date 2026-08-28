import type { ReactNode } from 'react'

import styles from './AuthLayout.module.scss'

interface AuthLayoutProps {
  /** 오른쪽 카드 안에 들어갈 폼. */
  children: ReactNode
}

/**
 * 로그인 전 화면의 껍데기. /login 과 /signup 이 이 한 벌을 함께 씁니다.
 *
 * 왼쪽 소개는 두 화면이 똑같아서 화면이 넘기지 않고 여기가 통째로 갖습니다.
 *
 * 좁은 화면에서는 왼쪽을 감춥니다. 로그인하러 온 사람이 소개를 스크롤로
 * 지나쳐야 폼을 만나는 일이 없어야 합니다. 소개가 사라지면 브랜드도 같이
 * 사라지므로 카드 안쪽에 같은 락업을 한 번 더 둡니다.
 */
export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <section className={styles.shell}>
      <div className={styles.story}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>S</span>
          <span className={styles.brandName}>SalesLuv</span>
        </div>

        <div className={styles.copy}>
          <span className={styles.tag}>
            <i className={styles.pulseDot} /> Sales History Workspace
          </span>
          <h1>
            흩어진 영업기록을
            <br />
            <span>한 곳에 모아</span> 보여 줍니다.
          </h1>
          <p>회사·고객·일정·미팅 기록을 한 흐름으로 연결해 방문 준비와 보고서 작성을 돕습니다.</p>
        </div>

        <div className={styles.proof}>
          <div>
            <strong>01</strong>
            <small>방문 전 브리핑</small>
          </div>
          <div>
            <strong>02</strong>
            <small>영업활동 분석</small>
          </div>
          <div>
            <strong>03</strong>
            <small>보고서 자동화</small>
          </div>
        </div>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelBrand}>
          <span className={styles.brandMark}>S</span>
          <span className={styles.brandName}>SalesLuv</span>
        </div>
        {children}
      </div>
    </section>
  )
}
