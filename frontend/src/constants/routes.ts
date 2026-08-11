// 화면 경로. 내비게이션 라벨은 navigation.ts 가 갖습니다.
//
// 아직 라우트를 정의하지 않은 경로는 App.tsx 의 catch-all 이 404 로 받습니다.
// 화면을 구현할 때 src/pages/<Name>/ 을 만들고 App.tsx 에 <Route> 를 추가하세요.
export const ROUTES = {
  LOGIN: '/login', // 셸 밖. 내비게이션에 넣지 않습니다.
  DASHBOARD: '/',
  MANAGER: '/manager', // 팀 대시보드 (팀장 전용)
  TEAM: '/team', // 팀 관리 (팀장 전용)
  CUSTOMERS: '/customers',
  CALENDAR: '/calendar',
  DAILY: '/daily', // 업무 보고
  SALES: '/sales', // 매출 보고
  CONTRACTS: '/contracts',
  ORDERS: '/orders',
  DOCUMENTS: '/documents',
  SETTINGS: '/settings',
} as const

export type Route = (typeof ROUTES)[keyof typeof ROUTES]
