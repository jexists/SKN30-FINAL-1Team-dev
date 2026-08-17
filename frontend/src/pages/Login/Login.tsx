import { type FormEvent, useState } from 'react'
import { isAxiosError } from 'axios'
import { Navigate } from 'react-router'

import { useSession } from '@/auth/sessionContext'
import Button from '@/components/Button'
import { ROUTES } from '@/constants/routes'

import styles from './Login.module.scss'

function loginErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    if (error.response?.status === 401) return '로그인 아이디 또는 비밀번호를 확인해 주세요.'
    if (error.response?.status === 429)
      return '로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.'
  }
  return '로그인할 수 없습니다. 잠시 후 다시 시도해 주세요.'
}

export default function Login() {
  const { session, login } = useSession()

  const [loginId, setLoginId] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 로그인 직후에도, 이미 로그인한 채로 /login 에 들어와도 이 한 줄이 목적지를 정합니다.
  // login() 뒤에 navigate() 를 따로 부르면 이 리다이렉트와 경합해 목적지를 잃습니다.
  //
  // 가려던 경로로 되돌려보내지 않고 항상 대시보드로 보냅니다. 구현된 화면이
  // 대시보드뿐이라 나머지로 되돌아가 봐야 404 를 만나기 때문입니다.
  if (session) return <Navigate to={ROUTES.DASHBOARD} replace />

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(loginId.trim(), password)
    } catch (cause) {
      setError(loginErrorMessage(cause))
    } finally {
      setSubmitting(false)
    }
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
            <label htmlFor="login-id">로그인 아이디</label>
            <input
              className={styles.input}
              id="login-id"
              type="text"
              autoComplete="username"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              disabled={submitting}
              aria-invalid={error !== null}
              aria-describedby={error ? 'login-error' : undefined}
              required
            />
          </div>
          <div className={styles.field}>
            <label htmlFor="password">비밀번호</label>
            <input
              className={styles.input}
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              aria-invalid={error !== null}
              aria-describedby={error ? 'login-error' : undefined}
              required
            />
          </div>
          {error && (
            <p id="login-error" className={styles.error} role="alert">
              {error}
            </p>
          )}
          <Button className={styles.mainBtn} type="submit" disabled={submitting}>
            {submitting ? '로그인 중…' : '로그인'} <span aria-hidden="true">→</span>
          </Button>
        </form>

        <p className={styles.footnote}>
          시연용 합성 데이터입니다. 실제 개인정보는 포함되어 있지 않습니다.
        </p>
      </div>
    </section>
  )
}
