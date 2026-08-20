import type { TeamMember } from '@/types'

export const TEAM_API_ERROR = '팀 구성원과 매출 목표 조회 API가 백엔드에 제공되지 않습니다.'
export const TEAM: TeamMember[] = []

export function findMemberById(id: string): TeamMember | undefined {
  return TEAM.find((member) => member.id === id)
}

export function findMemberByName(name: string): TeamMember | undefined {
  return TEAM.find((member) => member.name === name)
}
