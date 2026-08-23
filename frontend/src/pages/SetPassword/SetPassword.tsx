import { type FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { client } from '@/api/client'
import { errorMessage } from '@/api/errorMessage'
import Button from '@/components/Button'
import { ROUTES } from '@/constants/routes'

import styles from './SetPassword.module.scss'

/** Supabase 정책과 별개로 화면이 먼저 막는 최소 길이입니다. 서버도 같은 값을 봅니다. */
const MIN_LENGTH = 8

/**
 * 초대 메일 링크에 실려 온 토큰을 읽습니다.
 *
 * Supabase 는 `#access_token=...&type=invite` 형태로 되돌려 보냅니다.
 * 읽기만 하고 지우지는 않습니다. StrictMode 가 초기화 함수를 두 번 부르므로,
 * 여기서 해시를 지우면 두 번째 호출이 빈 해시를 보고 토큰이 없다고 판단합니다.
 */
function readAccessToken(): string | null {
  const hash = window.location.hash.replace(/^#/, '')
  if (!hash) return null
  return new URLSearchParams(hash).get('access_token')
}

export default function SetPassword() {
  const navigate = useNavigate()
  // 링크를 여는 순간 한 번만 읽습니다. 이후 렌더는 지워진 해시를 다시 보지 않습니다.
  const [accessToken] = useState(readAccessToken)

  // 토큰을 state 로 옮겼으면 주소창에서는 지웁니다. 남겨 두면 어깨너머로도,
  // 뒤로가기로도, 공유된 링크로도 새어 나갑니다. 두 번 지워도 문제가 없습니다.
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
  }, [])

  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const tooShort = password.length > 0 && password.length < MIN_LENGTH
  const mismatched = confirmation.length > 0 && password !== confirmation
  const submittable = password.length >= MIN_LENGTH && password === confirmation

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!accessToken || !submittable) return

    setSubmitting(true)
    setError(null)
    try {
      await client.post('/auth/set-password', { access_token: accessToken, password })
      // 세션을 여기서 만들지 않습니다. 새 비밀번호가 실제로 되는지 로그인에서 바로 확인합니다.
      navigate(ROUTES.LOGIN, { replace: true })
    } catch (cause) {
      setError(errorMessage(cause, '비밀번호를 설정할 수 없습니다. 잠시 후 다시 시도해 주세요.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className={styles.shell}>
      <div className={styles.panel}>
        <p className={styles.eyebrow}>SalesLuv</p>
        <h1>비밀번호 설정</h1>

        {accessToken === null ? (
          <>
            <p className={styles.lead}>
              링크가 만료되었거나 올바르지 않습니다. 초대 메일의 링크는 한 번만 쓸 수 있습니다.
            </p>
            <p className={styles.error} role="alert">
              관리자에게 초대 메일 재발송을 요청해 주세요.
            </p>
          </>
        ) : (
          <>
            <p className={styles.lead}>
              앞으로 로그인에 쓸 비밀번호를 정해 주세요. {MIN_LENGTH}자 이상이어야 합니다.
            </p>

            <form onSubmit={onSubmit}>
              <div className={styles.field}>
                <label htmlFor="password">새 비밀번호</label>
                <input
                  className={styles.input}
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={submitting}
                  aria-invalid={tooShort}
                  aria-describedby={tooShort ? 'password-hint' : undefined}
                  required
                />
                {tooShort && (
                  <p id="password-hint" className={styles.hint}>
                    {MIN_LENGTH}자 이상 입력해 주세요.
                  </p>
                )}
              </div>

              <div className={styles.field}>
                <label htmlFor="confirmation">비밀번호 확인</label>
                <input
                  className={styles.input}
                  id="confirmation"
                  type="password"
                  autoComplete="new-password"
                  value={confirmation}
                  onChange={(e) => setConfirmation(e.target.value)}
                  disabled={submitting}
                  aria-invalid={mismatched}
                  aria-describedby={mismatched ? 'confirmation-hint' : undefined}
                  required
                />
                {mismatched && (
                  <p id="confirmation-hint" className={styles.hint}>
                    두 비밀번호가 다릅니다.
                  </p>
                )}
              </div>

              {error && (
                <p className={styles.error} role="alert">
                  {error}
                </p>
              )}

              <Button
                className={styles.mainBtn}
                type="submit"
                disabled={submitting || !submittable}
              >
                {submitting ? '설정 중…' : '비밀번호 설정'}
              </Button>
            </form>
          </>
        )}
      </div>
    </section>
  )
}
