// GET /api/dashboard 한 벌. 진입하자마자 화면에 서는 숫자와 오늘 일정만 담습니다.
// 눌러야 열리는 드로어의 목록과 본문은 각 도메인 API 가 그때 줍니다.
import type { ActivityRead } from './agenda'

export interface NoticeBrief {
  id: string
  tag: string | null
  author_display_name: string
  title: string
  published_at: string
  due_at: string | null
  due_text: string | null
}

export interface NoticeSummary {
  total: number
  items: NoticeBrief[]
}

export interface CountCard {
  count: number
}

export interface FollowUpCard {
  total: number
  overdue: number
  due_within_7_days: number
}

export interface SupportCard {
  total: number
  in_progress: number
  urgent: number
}

export interface RenewalCard {
  within_days: number | null
  count: number
  /** "새봄정형외과 외 2곳" 의 앞자리. 나머지는 count 로 셉니다. */
  lead_company_name: string | null
}

export interface SalesTargetCard {
  target_month: string
  target_amount: number | null
  confirmed_amount: number
  in_progress_amount: number
  /** 목표가 없으면 null 입니다. 0% 와 구분해야 합니다. */
  achievement_rate: number | null
}

export interface WeeklyDay {
  date: string
  meeting_count: number
  task_count: number
  due_count: number
}

export interface WeeklyBand {
  start_date: string
  end_date: string
  days: WeeklyDay[]
}

export interface DashboardResponse {
  as_of: string
  date: string
  notices: NoticeSummary
  directives: NoticeSummary
  visited_companies: CountCard
  activities: CountCard
  today_activities: ActivityRead[]
  follow_ups: FollowUpCard
  support_requests: SupportCard
  contract_renewals: RenewalCard
  sales_target: SalesTargetCard
  weekly: WeeklyBand
}
