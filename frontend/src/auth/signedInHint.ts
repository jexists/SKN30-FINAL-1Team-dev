/**
 * 세션이 있는지만 알려주는 표시입니다.
 *
 * 토큰 쿠키는 HttpOnly 라 JS 가 읽을 수 없어서, 프론트는 "로그인 안 함" 과
 * "쿠키가 있는데 안 보임" 을 구분하지 못합니다. 그래서 앱이 뜰 때마다
 * /auth/me 를 물어봐야 했습니다.
 *
 * 백엔드가 로그인 응답에서 토큰 쿠키와 함께 이 표시를 설정하고 로그아웃에서
 * 함께 지웁니다. 셋 다 쿠키라 브라우저가 정리할 때도 같이 사라지므로 서로
 * 어긋나지 않습니다. 값은 `1` 하나뿐이고 권한 판단은 여전히 서버가 합니다.
 *
 * 백엔드의 SIGNED_IN_COOKIE 와 이름·경로를 맞춰야 합니다.
 */

const COOKIE_NAME = 'salesluv_signed_in'
const COOKIE_PATH = '/'

export function hasSignedInHint(): boolean {
  // 쿠키를 못 읽는 환경이면 건너뛰지 않고 서버에 물어보는 쪽을 고릅니다.
  if (typeof document === 'undefined') return true

  return document.cookie.split(';').some((entry) => entry.trim().startsWith(`${COOKIE_NAME}=`))
}

/**
 * 서버가 지우지 못한 표시를 걷어냅니다.
 *
 * 만료된 세션으로 /auth/me 가 401 을 주는 경우, 그 응답은 쿠키를 지우지
 * 않습니다. 표시만 남으면 다음 진입 때 쓸데없이 다시 물어보게 되므로
 * HttpOnly 가 아닌 이 쿠키만 프론트에서 정리합니다.
 */
export function clearSignedInHint() {
  if (typeof document === 'undefined') return
  document.cookie = `${COOKIE_NAME}=; Max-Age=0; path=${COOKIE_PATH}`
}
