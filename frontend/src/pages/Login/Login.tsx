import { type FormEvent, useState } from 'react'
import { isAxiosError } from 'axios'
import { Link, Navigate } from 'react-router'

import { errorMessage } from '@/api/errorMessage'
import { DEV_ACCOUNTS, LOCAL_DEV_PASSWORD } from '@/auth/devAccounts'
import { useSession } from '@/auth/sessionContext'
import Button from '@/components/Button'
import AuthLayout from '@/components/layout/AuthLayout'
import { env } from '@/config/env'
import { ROUTES } from '@/constants/routes'

import styles from './Login.module.scss'

/**
 * 로그인 실패는 어떤 이유든 이 화면이 직접 알립니다.
 *
 * 예전에는 연결 실패를 ConnectionAlert 모달에 넘기려고 null 을 돌려줬는데,
 * 그 결과 모달이 안 뜨는 상황에서 아무 안내도 남지 않았습니다. 로그인 폼은
 * 자기 실패를 스스로 설명합니다.
 */
function loginErrorMessage(error: unknown): string {
  if (isAxiosError(error) && error.response === undefined) {
    return '서버에 연결할 수 없습니다. 백엔드 서버 상태를 확인해 주세요.'
  }
  return errorMessage(error, '로그인할 수 없습니다. 잠시 후 다시 시도해 주세요.')
}

export default function Login() {
  const { session, login } = useSession()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 로그인 직후에도, 이미 로그인한 채로 /login 에 들어와도 이 한 줄이 목적지를 정합니다.
  // login() 뒤에 navigate() 를 따로 부르면 이 리다이렉트와 경합해 목적지를 잃습니다.
  //
  // 가려던 경로로 되돌려보내지 않고 항상 대시보드로 보냅니다. 구현된 화면이
  // 대시보드뿐이라 나머지로 되돌아가 봐야 404 를 만나기 때문입니다.
  if (session) return <Navigate to={ROUTES.DASHBOARD} replace />

  const message = error

  // 폼 제출과 로컬 빠른 로그인이 같은 경로를 씁니다.
  // 성공해도 navigate() 를 부르지 않습니다. 위의 <Navigate> 가 목적지를 정합니다.
  const signIn = async (accountEmail: string, accountPassword: string) => {
    setSubmitting(true)
    setError(null)
    try {
      await login(accountEmail, accountPassword)
    } catch (cause) {
      setError(loginErrorMessage(cause))
    } finally {
      setSubmitting(false)
    }
  }

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    await signIn(email.trim(), password)
  }

  return (
    <AuthLayout>
      <h2>로그인</h2>
      <p className={styles.lead}>SalesLuv 계정으로 로그인해주세요.</p>

      <form onSubmit={onSubmit}>
        <div className={styles.field}>
          <label htmlFor="email">이메일</label>
          <input
            className={styles.input}
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
            aria-invalid={message !== null}
            aria-describedby={message ? 'login-error' : undefined}
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
            aria-invalid={message !== null}
            aria-describedby={message ? 'login-error' : undefined}
            required
          />
        </div>
        {message && (
          <p id="login-error" className={styles.error} role="alert">
            {message}
          </p>
        )}
        <Button className={styles.mainBtn} type="submit" disabled={submitting}>
          {submitting ? '로그인 중…' : '로그인'}
        </Button>
      </form>

      {env.isDev && (
        <div className={styles.devPanel}>
          <p className={styles.devHint}>로컬 전용 · 비밀번호 {LOCAL_DEV_PASSWORD}</p>
          <div className={styles.devButtons}>
            {DEV_ACCOUNTS.map((account) => (
              <Button
                key={account.email}
                type="button"
                variant="outline"
                size="sm"
                disabled={submitting}
                onClick={() => void signIn(account.email, LOCAL_DEV_PASSWORD)}
              >
                {account.label}로 로그인
              </Button>
            ))}
          </div>
        </div>
      )}

      <p className={styles.footnote}>
        SalesLuv 처음이신가요? <Link to={ROUTES.SIGNUP}>회원가입</Link>
      </p>
    </AuthLayout>
  )
}
