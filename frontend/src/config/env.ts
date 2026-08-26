/**
 * 환경변수를 읽는 유일한 창구.
 *
 * 다른 파일에서 import.meta.env 를 직접 읽지 마세요.
 * 오타가 나도 타입 에러 없이 undefined 로 통과해 엉뚱한 곳에서 터집니다.
 *
 * 여기 넣는 값은 빌드 시 번들에 문자열로 박혀 브라우저에 그대로 노출됩니다.
 * 비밀값은 절대 두지 마세요. 외부 API 호출은 백엔드를 경유합니다.
 */
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
  // vite 개발 서버로 띄웠는지. 문구를 고르는 데만 씁니다.
  // 계정 발급이 초대 메일을 보낼지 말지는 백엔드의 APP_ENV 가 정합니다.
  isDev: import.meta.env.DEV,
} as const

if (!env.apiBaseUrl) {
  throw new Error('VITE_API_BASE_URL 이 비어 있습니다. frontend/.env 를 확인하세요.')
}
