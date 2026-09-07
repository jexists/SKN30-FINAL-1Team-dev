export type Role = 'manager' | 'member'

/**
 * 팀 관리 화면의 한 줄. 서버(GET /team/members)가 주는 모양 그대로입니다.
 *
 * 목표는 그달치 하나입니다. 분기·연간은 따로 저장하지 않고 화면이 월 목표에서 환산해
 * 보여 줍니다.
 */
export interface TeamMemberRow {
  id: string
  display_name: string
  email: string | null
  job_title: string | null
  role_code: Role
  active: boolean
  /** 팀장이 고른 담당자 이름표 색(#rrggbb). null 이면 기본 회색입니다. */
  badge_color: string | null
  target_amount: number
  confirmed_amount: number
  /** 목표를 세우지 않았으면 0% 가 아니라 null 입니다. 미설정과 미달성은 다릅니다. */
  achievement_rate: number | null
}

export interface TeamOverviewResponse {
  /** YYYY-MM */
  target_month: string
  team_target: number
  team_confirmed: number
  team_rate: number | null
  /** 팀원 목표의 합계. 지금은 team_target 과 같지만 화면이 둘을 나눠 보여 줍니다. */
  member_target_sum: number
  members: TeamMemberRow[]
}

/** 보낸 항목만 바꿉니다. */
export interface TeamMemberPatchRequest {
  job_title?: string
  role_code?: Role
  active?: boolean
  /** null 을 보내면 색을 지우고 기본 회색으로 되돌립니다. */
  badge_color?: string | null
  monthly_target_amount?: number
  /** 어느 달의 목표를 고치는지. 그달 1일입니다. */
  target_month?: string
}
