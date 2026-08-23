/**
 * 백엔드 오류를 사용자 문구로 바꿉니다.
 *
 * `docs/technical/backend/api-conventions.md` 10절은 업무·권한 오류를
 * `{ "detail": "<snake_case 코드>" }` 로 통일하고, 그 코드를 사람이 읽는
 * 문구로 바꾸는 일을 프론트에 맡깁니다. 이 모듈이 그 자리입니다.
 *
 * 코드 → 상태 → 호출부가 준 fallback 순으로 내려가며, 어떤 경로로도 빈 값을
 * 돌려주지 않습니다. 화면이 조용히 실패하는 일이 없어야 합니다.
 *
 * 기존 페이지들은 아직 상태 코드만 보는 지역 함수를 각자 갖고 있습니다.
 * 그쪽을 옮겨올 때 여기에 코드를 추가하면 됩니다.
 */

import { isAxiosError } from 'axios'

/** 백엔드가 오류에 싣는 유일한 필드입니다. */
interface ErrorEnvelope {
  detail?: unknown
}

/** 422 검증 오류는 `detail` 이 문자열이 아니라 배열이라 여기서 걸러집니다. */
export function readErrorDetail(error: unknown): string | null {
  if (!isAxiosError(error)) return null
  const data = error.response?.data as ErrorEnvelope | undefined
  return typeof data?.detail === 'string' ? data.detail : null
}

const MESSAGE_BY_DETAIL: Record<string, string> = {
  invalid_credentials: '이메일 또는 비밀번호가 올바르지 않습니다.',
  not_authenticated: '로그인이 만료되었습니다. 다시 로그인해 주세요.',
  member_not_linked: '이 계정은 아직 팀에 연결되지 않았습니다. 관리자에게 문의해 주세요.',
  login_rate_limited: '로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.',
  auth_not_configured: '로그인 설정이 완료되지 않았습니다. 서버 설정을 확인해 주세요.',
  auth_unavailable: '인증 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.',
  origin_not_allowed: '허용되지 않은 주소에서 보낸 요청입니다.',
  // 계정 발급 (/admin)
  admin_only: '계정을 발급할 수 있는 계정이 아닙니다.',
  admin_not_configured: '계정 발급 설정이 완료되지 않았습니다. 서버 설정을 확인해 주세요.',
  email_already_exists: '이미 등록된 이메일입니다.',
  team_name_already_exists: '같은 이름의 팀이 이미 있습니다.',
  team_not_found: '고른 팀을 찾을 수 없습니다. 목록을 새로 불러와 주세요.',
  password_rejected: '비밀번호가 정책에 맞지 않습니다. 더 길고 복잡하게 정해 주세요.',
}

const MESSAGE_BY_STATUS: Record<number, string> = {
  401: '로그인이 만료되었습니다. 다시 로그인해 주세요.',
  403: '이 작업을 수행할 권한이 없습니다.',
  409: '다른 변경이 먼저 반영되었습니다. 새로고침한 뒤 다시 시도해 주세요.',
  422: '입력한 내용을 확인해 주세요.',
}

/**
 * @param fallback 코드도 상태도 못 알아봤을 때 보여 줄 문구. 화면 맥락을 담습니다.
 */
export function errorMessage(error: unknown, fallback: string): string {
  const detail = readErrorDetail(error)
  if (detail && detail in MESSAGE_BY_DETAIL) return MESSAGE_BY_DETAIL[detail]

  if (isAxiosError(error)) {
    const status = error.response?.status
    if (status !== undefined && status in MESSAGE_BY_STATUS) return MESSAGE_BY_STATUS[status]
  }

  return fallback
}
