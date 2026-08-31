import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'

import { errorMessage } from '@/api/errorMessage'
import { requestAccount } from '@/api/signup'
import Button from '@/components/Button'
import AuthLayout from '@/components/layout/AuthLayout'
import { ROUTES } from '@/constants/routes'

import styles from './Signup.module.scss'

/**
 * 계정 요청 화면.
 *
 * SalesLuv 는 관리자가 계정을 발급하는 제품이라 스스로 가입할 수 없습니다.
 * 여기서는 연락할 이메일만 받고, 요청은 팀 Discord 채널로 갑니다.
 */
export default function Signup() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 보낸 이메일을 그대로 들고 있다가 완료 화면에서 되읽어 줍니다. 오타를 여기서 발견합니다.
  const [sentTo, setSentTo] = useState<string | null>(null)

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const trimmed = email.trim()
    setSubmitting(true)
    setError(null)
    try {
      await requestAccount(trimmed)
      setSentTo(trimmed)
    } catch (cause) {
      setError(errorMessage(cause, '요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.'))
    } finally {
      setSubmitting(false)
    }
  }

  if (sentTo) {
    return (
      <AuthLayout>
        <p className={styles.eyebrow}>Request received</p>
        <h2>요청을 받았습니다</h2>
        {/* 조사가 붙지 않게 주소를 줄 바꿔 뺍니다. .com 뒤에는 '으로', .co 뒤에는
            '로' 가 맞아서 문장 안에 넣으면 어느 쪽을 써도 틀리는 주소가 생깁니다. */}
        <p className={`${styles.lead} ${styles.leadTight}`}>
          일주일 이내에 아래 주소로 연락드리겠습니다.
        </p>
        <p className={styles.sentTo}>{sentTo}</p>
        <p className={styles.footnote}>
          <Link to={ROUTES.LOGIN}>로그인으로 돌아가기</Link>
        </p>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <p className={styles.eyebrow}>Get started</p>
      <h2>회원가입</h2>
      <p className={styles.lead}>이메일을 남겨 주시면 일주일 이내로 계정 발급을 안내해 드립니다.</p>

      <form onSubmit={onSubmit}>
        <div className={styles.field}>
          <label htmlFor="email">이메일</label>
          <input
            className={styles.input}
            id="email"
            type="email"
            autoComplete="email"
            placeholder="name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={submitting}
            aria-invalid={error !== null}
            aria-describedby={error ? 'signup-error' : undefined}
            required
          />
        </div>
        {error && (
          <p id="signup-error" className={styles.error} role="alert">
            {error}
          </p>
        )}
        <Button className={styles.mainBtn} type="submit" disabled={submitting}>
          {submitting ? '전송중' : '요청 보내기'}
        </Button>
      </form>

      <p className={styles.footnote}>
        이미 계정이 있으신가요? <Link to={ROUTES.LOGIN}>로그인</Link>
      </p>
    </AuthLayout>
  )
}
