import type { ColumnTone, SupportStatusCode } from '@/types'

/**
 * 불만 상태 네 가지. 목록 탭, 등록 모달의 선택 칸, 드로어의 상태 바꾸기가 모두
 * 이 배열 하나를 봅니다. 서버의 support_request_status_code_check 와 같은 순서입니다.
 */
export const STATES: { code: SupportStatusCode; label: string; tone: ColumnTone }[] = [
  { code: 'received', label: '접수', tone: 'gray' },
  { code: 'diagnosing', label: '원인파악', tone: 'orange' },
  { code: 'in_progress', label: '처리중', tone: 'blue' },
  { code: 'completed', label: '처리완료', tone: 'green' },
]

export const STATUS_LABEL = Object.fromEntries(
  STATES.map((state) => [state.code, state.label]),
) as Record<SupportStatusCode, string>
