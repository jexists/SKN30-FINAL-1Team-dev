// demo/layout_v3.html 의 인라인 SVG 를 컴포넌트로 옮긴 것입니다.
// viewBox·stroke 같은 공통 속성은 Icon 한 곳에만 두고 각 아이콘은 path 만 갖습니다.
import type { SVGProps } from 'react'

export type IconProps = SVGProps<SVGSVGElement>

function Icon({ children, strokeWidth = 1.7, ...rest }: IconProps) {
  return (
    <svg
      width={18}
      height={18}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  )
}

/* ---- 내비게이션 ---- */

export function DashboardIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 13h5v7H4zM10 4h5v16h-5zM16 9h4v11h-4z" />
    </Icon>
  )
}

export function TeamDashboardIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 3v18h18" />
      <path d="M7 15l3.5-4 3 2.5L20 7" />
    </Icon>
  )
}

export function TeamIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 20v-1.5A4.5 4.5 0 0 1 8 14h2a4.5 4.5 0 0 1 4.5 4.5V20" />
      <path d="M17 11a2.5 2.5 0 1 0 0-5M18 14a4 4 0 0 1 3 3.9V20" />
    </Icon>
  )
}

export function CustomersIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 21V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v15M15 21V10h3a2 2 0 0 1 2 2v9M3 21h18M8 8h3M8 12h3M8 16h3" />
    </Icon>
  )
}

export function CalendarIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </Icon>
  )
}

export function DailyReportIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4V3h6v1M9 10h6M9 14h4" />
    </Icon>
  )
}

export function SalesReportIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 17l6-6 4 4 7-7" />
      <path d="M14 8h6v6" />
    </Icon>
  )
}

export function ContractIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </Icon>
  )
}

export function OrdersIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M21 16V8l-9-5-9 5v8l9 5z" />
      <path d="M3.3 7.5L12 12.5l8.7-5M12 12.5V22" />
    </Icon>
  )
}

export function DocumentsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </Icon>
  )
}

export function SettingsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h10M18 18h2" />
      <circle cx="16" cy="6" r="2" />
      <circle cx="8" cy="12" r="2" />
      <circle cx="16" cy="18" r="2" />
    </Icon>
  )
}

/* ---- 셸 UI ---- */

export function ChevronLeftIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2} {...props}>
      <path d="M14 6l-6 6 6 6" />
    </Icon>
  )
}

export function ChevronRightIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2} {...props}>
      <path d="M10 6l6 6-6 6" />
    </Icon>
  )
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2.2} {...props}>
      <path d="M6 9l6 6 6-6" />
    </Icon>
  )
}

export function ArrowDownIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2.2} {...props}>
      <path d="M12 5v14M6 13l6 6 6-6" />
    </Icon>
  )
}

export function LogoutIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.8} {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </Icon>
  )
}

export function MenuIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2} {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </Icon>
  )
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2.2} {...props}>
      <path d="M18 6L6 18M6 6l12 12" />
    </Icon>
  )
}

export function BellIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.8} {...props}>
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </Icon>
  )
}

export function NotFoundIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.5} {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h5M9 17h3" />
    </Icon>
  )
}

/* ---- 목록·표 도구 ---- */

export function SearchIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.9} {...props}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </Icon>
  )
}

export function FilterIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.8} {...props}>
      <path d="M4 6h16l-6.2 7.2V19l-3.6-2v-3.8z" />
    </Icon>
  )
}

export function ColumnsIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9.5 4v16M15 4v16" />
    </Icon>
  )
}

export function PlusIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2.2} {...props}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  )
}

export function UploadIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.8} {...props}>
      <path d="M12 16V4M7.5 8.5L12 4l4.5 4.5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </Icon>
  )
}

export function DownloadIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.8} {...props}>
      <path d="M12 4v12M7.5 11.5L12 16l4.5-4.5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </Icon>
  )
}

/** 정렬되지 않은 헤더의 위아래 화살표 */
export function SortIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2} {...props}>
      <path d="M8 9l4-4 4 4M8 15l4 4 4-4" />
    </Icon>
  )
}

export function ArrowUpIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2.2} {...props}>
      <path d="M12 19V5M6 11l6-6 6 6" />
    </Icon>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <Icon strokeWidth={2.4} {...props}>
      <path d="M5 12.5l4.5 4.5L19 7" />
    </Icon>
  )
}

export function TrashIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.8} {...props}>
      <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
      <path d="M10 11v6M14 11v6" />
    </Icon>
  )
}

export function MailIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.6} {...props}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3.5 7l8.5 6 8.5-6" />
    </Icon>
  )
}

export function PhoneIcon(props: IconProps) {
  return (
    <Icon strokeWidth={1.6} {...props}>
      <path d="M7 3h3l1.5 4.5-2 1.5a12 12 0 0 0 5.5 5.5l1.5-2L21 14v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 5 5.2 2 2 0 0 1 7 3z" />
    </Icon>
  )
}
