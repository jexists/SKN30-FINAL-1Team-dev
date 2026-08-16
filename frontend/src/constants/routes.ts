import type { ReportKind } from '@/types'

// 화면 경로. 내비게이션 라벨은 navigation.ts 가 갖습니다.
//
// 아직 라우트를 정의하지 않은 경로는 App.tsx 의 catch-all 이 404 로 받습니다.
// 화면을 구현할 때 src/pages/<Name>/ 을 만들고 App.tsx 에 <Route> 를 추가하세요.
export const ROUTES = {
  LOGIN: '/login', // 셸 밖. 내비게이션에 넣지 않습니다.
  DASHBOARD: '/',
  TEAM: '/team', // 팀 관리 (팀장 전용)
  CUSTOMERS: '/customers',
  COMPLAINTS: '/complaints', // 고객 불만 관리
  NOTIFICATIONS: '/notifications', // 알림. 진입은 헤더 벨에서 합니다.
  CALENDAR: '/calendar',
  MEETINGS: '/meetings', // 미팅보고서. 진입은 대시보드 일정에서 합니다.
  DAILY: '/daily', // 업무 보고
  VISITS: '/visits', // 영업 현황
  SALES: '/sales', // 매출 분석
  QUOTES: '/quotes', // 견적 현황
  CONTRACTS: '/contracts',
  ORDERS: '/orders',
  DOCUMENTS: '/documents',
  // 마이페이지. 진입은 사이드바 하단 이름과 헤더 아바타에서 합니다.
  // 바꿀 수 있는 설정이 없어 '설정' 대신 내 정보·약관을 보는 화면 하나만 둡니다.
  MYPAGE: '/mypage',
  TERMS: '/mypage/terms', // 이용약관
  PRIVACY: '/mypage/privacy', // 개인정보처리방침
  LEGAL: '/mypage/legal', // 법적고지
} as const

export type Route = (typeof ROUTES)[keyof typeof ROUTES]

// 쿼리에 쓰는 종류 값. 기간 탭(?tab=)과 같은 어휘를 씁니다.
const KIND_PARAM: Record<ReportKind, string> = { 일일: 'daily', 주간: 'weekly', 월간: 'monthly' }

/**
 * 업무보고 작성 화면. dateISO 를 주면 그날 보고서를, kind 를 주면 그 종류를 씁니다.
 * 밀린 날짜를 소급 작성하는 경로도 이 하나를 씁니다.
 */
export const dailyComposePath = (dateISO?: string, kind: ReportKind = '일일') => {
  const query = new URLSearchParams()
  if (dateISO) query.set('date', dateISO)
  if (kind !== '일일') query.set('kind', KIND_PARAM[kind])
  const suffix = query.toString()
  return suffix ? `${ROUTES.DAILY}/new?${suffix}` : `${ROUTES.DAILY}/new`
}

/** 제출된 보고서 상세 */
export const dailyReportPath = (id: string) => `${ROUTES.DAILY}/${id}`

/**
 * 미팅보고서 작성 화면. 일정 하나를 기록하므로 그 일정 id 를 달고 갑니다.
 * 이미 쓴 기록을 고칠 때도 같은 경로를 씁니다.
 */
export const meetingComposePath = (agendaId?: string) =>
  agendaId
    ? `${ROUTES.MEETINGS}/new?agenda=${encodeURIComponent(agendaId)}`
    : `${ROUTES.MEETINGS}/new`

/** 확정한 미팅보고서 상세 */
export const meetingReportPath = (id: string) => `${ROUTES.MEETINGS}/${id}`

/** 영업 보드. 목록과 같은 데이터를 단계별 칸으로 봅니다. */
export const visitBoardPath = () => `${ROUTES.VISITS}/board`

/** 계약 상세. 계약번호(FM-CT-2026-0039)를 그대로 씁니다. */
export const contractPath = (no: string) => `${ROUTES.CONTRACTS}/${no}`

/** 계약 추가 화면. stageId 를 주면 그 단계로 시작합니다. */
export const contractNewPath = (stageId?: string) =>
  stageId
    ? `${ROUTES.CONTRACTS}/new?stage=${encodeURIComponent(stageId)}`
    : `${ROUTES.CONTRACTS}/new`

/** 발주 상세. 발주번호(FM-PO-2026-0021)를 그대로 씁니다. */
export const orderPath = (no: string) => `${ROUTES.ORDERS}/${no}`

/** 발주 추가 화면. status 를 주면 그 상태로 시작합니다. */
export const orderNewPath = (status?: string) =>
  status ? `${ROUTES.ORDERS}/new?status=${encodeURIComponent(status)}` : `${ROUTES.ORDERS}/new`
