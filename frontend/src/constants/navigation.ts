// 사이드바 메뉴의 단일 출처. Sidebar 렌더링과 Topbar breadcrumb 제목이 모두
// 여기서 나오므로 화면 이름이 여러 곳에 흩어지지 않습니다.
import type { FC } from 'react'

import {
  CalendarIcon,
  ContractIcon,
  CustomersIcon,
  DailyReportIcon,
  DashboardIcon,
  DocumentsIcon,
  type IconProps,
  OrdersIcon,
  SalesReportIcon,
  SettingsIcon,
  TeamDashboardIcon,
  TeamIcon,
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
    id: 'manager',
    title: '팀장',
    managerOnly: true,
    items: [
      { to: ROUTES.MANAGER, label: '팀 대시보드', icon: TeamDashboardIcon },
      { to: ROUTES.TEAM, label: '팀 관리', icon: TeamIcon },
    ],
  },
  {
    id: 'account',
    title: '고객',
    items: [{ to: ROUTES.CUSTOMERS, label: '고객·회사', icon: CustomersIcon }],
  },
  {
    id: 'sales',
    title: '영업',
    items: [
      { to: ROUTES.CALENDAR, label: '캘린더', icon: CalendarIcon },
      { to: ROUTES.DAILY, label: '업무 보고', icon: DailyReportIcon },
      { to: ROUTES.SALES, label: '매출 보고', icon: SalesReportIcon },
    ],
  },
  {
    id: 'deals',
    title: '계약·발주',
    items: [
      { to: ROUTES.CONTRACTS, label: '계약 현황', icon: ContractIcon },
      { to: ROUTES.ORDERS, label: '발주 관리', icon: OrdersIcon },
    ],
  },
  {
    id: 'documents',
    ariaLabel: '자료실',
    items: [{ to: ROUTES.DOCUMENTS, label: '자료실', icon: DocumentsIcon }],
  },
  {
    id: 'settings',
    ariaLabel: '설정',
    items: [{ to: ROUTES.SETTINGS, label: '설정', icon: SettingsIcon }],
  },
]

const NAV_ITEMS = NAV_SECTIONS.flatMap((section) => section.items)

/** 경로에 해당하는 화면 이름. 정의되지 않은 경로면 undefined. */
export function findNavLabel(pathname: string): string | undefined {
  return NAV_ITEMS.find((item) => item.to === pathname)?.label
}
