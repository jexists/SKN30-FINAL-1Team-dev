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
  team_manager_exists: '이 팀에는 이미 팀장이 있습니다. 팀장은 팀당 한 명입니다.',
  password_rejected: '비밀번호가 정책에 맞지 않습니다. 더 길고 복잡하게 정해 주세요.',
  // 계정 요청 (/signup)
  signup_rate_limited: '요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.',
  signup_not_configured: '계정 요청 접수 설정이 완료되지 않았습니다. 서버 설정을 확인해 주세요.',
  signup_unavailable: '요청을 접수하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  // 고객 (/customers)
  manager_required: '이 작업은 팀장만 할 수 있습니다.',
  assignee_required: '담당자를 한 명 이상 정해 주세요.',
  assignee_member_not_found: '고른 담당자를 찾을 수 없습니다. 목록을 새로 불러와 주세요.',
  customer_company_not_found: '고객사를 찾지 못했습니다. 다시 시도해 주세요.',
  customer_contact_not_found: '고객을 찾지 못했습니다. 목록을 새로 불러와 주세요.',
  customer_contact_duplicate: '이미 등록된 고객입니다. 기존 고객 정보를 확인해 주세요.',
  customer_contact_status_code_not_found: '고객 상태 설정을 확인해 주세요.',
  // 문자 인식(OCR)·AI 처리. 자료실과 명함이 같은 코드를 씁니다.
  ocr_not_configured: '문자 인식 설정이 완료되지 않았습니다. 서버 설정을 확인해 주세요.',
  ocr_unavailable: '문자 인식 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  llm_not_configured: 'AI 처리 설정이 완료되지 않았습니다. 서버 설정을 확인해 주세요.',
  // 명함 인식 (/customers)
  business_card_extraction_failed:
    '명함에서 값을 정리하지 못했습니다. 글자가 또렷하게 나오도록 다시 찍어 주세요.',
  business_card_scan_empty: '명함에서 읽어 낸 값이 없습니다. 화면에 꽉 차게 다시 찍어 주세요.',
  business_card_scan_not_found: '인식 결과가 만료되었습니다. 다시 시도해 주세요.',
  business_card_scan_timeout: '명함 인식이 제한시간 안에 끝나지 않았습니다. 다시 시도해 주세요.',
  business_card_upload_timeout:
    '사진을 올리는 데 시간이 너무 오래 걸렸습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요.',
  // 사업자등록증 인식 (/customers)
  business_license_scan_empty:
    '사업자등록증에서 읽어 낸 값이 없습니다. 문서가 선명하게 보이도록 다시 올려 주세요.',
  business_license_scan_not_found: '인식 결과가 만료되었습니다. 다시 시도해 주세요.',
  business_license_scan_timeout:
    '사업자등록증 인식이 제한시간 안에 끝나지 않았습니다. 잠시 후 다시 시도해 주세요.',
  business_license_upload_timeout:
    '사업자등록증을 올리는 데 시간이 너무 오래 걸렸습니다. 네트워크 상태를 확인해 주세요.',
  business_license_upload_invalid: '사업자등록증 파일 형식을 확인해 주세요.',
  business_license_unsupported_file: 'PDF 또는 이미지 형식의 사업자등록증만 올릴 수 있습니다.',
  // 보고서 (/reports)
  activity_not_owned: '본인이 진행한 일정에만 보고서를 쓸 수 있습니다.',
  report_not_owned: '본인이 쓴 보고서만 고치거나 제출할 수 있습니다.',
  meeting_notes_changed:
    '다른 화면에서 미팅 메모가 수정되었습니다. 입력한 내용을 보관한 뒤 최신 메모를 다시 불러와 주세요.',
  meeting_notes_stale:
    '새 미팅 결과가 저장되었습니다. 입력한 내용을 보관한 뒤 화면을 새로고침해 주세요.',
  meeting_assignment_stale:
    '다른 화면에서 새 미팅 결과를 저장했습니다. 최신 원문 배정을 불러온 뒤 다시 시도해 주세요.',
  meeting_notes_conflict:
    '보고서에 저장된 미팅 메모가 서로 다릅니다. 입력한 내용을 보관한 뒤 최신 내용을 확인해 주세요.',
  meeting_report_changed:
    '실행 중 보고서가 수정되어 AI 결과를 적용하지 않았습니다. 최신 보고서를 확인해 주세요.',
  report_has_submission_history: '확정 이력이 있는 보고서는 삭제할 수 없습니다.',
  meeting_notes_empty: '기록된 공통·미지정 내용은 비워서 저장할 수 없습니다.',
  meeting_notes_without_evidence: '근거가 없는 공통·미지정 항목에는 메모를 추가할 수 없습니다.',
  report_agent_output_invalid:
    'AI가 보고서 초안을 정상적으로 구성하지 못했습니다. 입력한 내용은 유지됩니다. 다시 시도해 주세요.',
  // 상품 (/products)
  product_not_found: '상품을 찾을 수 없습니다. 목록을 새로 불러와 주세요.',
  product_image_not_found: '등록된 사진이 없습니다.',
  document_link_conflict: '상품과 딜은 동시에 연결할 수 없습니다. 하나만 선택해 주세요.',
  document_summary_not_awaiting_approval:
    '승인 대기 중인 문서 요약이 없습니다. 먼저 OCR·요약을 실행해 주세요.',
  summary_draft_unavailable: '승인 대기 중인 요약 결과를 불러오지 못했습니다. 다시 처리해 주세요.',
  // 파일 업로드 (상품 사진, 자료실)
  invalid_file_name: '파일 이름을 확인해 주세요.',
  unsupported_file_extension: '올릴 수 없는 파일 형식입니다.',
  media_type_mismatch: '파일 형식과 내용이 맞지 않습니다.',
  file_signature_mismatch: '파일 형식과 내용이 맞지 않습니다.',
  empty_file: '빈 파일은 올릴 수 없습니다.',
  file_too_large: '파일 용량이 너무 큽니다.',
  storage_not_configured: '파일 저장소 설정이 완료되지 않았습니다. 서버 설정을 확인해 주세요.',
  // 음성 변환 (/transcriptions)
  stt_not_configured: '음성 변환 설정이 완료되지 않았습니다. 서버 설정을 확인해 주세요.',
  stt_unavailable: '음성 변환 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.',
  // AI 추천 승인 (/activities)
  suggestion_already_processed: '이미 처리된 추천입니다. 목록을 새로 불러옵니다.',
}

/**
 * 통신 계층의 실패를 문구로 바꿉니다. 업무 오류가 아니면 여기서 걸립니다.
 *
 * 응답이 없으면 요청이 서버까지 못 간 것(네트워크 끊김·timeout·DNS 실패)이고,
 * 5xx 는 서버에 닿았지만 서버가 실패한 것입니다. 둘은 사용자가 할 일이 달라서
 * 같은 문구로 뭉뚱그리면 안 됩니다.
 *
 * 502·503·504 를 따로 나누지 않습니다. "잠시 후 다시 시도" 가 그 경우에도 맞는
 * 안내라 분기를 늘릴 이유가 없습니다.
 *
 * @returns 통신 실패가 아니면 null. 호출부가 상태별 업무 문구로 이어 갑니다.
 */
export function transportMessage(error: unknown): string | null {
  if (!isAxiosError(error)) return null
  const status = error.response?.status
  if (status === undefined) return '서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.'
  if (status >= 500) return '서버에서 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'
  return null
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
/**
 * 서버 응답이 아니라 화면이 직접 만든 코드도 같은 표에서 문구를 찾습니다.
 *
 * 폴링으로 받은 실패는 HTTP 오류가 아니라 응답 본문 안의 코드로 옵니다. 그 코드도
 * 같은 곳에서 문구를 얻어야 화면마다 말이 갈라지지 않습니다.
 */
export function messageForCode(code: string, fallback: string): string {
  return code in MESSAGE_BY_DETAIL ? MESSAGE_BY_DETAIL[code] : fallback
}

export function reportGenerationMessage(code: string): string {
  return messageForCode(
    code,
    'AI 보고서 작성을 완료하지 못했습니다. 입력한 내용은 유지됩니다. 다시 시도해 주세요.',
  )
}

export function errorMessage(error: unknown, fallback: string): string {
  const detail = readErrorDetail(error)
  if (detail && detail in MESSAGE_BY_DETAIL) return MESSAGE_BY_DETAIL[detail]

  if (isAxiosError(error)) {
    const status = error.response?.status
    if (status !== undefined && status in MESSAGE_BY_STATUS) return MESSAGE_BY_STATUS[status]
  }

  return fallback
}
