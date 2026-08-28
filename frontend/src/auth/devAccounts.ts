/** 로컬에서 바로 만든 계정의 고정 비밀번호. backend/app/api/admin.py 의 값과 같아야 합니다. */
export const LOCAL_DEV_PASSWORD = '12341234'

/** 로컬 빠른 로그인 대상. docs/sample-data-2026q3.md 의 테스트1 팀 계정입니다. */
export const DEV_ACCOUNTS = [
  { label: '팀원1', email: 'bt1@naver.com' },
  { label: '팀원2', email: 'bt2@naver.com' },
  { label: '팀장', email: 'jungia21@naver.com' },
] as const
