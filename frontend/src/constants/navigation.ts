// 사이드바 메뉴의 단일 출처. Sidebar 렌더링과 Topbar breadcrumb 제목이 모두
// 여기서 나오므로 화면 이름이 여러 곳에 흩어지지 않습니다.
import type { FC } from 'react'

import {
  CalendarIcon,
  ComplaintIcon,
  ContractIcon,
  CustomersIcon,
  DailyReportIcon,
  DashboardIcon,
  DocumentsIcon,
  type IconProps,
  OrdersIcon,
  QuoteIcon,
  SalesReportIcon,
  TeamIcon,
  VisitIcon,
} from '@/components/icons'
import { ROUTES, type Route } from '@/constants/routes'

export interface NavItem {
  to: Route
  label: string
  icon: FC<IconProps>
}

export interface NavSection {
  id: string
  /** 섹션 캡션. 항목이 하나뿐인 섹션은 캡션 없이 ariaLabel 만 씁니다. */
  title?: string
  /** 아이콘 레일에서 캡션 자리에 대신 넣는 짧은 이름. 없으면 title 을 그대로 씁니다. */
  shortTitle?: string
  ariaLabel?: string
  /** 팀장 역할에게만 보이는 섹션 */
  managerOnly?: boolean
  items: NavItem[]
}

export const NAV_SECTIONS: NavSection[] = [
  {
    id: 'dashboard',
    ariaLabel: '대시보드',
    items: [{ to: ROUTES.DASHBOARD, label: '대시보드', icon: DashboardIcon }],
  },
  {
    id: 'account',
    title: '고객',
    items: [
      { to: ROUTES.CUSTOMERS, label: '고객현황', icon: CustomersIcon },
      { to: ROUTES.COMPLAINTS, label: '고객불만관리', icon: ComplaintIcon },
    ],
  },
  {
    id: 'sales',
    title: '영업',
    items: [
      { to: ROUTES.CALENDAR, label: '캘린더', icon: CalendarIcon },
      { to: ROUTES.DAILY, label: '업무보고', icon: DailyReportIcon },
      { to: ROUTES.SALES, label: '매출분석', icon: SalesReportIcon },
    ],
  },
  {
    id: 'deals',
    title: '딜상세관리',
    shortTitle: '딜',
    items: [
      { to: ROUTES.DEALS, label: '영업현황', icon: VisitIcon },
      { to: ROUTES.QUOTES, label: '견적현황', icon: QuoteIcon },
      { to: ROUTES.CONTRACTS, label: '계약현황', icon: ContractIcon },
      { to: ROUTES.ORDERS, label: '발주현황', icon: OrdersIcon },
    ],
  },
  {
    id: 'documents',
    ariaLabel: '자료실',
    items: [{ to: ROUTES.DOCUMENTS, label: '자료실', icon: DocumentsIcon }],
  },
  {
    // 팀 실적 조회는 Topbar 의 보기 범위 스위처가 맡습니다. 여기 남는 것은
    // 화면 전체가 팀장 것인 '팀 관리' 하나뿐입니다.
    id: 'manager',
    ariaLabel: '팀 관리',
    managerOnly: true,
    items: [{ to: ROUTES.TEAM, label: '팀 관리', icon: TeamIcon }],
  },
  // 설정 메뉴는 두지 않습니다. 바꿀 수 있는 값이 없어 마이페이지로 대체했고,
  // 진입은 사이드바 하단 이름과 헤더 아바타에서 합니다.
]

const NAV_ITEMS = NAV_SECTIONS.flatMap((section) => section.items)

/**
 * 사이드바에 없는 화면의 이름. 미팅보고서처럼 다른 화면에서만 들어가는 곳도
 * breadcrumb 에는 제 이름이 나와야 합니다.
 */
const OFF_MENU_LABELS: { to: Route; label: string }[] = [
  { to: ROUTES.MEETINGS, label: '미팅보고서' },
  { to: ROUTES.NOTIFICATIONS, label: '알림' },
  { to: ROUTES.MYPAGE, label: '마이페이지' },
  { to: ROUTES.TERMS, label: '이용약관' },
  { to: ROUTES.PRIVACY, label: '개인정보처리방침' },
  { to: ROUTES.LEGAL, label: '법적고지' },
]

/**
 * 경로에 해당하는 화면 이름. 정의되지 않은 경로면 undefined.
 *
 * 하위 경로(예: /daily/new)는 부모 메뉴의 이름을 물려받습니다. 가장 긴 것부터 보므로
 * 나중에 /daily 아래 별도 메뉴가 생겨도 그쪽이 먼저 잡힙니다.
 * '/' 는 모든 경로의 접두사라 완전일치일 때만 씁니다.
 */
export function findNavLabel(pathname: string): string | undefined {
  return [...NAV_ITEMS, ...OFF_MENU_LABELS]
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => item.to === pathname || (item.to !== '/' && pathname.startsWith(`${item.to}/`)))
    ?.label
}
