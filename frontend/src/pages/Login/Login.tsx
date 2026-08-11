import { type FormEvent, useState } from 'react'
import { Navigate } from 'react-router'

import { type Role, useSession } from '@/auth/sessionContext'
import Button from '@/components/Button'
import { ROUTES } from '@/constants/routes'

import styles from './Login.module.scss'

const DEMO_ROLES: { role: Role; label: string; note: string }[] = [
  { role: 'member', label: '영업 담당자', note: '내 고객·일정·문서만 조회' },
  { role: 'manager', label: '영업 팀장', note: '팀 전체 현황과 매출 조회' },
]

export default function Login() {
  const { session, login } = useSession()

  const [email, setEmail] = useState('manager@salesluv.demo')
  const [password, setPassword] = useState('salesluv')

  // 로그인 직후에도, 이미 로그인한 채로 /login 에 들어와도 이 한 줄이 목적지를 정합니다.
  // login() 뒤에 navigate() 를 따로 부르면 이 리다이렉트와 경합해 목적지를 잃습니다.
  //
  // 가려던 경로로 되돌려보내지 않고 항상 대시보드로 보냅니다. 구현된 화면이
  // 대시보드뿐이라 나머지로 되돌아가 봐야 404 를 만나기 때문입니다.
  if (session) return <Navigate to={ROUTES.DASHBOARD} replace />

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    // 아직 인증 API 가 없어 입력값을 검증하지 않습니다. 아래 각주가 이를 밝힙니다.
    login('manager')
  }

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
        <p className={styles.eyebrow}>Welcome back</p>
        <h2>현장으로 돌아가기</h2>
        <p className={styles.lead}>SalesLuv 데모 계정으로 주요 영업 흐름을 확인하세요.</p>

        <form onSubmit={onSubmit}>
          <div className={styles.field}>
            <label htmlFor="email">이메일</label>
            <input
              className={styles.input}
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="password">비밀번호</label>
            <input
              className={styles.input}
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <Button className={styles.mainBtn} type="submit">
            팀장 데모로 로그인 <span aria-hidden="true">→</span>
          </Button>
        </form>

        <div className={styles.or}>역할별 화면 바로 보기</div>

        <div className={styles.demoRoles}>
          {DEMO_ROLES.map(({ role, label, note }) => (
            <button
              key={role}
              className={styles.demoRole}
              type="button"
              onClick={() => login(role)}
            >
              <strong>{label}</strong>
              <span>{note}</span>
            </button>
          ))}
        </div>

        <p className={styles.footnote}>
          시연용 합성 데이터입니다. 실제 개인정보는 포함되어 있지 않습니다.
        </p>
      </div>
    </section>
  )
}
