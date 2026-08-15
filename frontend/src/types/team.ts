export type Role = 'manager' | 'member'

export interface TeamMember {
  /** 백엔드 rep_id 자리 */
  id: string
  /** 시드 데이터의 owner 문자열과 같아야 합니다. */
  name: string
  title: string
  role: Role
  /** ERD 의 employment_status. 퇴사·휴직자는 스코프 선택지에서 빠집니다. */
  active: boolean
  /** 월 매출 목표(원). 합계는 counters.ts 의 팀 월 목표 3억과 같습니다. */
  monthlyTarget: number
}
